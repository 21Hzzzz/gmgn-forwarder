ACTION_TEXT = {
    "tweet": "📝 发布新推文",
    "repost": "🔁 转推",
    "reply": "💬 回复",
    "quote": "📌 引用推文",
    "pin": "📌 置顶推文",
    "unpin": "📍 取消置顶",
    "follow": "✅ 新增关注",
    "unfollow": "❌ 取消关注",
    "delete_post": "🗑️ 删除推文",
    "photo": "🖼️ 更换头像",
    "description": "📄 简介更新",
    "name": "📛 更改昵称",
}

REFERENCE_PREFIX = {
    "repost": "🔁 转推了",
    "reply": "💬 回复了",
    "quote": "📌 引用了",
}

REFERENCE_TYPE = {
    "repost": "retweeted",
    "reply": "replied_to",
    "quote": "quoted",
    "delete_post": "deleted",
}

TWEET_PREVIEW_ACTIONS = frozenset({"tweet", "reply", "quote", "pin", "unpin"})
FOLLOW_ACTIONS = frozenset({"follow", "unfollow"})
