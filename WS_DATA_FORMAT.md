# GMGN WebSocket 数据格式说明

本文档说明当前项目监听 GMGN 页面 WebSocket 时会看到的数据层次，以及参考项目 `abcd` 中解析器做了什么工作。`abcd/` 仅作为只读参考，不需要在里面改代码。

## 1. WebSocket 外层格式

GMGN 页面建立的 WebSocket URL 通常包含：

```text
gmgn.ai/ws
```

Playwright 可以通过：

```python
page.on("websocket", on_web_socket)
ws.on("framereceived", handle_ws_frame)
```

拿到每一帧数据。这里拿到的 `frame_data` 不是业务 JSON 本体，而是 Socket.IO / Engine.IO 包。

典型帧长这样：

```text
42["message","{\"channel\":\"twitter_user_monitor_basic\",\"data\":[...]}"]
```

可以分三层理解：

| 层级           | 示例                                                    | 含义                                       |
| -------------- | ------------------------------------------------------- | ------------------------------------------ |
| Socket.IO 前缀 | `42`                                                    | 表示这是 Socket.IO event message           |
| 事件数组       | `["message", "..."]`                                    | 事件名是 `message`，第二项才是业务 payload |
| GMGN payload   | `{"channel":"twitter_user_monitor_basic","data":[...]}` | 真正的 GMGN 业务数据                       |

因此解析时要先去掉前导数字，再 `json.loads()`。第一次解析后通常得到一个 list，取第二项；第二项经常还是 JSON 字符串，需要再解析一次。

## 2. GMGN 业务 payload 格式

解析完成后，目标结构大致是：

```json
{
  "channel": "twitter_user_monitor_basic",
  "data": [
    {
      "tw": "tweet",
      "i": "internal-message-id",
      "ti": "twitter-tweet-id",
      "ts": 1712300000000,
      "u": {},
      "c": {}
    }
  ]
}
```

只有 `channel == "twitter_user_monitor_basic"` 的数据才是当前要处理的 Twitter 监控消息。

`data` 是数组，一帧里可能有一条或多条 Twitter 动作记录。每个元素称为一个 `item`。

## 3. item 常见字段

| 字段  | 含义                                                                     |
| ----- | ------------------------------------------------------------------------ |
| `tw`  | 动作类型，例如 `tweet`、`repost`、`reply`、`quote`、`follow`、`unfollow`、`pin`、`unpin` |
| `stw` | 原始动作类型，主要用于 `delete_post`                                     |
| `i`   | GMGN 内部消息 ID，后续去重用                                             |
| `cp`  | 消息完整度标记，参考项目用它做快照版/完整版去重                          |
| `ti`  | Twitter tweet id                                                         |
| `ts`  | 时间戳，GMGN 可能给毫秒级                                                |
| `ut`  | 作者标签数组                                                             |
| `u`   | 当前动作的作者信息                                                       |
| `c`   | 当前动作的正文内容                                                       |
| `si`  | 被引用、回复、转推、删除的 tweet id                                      |
| `su`  | 被引用、回复、转推、删除的作者信息                                       |
| `sc`  | 被引用、回复、转推、删除的正文内容                                       |
| `f`   | follow / unfollow 的目标信息                                             |
| `p`   | 头像或简介变更信息                                                       |

## 4. 用户、正文、媒体字段

`u` 表示作者：

```json
{
  "s": "handle",
  "n": "display name",
  "a": "avatar url",
  "f": 123456
}
```

字段含义：

| 字段 | 标准化后含义 |
| ---- | ------------ |
| `s`  | `handle`     |
| `n`  | `name`       |
| `a`  | `avatar`     |
| `f`  | `followers`  |

`c` 表示正文内容：

```json
{
  "t": "tweet text",
  "m": [{ "t": "photo", "u": "media url" }]
}
```

字段含义：

| 字段    | 标准化后含义 |
| ------- | ------------ |
| `t`     | 正文文本     |
| `m`     | 媒体列表     |
| `m[].t` | 媒体类型     |
| `m[].u` | 媒体 URL     |

## 5. 引用、回复、转推相关字段

当动作是 `repost`、`reply`、`quote`、`delete_post` 时，可能会出现：

```json
{
  "si": "referenced tweet id",
  "su": {
    "s": "referenced_author",
    "n": "Referenced Author",
    "a": "avatar url",
    "f": 10000
  },
  "sc": {
    "t": "referenced tweet text",
    "m": []
  }
}
```

`abcd` 解析器会把它们整理成 `reference`：

| 原字段 | 标准化字段                   |
| ------ | ---------------------------- |
| `si`   | `reference.tweet_id`         |
| `su.s` | `reference.author_handle`    |
| `su.n` | `reference.author_name`      |
| `su.a` | `reference.author_avatar`    |
| `su.f` | `reference.author_followers` |
| `sc.t` | `reference.text`             |
| `sc.m` | `reference.media`            |

