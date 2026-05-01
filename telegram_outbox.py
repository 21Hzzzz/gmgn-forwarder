import hashlib
import json
import time
from pathlib import Path
from typing import Any


class TelegramOutbox:
    def __init__(
        self,
        outbox_path: str | Path | None,
        *,
        failed_path: str | Path | None = None,
        max_size: int = 1000,
    ) -> None:
        self.outbox_path = Path(outbox_path) if outbox_path else None
        self.failed_path = Path(failed_path) if failed_path else None
        self.max_size = max_size
        self.messages: dict[str, dict[str, Any]] = {}

    def load(self) -> int:
        self.messages = self._load_outbox()
        migrated = self._migrate_failed_messages()
        if migrated and self.save():
            self._clear_failed_messages()
        return migrated

    def add(self, message: dict) -> bool:
        item_id = self.message_id(message)
        if item_id in self.messages:
            return True

        if self.max_size > 0 and len(self.messages) >= self.max_size:
            print("Telegram outbox 已满，拒绝写入新消息")
            return False

        now = time.time()
        self.messages[item_id] = {
            "id": item_id,
            "message": message,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "next_attempt_at": 0,
            "last_error": None,
        }
        if self.save():
            return True

        self.messages.pop(item_id, None)
        return False

    def remove(self, item_id: str) -> bool:
        self.messages.pop(item_id, None)
        return self.save()

    def mark_failed(self, item_id: str, *, delay: int, error: str) -> bool:
        item = self.messages.get(item_id)
        if item is None:
            return True

        attempts = int(item.get("attempts") or 0) + 1
        item["attempts"] = attempts
        item["updated_at"] = time.time()
        item["next_attempt_at"] = time.time() + delay
        item["last_error"] = error
        return self.save()

    def due_item(self) -> dict | None:
        now = time.time()
        due_items = [
            item
            for item in self.messages.values()
            if float(item.get("next_attempt_at") or 0) <= now
        ]
        if not due_items:
            return None

        return min(due_items, key=lambda item: float(item.get("created_at") or 0)).copy()

    def seconds_until_next_due(self) -> float:
        if not self.messages:
            return 60

        next_due = min(
            float(item.get("next_attempt_at") or 0)
            for item in self.messages.values()
        )
        return max(min(next_due - time.time(), 60), 0.1)

    def save(self) -> bool:
        if self.outbox_path is None:
            return True

        try:
            self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.outbox_path.with_suffix(f"{self.outbox_path.suffix}.tmp")
            payload = {"version": 1, "messages": self.messages}
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(self.outbox_path)
            return True
        except Exception as exc:
            print(f"Telegram outbox 保存失败: {exc}")
            return False

    def _load_outbox(self) -> dict[str, dict[str, Any]]:
        if self.outbox_path is None or not self.outbox_path.exists():
            return {}

        try:
            data = json.loads(self.outbox_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Telegram outbox 读取失败，忽略旧文件: {exc}")
            return {}

        if isinstance(data, dict) and isinstance(data.get("messages"), dict):
            raw_messages = data["messages"]
        elif isinstance(data, list):
            raw_messages = {self.message_id(item): {"message": item} for item in data}
        else:
            print("Telegram outbox 格式无效，忽略旧文件")
            return {}

        outbox: dict[str, dict[str, Any]] = {}
        for key, value in raw_messages.items():
            if not isinstance(value, dict):
                continue

            message = value.get("message")
            if not isinstance(message, dict):
                continue

            item_id = str(value.get("id") or key or self.message_id(message))
            outbox[item_id] = {
                "id": item_id,
                "message": message,
                "attempts": int(value.get("attempts") or 0),
                "created_at": float(value.get("created_at") or time.time()),
                "updated_at": float(value.get("updated_at") or time.time()),
                "next_attempt_at": float(value.get("next_attempt_at") or 0),
                "last_error": value.get("last_error"),
            }

        if outbox:
            print(f"已加载 Telegram outbox: {len(outbox)} 条")
        return outbox

    def _migrate_failed_messages(self) -> int:
        count = 0
        for message in self._load_failed_messages():
            item_id = self.message_id(message)
            if item_id in self.messages:
                continue

            now = time.time()
            self.messages[item_id] = {
                "id": item_id,
                "message": message,
                "attempts": 0,
                "created_at": now,
                "updated_at": now,
                "next_attempt_at": 0,
                "last_error": "migrated from failed jsonl",
            }
            count += 1

        return count

    def _load_failed_messages(self) -> list[dict]:
        if self.failed_path is None or not self.failed_path.exists():
            return []

        messages: list[dict] = []
        try:
            for line in self.failed_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    messages.append(item)
        except Exception as exc:
            print(f"Telegram 旧失败队列读取失败，忽略旧文件: {exc}")
            return []

        return messages

    def _clear_failed_messages(self) -> None:
        if self.failed_path is None:
            return

        try:
            self.failed_path.unlink(missing_ok=True)
        except Exception as exc:
            print(f"Telegram 旧失败队列清理失败: {exc}")

    @staticmethod
    def message_id(message: dict) -> str:
        internal_id = message.get("internal_id")
        if internal_id:
            return str(internal_id)

        raw = json.dumps(message, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
