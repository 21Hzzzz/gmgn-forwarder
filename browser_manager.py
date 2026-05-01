import asyncio
from collections.abc import Callable

from gmgn_parser import iter_polling_messages, parse_socketio_payload
from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from settings import Settings


class BrowserManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    @classmethod
    async def create(cls, settings: Settings) -> "BrowserManager":
        instance = cls(settings)
        await instance.launch()
        return instance

    async def launch(self) -> None:
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.settings.browser_data_dir,
            headless=False,
            proxy={"server": self.settings.proxy_url},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        )
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()

    async def is_logged_in(
        self,
        *,
        timeout: int = 10_000,
    ) -> bool:
        if self.context is None:
            raise RuntimeError("请先调用 launch()")

        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        page = await self.context.new_page()
        target_url = self.settings.security_url.rstrip("/")

        # 访问 security 页面后，未登录状态会被站点重定向到其他页面。
        # 如果页面加载完成时 URL 已经变了，说明重定向已发生，判定为未登录。
        # 检测过程使用临时页面，避免把正在授权登录的主页面导航走。
        try:
            try:
                await page.goto(
                    self.settings.security_url,
                    wait_until="domcontentloaded",
                    timeout=timeout,
                )
            except PlaywrightTimeoutError:
                return False

            if page.url.rstrip("/") != target_url:
                return False

            # 如果当前仍停留在 security 页面，就继续等一小段时间。
            # 等到了 URL 变化，说明后续发生了重定向，判定为未登录；
            # 等到超时仍未跳转，则认为当前会话已登录。
            try:
                await page.wait_for_url(
                    lambda url: url.rstrip("/") != target_url,
                    timeout=timeout,
                )
                return False
            except PlaywrightTimeoutError:
                return True
        finally:
            await page.close()

    async def login(self, timeout: int = 10_000) -> bool:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        login_url = (
            await asyncio.to_thread(input, "当前未登录，请粘贴授权链接: ")
        ).strip()

        if not login_url:
            print("未输入授权链接")
            return False

        await self.page.goto(login_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(8000)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout / 1000

        while loop.time() < deadline:
            if await self.is_logged_in(timeout=3000):
                return True

            await self.page.wait_for_timeout(1000)

        return False

    async def goto_monitor_page(self) -> None:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        print(f"正在进入监听页: {self.settings.monitor_url}")
        await self.page.goto(self.settings.monitor_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)

    async def handle_popups(self) -> None:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        for _ in range(5):
            try:
                button = self.page.locator(
                    "button:has-text('Next'), "
                    "button:has-text('Complete'), "
                    "button:has-text('下一步'), "
                    "button:has-text('完成')"
                ).first

                if not await button.is_visible(timeout=1000):
                    break

                await button.click()
                await self.page.wait_for_timeout(500)
            except Exception:
                break

        try:
            await self.page.keyboard.press("Escape")
            await self.page.mouse.click(10, 10)
            await self.page.wait_for_timeout(1000)
        except Exception:
            pass

    async def switch_to_mine_tab(self) -> None:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        try:
            tab = self.page.locator("xpath=//*[text()='我的' or text()='Mine']").first
            if await tab.is_visible(timeout=2000):
                await tab.click()
                await self.page.wait_for_timeout(2000)
                return

            backup_tab = self.page.locator(
                "span:has-text('我的'), span:has-text('Mine')"
            ).first
            if await backup_tab.is_visible(timeout=2000):
                await backup_tab.click()
                await self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"切换 Mine 标签失败: {e}")

    async def recover_after_timeout(self) -> None:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        print("尝试刷新监听页并恢复 Mine 标签...")
        await self.page.reload(wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)
        await self.handle_popups()
        await self.switch_to_mine_tab()
        print("监听页恢复完成")

    def listen_gmgn_messages(
        self,
        handle_payload: Callable[[dict], None],
        feed_watchdog: Callable[[], None],
    ) -> None:
        if self.page is None:
            raise RuntimeError("请先调用 launch()")

        connected_ws = set()

        def handle_ws_frame(frame_data):
            feed_watchdog()
            parsed = parse_socketio_payload(frame_data)
            if parsed is None:
                return

            feed_watchdog()
            handle_payload(parsed)

        def on_web_socket(ws):
            if "gmgn.ai/ws" not in ws.url:
                return

            feed_watchdog()
            if ws.url not in connected_ws:
                connected_ws.add(ws.url)
                print(f"GMGN WS 已连接: {ws.url}")

            ws.on("framereceived", lambda frame: handle_ws_frame(frame))
            ws.on("close", lambda _: connected_ws.discard(ws.url))

        async def handle_http_response(response):
            try:
                if "gmgn.ai/ws" not in response.url:
                    return
                if "transport=polling" not in response.url:
                    return
                if response.status != 200:
                    return

                feed_watchdog()
                text = await response.text()
                if "twitter_user_monitor_basic" not in text:
                    return

                for message in iter_polling_messages(text):
                    parsed = parse_socketio_payload(message)
                    if parsed is not None:
                        feed_watchdog()
                        handle_payload(parsed)
            except Exception as e:
                print(f"Polling 响应解析跳过: {e}")

        self.page.on("websocket", on_web_socket)
        self.page.on("response", handle_http_response)

    async def close(self) -> None:
        if self.context is not None:
            await self.context.close()

        if self.playwright is not None:
            await self.playwright.stop()
