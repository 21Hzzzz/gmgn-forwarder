import html
from datetime import datetime, timedelta, timezone
from typing import Any

from actions import ACTION_TEXT, FOLLOW_ACTIONS, REFERENCE_PREFIX, TWEET_PREVIEW_ACTIONS


class TelegramFormatter:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    def build_send_message_payload(self, msg: dict) -> dict:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": self.format_message(msg)[:4096],
            "parse_mode": "HTML",
        }

        preview_url = self.preview_link(msg)
        if preview_url:
            payload["link_preview_options"] = {
                "is_disabled": False,
                "prefer_large_media": True,
                "url": preview_url,
            }

        return payload

    def build_photo_change_payload(self, message: dict) -> dict | None:
        avatar_change = message.get("avatar_change") or {}
        before_url = avatar_change.get("before")
        after_url = avatar_change.get("after")
        if not before_url or not after_url:
            return None

        caption = self.format_message(message, include_link=False)[:1024]
        return {
            "chat_id": self.chat_id,
            "media": [
                {
                    "type": "photo",
                    "media": before_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                {
                    "type": "photo",
                    "media": after_url,
                },
            ],
        }

    def format_message(self, msg: dict, *, include_link: bool = True) -> str:
        action = msg.get("action", "unknown")
        author = msg.get("author") or {}
        handle = author.get("handle") or "unknown"
        name = self._escape(author.get("name") or handle)
        followers = self._format_followers(author.get("followers"))
        action_text = self.action_text(action)

        lines = [
            f"<b>{action_text}</b>",
            f'👤 <a href="https://x.com/{self._escape_attr(handle)}">{name} @{self._escape(handle)}</a>{followers}',
        ]

        if action in FOLLOW_ACTIONS and msg.get("unfollow_target"):
            target = msg["unfollow_target"]
            target_handle = target.get("handle") or "unknown"
            target_name = self._escape(target.get("name") or target_handle)
            target_followers = self._format_followers(target.get("followers"))
            verb = "✅ 关注了" if action == "follow" else "❌ 取关了"
            lines.append(
                f'{verb} <a href="https://x.com/{self._escape_attr(target_handle)}">'
                f"{target_name} @{self._escape(target_handle)}</a>{target_followers}"
            )
        else:
            self._append_reference(lines, msg)
            self._append_content(lines, msg)
            self._append_profile_change(lines, msg)

        timestamp = msg.get("timestamp") or 0
        lines.append("")
        lines.append(f"🕒 推文时间: {self._format_timestamp(timestamp)}")

        link = self.preview_link(msg)
        if include_link and link:
            lines.append(f'🔗 <a href="{self._escape_attr(link)}">打开原文</a>')

        return "\n".join(lines)

    def _append_reference(self, lines: list[str], msg: dict) -> None:
        action = msg.get("action")
        reference = msg.get("reference") or {}
        ref_handle = reference.get("author_handle")
        if not ref_handle:
            return

        ref_name = self._escape(reference.get("author_name") or ref_handle)
        ref_followers = self._format_followers(reference.get("author_followers"))
        prefix = REFERENCE_PREFIX.get(action, "➡️ 指向")
        lines.append(
            f'{prefix} <a href="https://x.com/{self._escape_attr(ref_handle)}">'
            f"{ref_name} @{self._escape(ref_handle)}</a>{ref_followers}"
        )

        ref_text = reference.get("text")
        if ref_text:
            lines.append("")
            lines.append(f"<blockquote>{self._escape(ref_text)}</blockquote>")

    def _append_content(self, lines: list[str], msg: dict) -> None:
        content = msg.get("content") or {}
        text = content.get("text")
        if text:
            lines.append("")
            lines.append(self._escape(text))

        if msg.get("action") == "delete_post" and msg.get("original_action"):
            lines.append(f"原类型: {self._escape(str(msg['original_action']))}")

    def _append_profile_change(self, lines: list[str], msg: dict) -> None:
        action = msg.get("action")
        if action == "photo" and msg.get("avatar_change"):
            change = msg["avatar_change"]
            before = change.get("before")
            after = change.get("after")
            if before:
                lines.append(f'旧头像: <a href="{self._escape_attr(before)}">查看</a>')
            if after:
                lines.append(f'新头像: <a href="{self._escape_attr(after)}">查看</a>')

        if action == "description" and msg.get("bio_change"):
            change = msg["bio_change"]
            lines.append("")
            lines.append("<b>旧简介</b>")
            lines.append(self._escape(change.get("before") or ""))
            lines.append("<b>新简介</b>")
            lines.append(self._escape(change.get("after") or ""))

    def preview_link(self, msg: dict) -> str | None:
        action = msg.get("action")
        author = msg.get("author") or {}
        handle = author.get("handle")
        tweet_id = msg.get("tweet_id")

        if action in TWEET_PREVIEW_ACTIONS and handle and tweet_id:
            return f"https://fxtwitter.com/{handle}/status/{tweet_id}"

        if action == "repost":
            reference = msg.get("reference") or {}
            ref_handle = reference.get("author_handle")
            ref_tweet_id = reference.get("tweet_id")
            if ref_handle and ref_tweet_id:
                return f"https://fxtwitter.com/{ref_handle}/status/{ref_tweet_id}"
            if handle and tweet_id:
                return f"https://fxtwitter.com/{handle}/status/{tweet_id}"

        if action in FOLLOW_ACTIONS:
            target = msg.get("unfollow_target") or {}
            target_handle = target.get("handle")
            return f"https://vxtwitter.com/{target_handle}" if target_handle else None

        if handle and action not in ("delete_post",):
            return f"https://vxtwitter.com/{handle}"

        return None

    @staticmethod
    def action_text(action: str) -> str:
        return ACTION_TEXT.get(action, f"❓ {action}")

    @staticmethod
    def _format_followers(count: int | None) -> str:
        if not count:
            return ""
        if count >= 1_000_000:
            return f" · {count / 1_000_000:.1f}M 粉丝"
        if count >= 1_000:
            return f" · {count / 1_000:.1f}K 粉丝"
        return f" · {count} 粉丝"

    @staticmethod
    def _format_timestamp(timestamp: int) -> str:
        if not timestamp:
            return "未知"
        tz_cst = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(timestamp, tz=tz_cst).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _escape(value: object) -> str:
        return html.escape(str(value), quote=False)

    @staticmethod
    def _escape_attr(value: object) -> str:
        return html.escape(str(value), quote=True)
