import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    proxy_url: str
    security_url: str
    monitor_url: str
    browser_data_dir: str
    tg_bot_token: str
    tg_chat_id: str
    tg_queue_max: int
    tg_failed_path: str
    tg_outbox_path: str
    dedup_state_path: str
    watchdog_timeout: int
    watchdog_poll_interval: int
    xvfb_width: int
    xvfb_height: int


def load_settings() -> Settings:
    load_dotenv()
    state_dir = os.getenv("STATE_DIR", "state")
    return Settings(
        proxy_url=os.getenv("PROXY_URL", "http://127.0.0.1:42001"),
        security_url=os.getenv("SECURITY_URL", "https://gmgn.ai/security?chain=bsc"),
        monitor_url=os.getenv(
            "MONITOR_URL", "https://gmgn.ai/follow?target=xTracker&chain=bsc"
        ),
        browser_data_dir=os.getenv("BROWSER_DATA_DIR", "browser_data"),
        tg_bot_token=os.getenv("TG_BOT_TOKEN", ""),
        tg_chat_id=os.getenv("TG_CHAT_ID", ""),
        tg_queue_max=getenv_int("TG_QUEUE_MAX", 1000),
        tg_failed_path=os.getenv(
            "TG_FAILED_PATH", os.path.join(state_dir, "failed_telegram.jsonl")
        ),
        tg_outbox_path=os.getenv(
            "TG_OUTBOX_PATH", os.path.join(state_dir, "telegram_outbox.json")
        ),
        dedup_state_path=os.getenv(
            "DEDUP_STATE_PATH", os.path.join(state_dir, "dedup_ids.json")
        ),
        watchdog_timeout=getenv_int("WATCHDOG_TIMEOUT", 120),
        watchdog_poll_interval=getenv_int("WATCHDOG_POLL_INTERVAL", 5),
        xvfb_width=getenv_int("XVFB_WIDTH", 1920),
        xvfb_height=getenv_int("XVFB_HEIGHT", 1080),
    )


def getenv_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
