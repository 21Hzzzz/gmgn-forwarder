import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from telegram_formatter import TelegramFormatter
from telegram_outbox import TelegramOutbox


def test_dir() -> Path:
    path = Path("state") / "tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def sample_message(internal_id: str = "id-1") -> dict:
    return {
        "internal_id": internal_id,
        "action": "tweet",
        "tweet_id": "tweet-1",
        "timestamp": 0,
        "author": {"handle": "solana", "name": "Solana"},
        "content": {"text": "hello"},
    }


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


class TelegramOutboxTests(unittest.TestCase):
    def test_add_is_idempotent_and_persistent(self) -> None:
        root = test_dir()
        try:
            path = root / "outbox.json"
            outbox = TelegramOutbox(path)
            self.assertEqual(outbox.load(), 0)

            self.assertTrue(outbox.add(sample_message()))
            self.assertTrue(outbox.add(sample_message()))

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(data["messages"]), ["id-1"])

            reloaded = TelegramOutbox(path)
            reloaded.load()
            self.assertIn("id-1", reloaded.messages)
        finally:
            cleanup_test_dir(root)

    def test_failed_jsonl_migration(self) -> None:
        root = test_dir()
        try:
            outbox_path = root / "outbox.json"
            failed_path = root / "failed.jsonl"
            failed_path.write_text(
                json.dumps(sample_message("legacy-1"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            outbox = TelegramOutbox(outbox_path, failed_path=failed_path)
            migrated = outbox.load()

            self.assertEqual(migrated, 1)
            self.assertIn("legacy-1", outbox.messages)
            self.assertFalse(failed_path.exists())
        finally:
            cleanup_test_dir(root)

    def test_mark_failed_and_remove(self) -> None:
        root = test_dir()
        try:
            outbox = TelegramOutbox(root / "outbox.json")
            outbox.load()
            outbox.add(sample_message())

            self.assertTrue(outbox.mark_failed("id-1", delay=1, error="failed"))
            self.assertEqual(outbox.messages["id-1"]["attempts"], 1)
            self.assertEqual(outbox.messages["id-1"]["last_error"], "failed")

            self.assertTrue(outbox.remove("id-1"))
            self.assertEqual(outbox.messages, {})
        finally:
            cleanup_test_dir(root)


class TelegramFormatterTests(unittest.TestCase):
    def test_pin_and_unpin_text_and_preview(self) -> None:
        formatter = TelegramFormatter("-100")
        message = sample_message()
        message["action"] = "unpin"

        self.assertEqual(formatter.action_text("pin"), "📌 置顶推文")
        self.assertEqual(formatter.action_text("unpin"), "📍 取消置顶")
        self.assertEqual(
            formatter.preview_link(message),
            "https://fxtwitter.com/solana/status/tweet-1",
        )


if __name__ == "__main__":
    unittest.main()
