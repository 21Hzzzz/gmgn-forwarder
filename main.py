import asyncio
import os
import subprocess

from browser_manager import BrowserManager
from deduplicator import MessageDeduplicator
from gmgn_parser import extract_triggers_map
from settings import Settings, load_settings
from telegram_sender import TelegramSender
from watchdog import Watchdog

try:
    from xvfbwrapper import Xvfb
    XVFB_IMPORT_ERROR = None
except (ImportError, OSError) as exc:
    Xvfb = None
    XVFB_IMPORT_ERROR = exc


def _cleanup_orphan_processes() -> None:
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "ubuntu"
    for target in ("chromium", "Xvfb"):
        try:
            result = subprocess.run(
                ["pkill", "-u", user, "-f", target],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            print("pkill 不存在，跳过旧进程清理")
            return

        if result.returncode == 0:
            print(f"已清理旧 {target} 进程")
        elif result.returncode == 1:
            print(f"无旧 {target} 进程")
        else:
            error = result.stderr.decode(errors="replace").strip()
            print(f"清理旧 {target} 进程失败，继续启动: {error}")


def _start_virtual_display(settings: Settings):
    if Xvfb is None:
        raise RuntimeError(
            "无法启动 Xvfb，请确认在 Linux 环境运行并已安装依赖: uv sync"
        ) from XVFB_IMPORT_ERROR

    display = Xvfb(width=settings.xvfb_width, height=settings.xvfb_height)
    display.start()
    print(f"Xvfb 已启动: {settings.xvfb_width}x{settings.xvfb_height}")
    return display


async def main():
    settings = load_settings()
    vdisplay = None
    bm = None
    telegram = None

    try:
        _cleanup_orphan_processes()
        vdisplay = _start_virtual_display(settings)

        bm = await BrowserManager.create(settings)
        telegram = TelegramSender(
            settings.tg_bot_token,
            settings.tg_chat_id,
            queue_max=settings.tg_queue_max,
            outbox_path=settings.tg_outbox_path,
            failed_path=settings.tg_failed_path,
        )
        watchdog = Watchdog(settings.watchdog_timeout)

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
        if telegram is not None:
            await telegram.stop()
        if bm is not None:
            await bm.close()
        if vdisplay is not None:
            vdisplay.stop()
            print("Xvfb 已停止")


if __name__ == "__main__":
    asyncio.run(main())
