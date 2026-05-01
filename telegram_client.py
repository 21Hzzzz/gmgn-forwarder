import asyncio

import aiohttp


class TelegramClient:
    def __init__(self, bot_token: str, *, timeout: int = 15) -> None:
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send_api(self, endpoint: str, payload: dict) -> dict | None:
        if self._session is None:
            return None

        for attempt in range(1, 4):
            try:
                async with self._session.post(
                    f"{self.api_base}/{endpoint}", json=payload
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()

                    if resp.status == 429:
                        data = await self._safe_json(resp)
                        retry_after = data.get("parameters", {}).get("retry_after", 5)
                        if attempt < 3:
                            print(f"Telegram 限流，{retry_after}s 后重试")
                            await asyncio.sleep(retry_after)
                            continue

                    body = await resp.text()
                    if resp.status >= 500 and attempt < 3:
                        delay = 2 ** (attempt - 1)
                        print(f"Telegram 服务端错误 [{resp.status}]，{delay}s 后重试")
                        await asyncio.sleep(delay)
                        continue

                    print(f"Telegram 推送失败 [{resp.status}]: {body[:200]}")
                    return None
            except asyncio.TimeoutError:
                if attempt < 3:
                    delay = 2 ** (attempt - 1)
                    print(f"Telegram 推送超时，{delay}s 后重试")
                    await asyncio.sleep(delay)
                    continue
                print("Telegram 推送超时")
                return None
            except aiohttp.ClientError as exc:
                if attempt < 3:
                    delay = 2 ** (attempt - 1)
                    print(f"Telegram 网络异常: {exc}，{delay}s 后重试")
                    await asyncio.sleep(delay)
                    continue
                print(f"Telegram 网络异常: {exc}")
                return None

        return None

    async def _safe_json(self, response: aiohttp.ClientResponse) -> dict:
        try:
            data = await response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
