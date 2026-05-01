import asyncio
from pathlib import Path

from telegram_client import TelegramClient
from telegram_formatter import TelegramFormatter
from telegram_outbox import TelegramOutbox


class TelegramSender:
    retry_base_delay = 30
    retry_max_delay = 300

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        queue_max: int = 1000,
        outbox_path: str | Path | None = None,
        failed_path: str | Path | None = None,
        client: TelegramClient | None = None,
        formatter: TelegramFormatter | None = None,
        outbox: TelegramOutbox | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = client or TelegramClient(bot_token)
        self.formatter = formatter or TelegramFormatter(chat_id)
        self.outbox = outbox or TelegramOutbox(
            outbox_path,
            failed_path=failed_path,
            max_size=queue_max,
        )
        self._outbox_lock: asyncio.Lock | None = None
        self._wake_event: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def start(self) -> None:
        if not self.enabled:
            print("Telegram 未配置 TG_BOT_TOKEN/TG_CHAT_ID，跳过群组推送")
            return

        self._outbox_lock = asyncio.Lock()
        self._wake_event = asyncio.Event()
        migrated = self.outbox.load()
        if migrated:
            print(f"已迁移 Telegram 旧失败队列: {migrated} 条")

        await self.client.start()
        self._worker = asyncio.create_task(self._worker_loop())
        self._wake_event.set()
        print(f"Telegram 推送已启用，目标群组: {self.chat_id}")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

        if self._outbox_lock is not None:
            async with self._outbox_lock:
                self.outbox.save()

        await self.client.stop()

    async def send(self, message: dict) -> bool:
        if not self.enabled or self._outbox_lock is None:
            return False

        async with self._outbox_lock:
            saved = self.outbox.add(message)

        if saved:
            self._wake_worker()
        return saved

    async def _worker_loop(self) -> None:
        if self._wake_event is None:
            return

        while True:
            item = await self._next_due_item()
            if item is None:
                wait_seconds = await self._seconds_until_next_due()
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=wait_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
                self._wake_event.clear()
                continue

            item_id = item["id"]
            message = item["message"]
            try:
                sent = await self._send_message(message)
            except Exception as exc:
                sent = False
                print(f"Telegram worker 发送异常: {exc}")

            async with self._outbox_lock:
                if item_id not in self.outbox.messages:
                    continue

                if sent:
                    self.outbox.remove(item_id)
                    continue

                attempts = int(self.outbox.messages[item_id].get("attempts") or 0) + 1
                self.outbox.mark_failed(
                    item_id,
                    delay=self._retry_delay(attempts),
                    error="send failed",
                )
                print(f"Telegram 发送失败，保留在 outbox 中等待重试: {attempts}")

    async def _next_due_item(self) -> dict | None:
        if self._outbox_lock is None:
            return None

        async with self._outbox_lock:
            return self.outbox.due_item()

    async def _seconds_until_next_due(self) -> float:
        if self._outbox_lock is None:
            return 60

        async with self._outbox_lock:
            return self.outbox.seconds_until_next_due()

    async def _send_message(self, message: dict) -> bool:
        if message.get("action") == "photo":
            payload = self.formatter.build_photo_change_payload(message)
            if payload and await self.client.send_api("sendMediaGroup", payload):
                return True

        payload = self.formatter.build_send_message_payload(message)
        return await self.client.send_api("sendMessage", payload) is not None

    def _retry_delay(self, attempts: int) -> int:
        return min(self.retry_base_delay * max(attempts, 1), self.retry_max_delay)

    def _wake_worker(self) -> None:
        if self._wake_event is not None:
            self._wake_event.set()
