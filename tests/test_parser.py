import json
import unittest

from gmgn_parser import build_standardized_message, iter_polling_messages, parse_socketio_payload


class ParserTests(unittest.TestCase):
    def test_parse_socketio_payload(self) -> None:
        payload = {
            "channel": "twitter_user_monitor_basic",
            "data": [{"tw": "tweet", "u": {"s": "solana"}}],
        }
        frame = f'42["message",{json.dumps(payload)}]'

        parsed = parse_socketio_payload(frame)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["channel"], "twitter_user_monitor_basic")
        self.assertEqual(parsed["data"][0]["u"]["s"], "solana")

    def test_iter_polling_messages(self) -> None:
        first = '42["message",{"channel":"twitter_user_monitor_basic","data":[]}]'
        second = '42["message",{"channel":"twitter_user_monitor_basic","data":[{"tw":"pin"}]}]'
        payload = f"{len(first)}:{first}{len(second)}:{second}"

        self.assertEqual(iter_polling_messages(payload), [first, second])

    def test_build_standardized_pin_message(self) -> None:
        message = build_standardized_message(
            {
                "tw": "pin",
                "i": "internal-1",
                "ti": "tweet-1",
                "ts": 1_700_000_000_000,
                "u": {"s": "solana", "n": "Solana", "f": 1000},
                "c": {"t": "Pinned text"},
            }
        )

        self.assertEqual(message.action, "pin")
        self.assertEqual(message.tweet_id, "tweet-1")
        self.assertEqual(message.timestamp, 1_700_000_000)
        self.assertEqual(message.author.handle, "solana")


if __name__ == "__main__":
    unittest.main()
