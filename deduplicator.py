import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from gmgn_parser import build_standardized_message


PublishCallback = Callable[[dict], Awaitable[bool]]


class MessageDeduplicator:
    timeout = 0.5
    max_history = 1000

    def __init__(
        self,
        publish: PublishCallback,
        *,
        state_path: str | Path | None = None,
    ) -> None:
        self._publish = publish
        self._pending: dict[str, tuple[dict, asyncio.TimerHandle]] = {}
        self._processed_ids: set[str] = set()
        self._inflight_ids: set[str] = set()
        self._history: list[str] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._state_path = Path(state_path) if state_path else None
        self._load_history()

    def process(self, item: dict) -> None:
        internal_id = item.get("i")
        if not internal_id:
            self._start_dispatch(item, None)
            return

        if internal_id in self._processed_ids or internal_id in self._inflight_ids:
            return

        cp = item.get("cp")
        if cp == 1:
            if internal_id in self._pending:
                _, timer = self._pending.pop(internal_id)
                timer.cancel()

            self._start_dispatch(item, internal_id)
            return

        if internal_id in self._pending:
            return

        loop = asyncio.get_running_loop()
        timer = loop.call_later(self.timeout, self._fallback, internal_id)
        self._pending[internal_id] = (item, timer)

    async def close(self) -> None:
        pending_items = list(self._pending.items())
        self._pending.clear()

        for internal_id, (item, timer) in pending_items:
            timer.cancel()
            if internal_id not in self._processed_ids:
                self._start_dispatch(item, internal_id)

        tasks = set(self._tasks)
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=5)
            for task in done:
                try:
                    task.result()
                except Exception as exc:
                    print(f"Dedup 发布任务异常: {exc}")

            if pending:
                print(f"Dedup 关闭时仍有 {len(pending)} 个发布任务未完成")

        self._save_history()

    def _fallback(self, internal_id: str) -> None:
        pending = self._pending.pop(internal_id, None)
        if pending is None:
            return

        item, _ = pending
        if internal_id in self._processed_ids or internal_id in self._inflight_ids:
            return

        self._start_dispatch(item, internal_id)

    def _start_dispatch(self, item: dict, internal_id: str | None) -> None:
        if internal_id is not None:
            self._inflight_ids.add(internal_id)

        task = asyncio.create_task(self._dispatch(item, internal_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _dispatch(self, item: dict, internal_id: str | None) -> None:
        try:
            message = build_standardized_message(item)
            data = message.to_dict()
        except Exception as exc:
            if internal_id is not None:
                self._inflight_ids.discard(internal_id)
            print(f"GMGN 消息标准化失败: {exc}")
            return

        author = data.get("author") or {}
        content = data.get("content") or {}
        handle = author.get("handle") or "unknown"
        text = content.get("text") or ""
        print(f"发布 [{message.action}] @{handle}: {text[:80]}")

        try:
            published = await self._publish(data)
        except Exception as exc:
            published = False
            print(f"发布到 outbox 失败: {exc}")

        if internal_id is None:
            return

        if published:
            self._mark_processed(internal_id)
        else:
            self._inflight_ids.discard(internal_id)

    def _mark_processed(self, internal_id: str) -> None:
        self._inflight_ids.discard(internal_id)
        if internal_id in self._processed_ids:
            return

        self._processed_ids.add(internal_id)
        self._history.append(internal_id)

        if len(self._history) > self.max_history:
            old_id = self._history.pop(0)
            self._processed_ids.discard(old_id)

        self._save_history()

    def _load_history(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return

        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Dedup 状态读取失败，忽略旧状态: {exc}")
            return

        if not isinstance(data, list):
            print("Dedup 状态格式无效，忽略旧状态")
            return

        history = [item for item in data if isinstance(item, str)]
        self._history = history[-self.max_history :]
        self._processed_ids = set(self._history)
        if self._history:
            print(f"已加载 dedup 历史: {len(self._history)} 条")

    def _save_history(self) -> None:
        if self._state_path is None:
            return

        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._state_path.with_suffix(f"{self._state_path.suffix}.tmp")
            temp_path.write_text(
                json.dumps(self._history[-self.max_history :], ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(self._state_path)
        except Exception as exc:
            print(f"Dedup 状态保存失败: {exc}")
