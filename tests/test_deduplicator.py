import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from deduplicator import MessageDeduplicator


def test_dir() -> Path:
    path = Path("state") / "tests" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_item(internal_id: str, *, cp: int, text: str) -> dict:
    return {
        "i": internal_id,
        "cp": cp,
        "tw": "tweet",
        "ti": "tweet-1",
        "ts": 0,
        "u": {"s": "solana", "n": "Solana"},
        "c": {"t": text},
    }


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


class DeduplicatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_success_marks_history(self) -> None:
        root = test_dir()
        try:
            state_path = root / "dedup.json"

            async def publish(_: dict) -> bool:
                return True

            dedup = MessageDeduplicator(publish, state_path=state_path)
            dedup.process(raw_item("id-1", cp=1, text="full"))
            await dedup.close()

            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), ["id-1"])
            self.assertIn("id-1", dedup._processed_ids)
        finally:
            cleanup_test_dir(root)

    async def test_publish_failure_does_not_mark_history(self) -> None:
        root = test_dir()
        try:
            state_path = root / "dedup.json"

            async def publish(_: dict) -> bool:
                return False

            dedup = MessageDeduplicator(publish, state_path=state_path)
            dedup.process(raw_item("id-1", cp=1, text="full"))
            await dedup.close()

            self.assertNotIn("id-1", dedup._processed_ids)
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), [])
        finally:
            cleanup_test_dir(root)

    async def test_cp1_replaces_pending_cp0(self) -> None:
        root = test_dir()
        try:
            published: list[dict] = []

            async def publish(message: dict) -> bool:
                published.append(message)
                return True

            dedup = MessageDeduplicator(publish, state_path=root / "dedup.json")
            dedup.process(raw_item("id-1", cp=0, text="snapshot"))
            dedup.process(raw_item("id-1", cp=1, text="full"))
            await dedup.close()

            self.assertEqual(len(published), 1)
            self.assertEqual(published[0]["content"]["text"], "full")
        finally:
            cleanup_test_dir(root)


if __name__ == "__main__":
    unittest.main()