`reference.type` 会根据动作类型映射：

| `tw`          | `reference.type` |
| ------------- | ---------------- |
| `repost`      | `retweeted`      |
| `reply`       | `replied_to`     |
| `quote`       | `quoted`         |
| `delete_post` | `deleted`        |

## 6. follow / unfollow 相关字段

`follow` 和 `unfollow` 的目标信息在 `f.f` 里：

```json
{
  "tw": "follow",
  "f": {
    "f": {
      "s": "target_handle",
      "n": "Target Name",
      "d": "target bio",
      "a": "avatar url",
      "f": 12345
    }
  }
}
```

`abcd` 解析器会整理成 `unfollow_target`。虽然字段名叫 `unfollow_target`，但它同时用于 `follow` 和 `unfollow`。

## 7. 头像和简介变更字段

头像变更动作 `photo` 使用 `p`：

```json
{
  "tw": "photo",
  "p": {
    "ba": "before avatar url",
    "aa": "after avatar url"
  }
}
```

标准化后：

| 原字段 | 标准化字段             |
| ------ | ---------------------- |
| `p.ba` | `avatar_change.before` |
| `p.aa` | `avatar_change.after`  |

简介变更动作 `description` 也使用 `p`：

```json
{
  "tw": "description",
  "p": {
    "bd": "before bio",
    "d": "after bio"
  }
}
```

标准化后：

| 原字段 | 标准化字段          |
| ------ | ------------------- |
| `p.bd` | `bio_change.before` |
| `p.d`  | `bio_change.after`  |

## 8. abcd 解析器做的工作

参考文件：

```text
abcd/gmgn_twitter_monitor/parser.py
abcd/gmgn_twitter_monitor/models.py
```

它主要做三件事。

第一步：过滤和拆 Socket.IO 包。

`parse_socketio_payload(frame_data)` 的职责：

1. 确认 `frame_data` 是字符串。
2. 确认里面包含 `twitter_user_monitor_basic`。
3. 去掉前导数字，例如 `42`。
4. 第一次 `json.loads()`，把 Socket.IO 事件数组解析出来。
5. 如果解析结果是 list，就取第二项业务 payload。
6. 如果第二项还是字符串，再 `json.loads()` 一次。
7. 确认 `channel == "twitter_user_monitor_basic"`。
8. 确认 `data` 是 list。
9. 返回解析后的 dict。

第二步：提取简报。

`extract_triggers_map(items)` 会从每个 item 里取：

```text
u.s -> twitter handle
tw  -> action type
```

输出类似：

```json
{
  "cz_binance": "tweet",
  "elonmusk": "reply"
}
```

这个函数只用于日志简报，不负责完整解析。

第三步：标准化 item。

`build_standardized_message(item)` 会把 GMGN 的短字段整理成更容易读、更适合分发的结构：

```json
{
  "action": "tweet",
  "original_action": null,
  "tweet_id": "123",
  "internal_id": "abc",
  "timestamp": 1712300000,
  "author": {},
  "content": {},
  "reference": null,
  "unfollow_target": null,
  "avatar_change": null,
  "bio_change": null
}
```

它会额外处理：

| 工作              | 说明                                                       |
| ----------------- | ---------------------------------------------------------- |
| 作者标准化        | `u.s/u.n/u.a/u.f` -> `author.handle/name/avatar/followers` |
| 正文标准化        | `c.t/c.m` -> `content.text/media`                          |
| 媒体标准化        | `m[].t/m[].u` -> `media.type/url`                          |
| 引用标准化        | `si/su/sc` -> `reference`                                  |
| follow 目标标准化 | `f.f` -> `unfollow_target`                                 |
| 头像变更标准化    | `p.ba/p.aa` -> `avatar_change`                             |
| 简介变更标准化    | `p.bd/p.d` -> `bio_change`                                 |
| 时间戳标准化      | 毫秒级时间戳会转换成秒级                                   |

## 9. 解析器不做的工作

`abcd` 的解析器只负责“把原始数据变成结构化数据”。它不负责：

| 工作                                | 所在位置                            |
| ----------------------------------- | ----------------------------------- |
| 监听 WebSocket                      | `app.py`                            |
| 监听 HTTP polling 降级响应          | `app.py`                            |
| `cp=0/cp=1` 去重                    | `app.py` 里的 `MessageDeduplicator` |
| Telegram / Webhook / WebSocket 分发 | `distributor.py`                    |
| DeepSeek 翻译                       | `translator.py`                     |
| 页面超时刷新                        | `watchdog.py`                       |

所以自己实现时建议按这个顺序拆：

1. `parse_socketio_payload()`：先把 WS 原始字符串解析成 dict。
2. `build_standardized_message()`：再把每个 item 变成标准结构。
3. `MessageDeduplicator`：最后再处理 `cp=0/cp=1` 的重复消息。
