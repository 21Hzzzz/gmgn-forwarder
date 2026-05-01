import json
from typing import Any

from actions import REFERENCE_TYPE
from models import (
    Author,
    AvatarChange,
    BioChange,
    Content,
    Media,
    Reference,
    StandardizedMessage,
    UnfollowTarget,
)


def parse_socketio_payload(frame_data: Any) -> dict | None:
    if not isinstance(frame_data, str):
        return None

    if "twitter_user_monitor_basic" not in frame_data:
        return None

    payload = _strip_socketio_prefix(frame_data)
    if not payload:
        return None

    parsed = _loads_json(payload)
    if parsed is None:
        return None

    if isinstance(parsed, list) and len(parsed) >= 2:
        parsed = parsed[1]

    if isinstance(parsed, str):
        parsed = _loads_json(parsed)

    if not isinstance(parsed, dict):
        return None

    if parsed.get("channel") != "twitter_user_monitor_basic":
        return None

    if not isinstance(parsed.get("data"), list):
        return None

    return parsed


def extract_triggers_map(items: list[dict]) -> dict[str, str]:
    triggers: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        author = item.get("u")
        if not isinstance(author, dict):
            continue

        handle = author.get("s")
        if handle:
            triggers[handle] = item.get("tw", "unknown")

    return triggers


def iter_polling_messages(text: str) -> list[str]:
    messages: list[str] = []
    parts = text.split("\x1e") if "\x1e" in text else [text]

    for part in parts:
        index = 0
        while index < len(part):
            colon_index = part.find(":", index)
            if colon_index == -1:
                if part[index:].startswith("42"):
                    messages.append(part[index:])
                break

            length_text = part[index:colon_index]
            if not length_text.isdigit():
                if part[index:].startswith("42"):
                    messages.append(part[index:])
                break

            message_length = int(length_text)
            message_start = colon_index + 1
            message_end = message_start + message_length
            if message_end > len(part):
                break

            message = part[message_start:message_end]
            if message.startswith("42"):
                messages.append(message)

            index = message_end

    return messages


def build_standardized_message(item: dict) -> StandardizedMessage:
    action = item.get("tw", "unknown")
    author_data = _safe_dict(item.get("u"))
    content_data = _safe_dict(item.get("c"))

    timestamp = _normalize_timestamp(item.get("ts"))

    return StandardizedMessage(
        action=action,
        original_action=item.get("stw"),
        tweet_id=item.get("ti"),
        internal_id=item.get("i"),
        timestamp=timestamp,
        author=Author(
            handle=author_data.get("s"),
            name=author_data.get("n"),
            avatar=author_data.get("a"),
            followers=author_data.get("f"),
            tags=item.get("ut", []) if isinstance(item.get("ut"), list) else [],
        ),
        content=Content(
            text=content_data.get("t"),
            media=_build_media_list(content_data.get("m")),
        ),
        reference=_build_reference(item, action),
        unfollow_target=_build_unfollow_target(item) if action in ("follow", "unfollow") else None,
        avatar_change=_build_avatar_change(item) if action == "photo" else None,
        bio_change=_build_bio_change(item) if action == "description" else None,
    )


def _strip_socketio_prefix(frame_data: str) -> str:
    for index, char in enumerate(frame_data):
        if char in "[{":
            return frame_data[index:]
    return ""


def _loads_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _build_media_list(raw_media: Any) -> list[Media]:
    if not isinstance(raw_media, list):
        return []

    media: list[Media] = []
    for item in raw_media:
        if not isinstance(item, dict):
            continue
        media.append(Media(type=item.get("t"), url=item.get("u")))

    return media


def _build_reference(item: dict, action: str) -> Reference | None:
    if "su" not in item:
        return None

    author = _safe_dict(item.get("su"))
    content = _safe_dict(item.get("sc"))
    reference_type = REFERENCE_TYPE.get(action, "referenced")

    return Reference(
        tweet_id=item.get("si"),
        author_handle=author.get("s"),
        author_name=author.get("n"),
        author_avatar=author.get("a"),
        author_followers=author.get("f"),
        text=content.get("t"),
        media=_build_media_list(content.get("m")),
        type=reference_type,
    )


def _build_unfollow_target(item: dict) -> UnfollowTarget | None:
    follow_data = _safe_dict(item.get("f"))
    target = _safe_dict(follow_data.get("f"))
    if not target:
        return None

    return UnfollowTarget(
        handle=target.get("s"),
        name=target.get("n"),
        bio=target.get("d"),
        avatar=target.get("a"),
        followers=target.get("f"),
    )


def _build_avatar_change(item: dict) -> AvatarChange | None:
    data = _safe_dict(item.get("p"))
    if not data:
        return None

    return AvatarChange(before=data.get("ba"), after=data.get("aa"))


def _build_bio_change(item: dict) -> BioChange | None:
    data = _safe_dict(item.get("p"))
    if not data:
        return None

    return BioChange(before=data.get("bd"), after=data.get("d"))


def _normalize_timestamp(value: Any) -> int:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return 0

    return timestamp // 1000 if timestamp > 9_999_999_999 else timestamp
