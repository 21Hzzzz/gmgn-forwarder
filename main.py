import asyncio

from browser_manager import BrowserManager
from deduplicator import MessageDeduplicator
from gmgn_parser import extract_triggers_map
from settings import load_settings
from telegram_sender import TelegramSender
from watchdog import Watchdog


async def main():
    settings = load_settings()
    bm = await BrowserManager.create(settings)
    telegram = TelegramSender(
        settings.tg_bot_token,
        settings.tg_chat_id,
        queue_max=settings.tg_queue_max,
        outbox_path=settings.tg_outbox_path,
        failed_path=settings.tg_failed_path,
    )
    watchdog = Watchdog(settings.watchdog_timeout)

    try:
        await telegram.start()

        async def publish(message: dict) -> bool:
            return await telegram.send(message)

        deduplicator = MessageDeduplicator(
            publish,
            state_path=settings.dedup_state_path,
        )

        def handle_payload(payload: dict) -> None:
            watchdog.feed()
            triggers = extract_triggers_map(payload["data"])
            if triggers:
                print(f"收到 GMGN 动作: {triggers}")

            for item in payload["data"]:
                if isinstance(item, dict):
                    deduplicator.process(item)

        if await bm.is_logged_in() or await bm.login():
            print("已登录，进入监听页")
            bm.listen_gmgn_messages(handle_payload, watchdog.feed)
            await bm.goto_monitor_page()
            await bm.handle_popups()
            await bm.switch_to_mine_tab()
            watchdog.feed()
            print("监听页准备完成，等待 WS 数据...")
            while True:
                await asyncio.sleep(settings.watchdog_poll_interval)
                if watchdog.is_timed_out():
                    elapsed = watchdog.time_since_last_msg()
                    print(f"看门狗警报: {elapsed:.0f}s 未收到 GMGN 数据，准备恢复页面")
                    try:
                        await bm.recover_after_timeout()
                        watchdog.feed()
                    except Exception as e:
                        print(f"页面恢复失败: {e}")
        else:
            print("仍然未登录")
    finally:
        if "deduplicator" in locals():
            await deduplicator.close()
        await telegram.stop()
        await bm.close()


if __name__ == "__main__":
    asyncio.run(main())
