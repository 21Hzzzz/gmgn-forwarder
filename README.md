# gmgn-forwarder

`gmgn-forwarder` 是一个本地运行的 GMGN 动态监听和 Telegram 推送工具。它通过 Playwright 打开 GMGN follow 页面，监听页面里的 WebSocket / HTTP polling 数据，把 GMGN 返回的 Twitter/X 动态解析成标准消息，然后通过 Telegram Bot 推送到指定群组。

当前项目只做一件事：监听 GMGN 动态并推送到一个 Telegram 群组。

## 功能

- 持久化浏览器登录态，默认保存在 `browser_data/`。
- 未登录时在控制台请求粘贴 GMGN 授权链接。
- 同时监听 GMGN WebSocket 和 HTTP polling，降低重连间隙漏消息的概率。
- 解析 GMGN 的 `twitter_user_monitor_basic` 数据。
- 支持常见 Twitter/X 动作：发推、转推、回复、引用、关注、取关、删帖、换头像、改简介、改昵称、置顶、取消置顶。
- 使用 `cp=0/cp=1` 规则等待完整消息，避免快照版和完整版重复推送。
- Telegram outbox 持久化队列，发送失败或进程重启后会继续补发。
- dedup 历史持久化，重启后仍会跳过近期已处理消息。
- watchdog 超时检测，长时间无 GMGN 数据时自动刷新监听页。

## 环境要求

- Python `>=3.14`
- `uv`
- Playwright Chromium
- 可访问 GMGN 的代理
- Telegram Bot Token 和目标群组 ID

## 安装

```powershell
uv sync
uv run playwright install chromium
```

如果你的网络环境需要额外代理配置，可以参考 [warp-proxy.md](warp-proxy.md)。

## 配置

在项目根目录创建 `.env`：

```env
# Telegram
TG_BOT_TOKEN=123456:your_bot_token
TG_CHAT_ID=-1001234567890

# Network
PROXY_URL=http://127.0.0.1:42001

# GMGN
SECURITY_URL=https://gmgn.ai/security?chain=bsc
MONITOR_URL=https://gmgn.ai/follow?target=xTracker&chain=bsc

# Runtime state
STATE_DIR=state
BROWSER_DATA_DIR=browser_data
TG_OUTBOX_PATH=state/telegram_outbox.json
DEDUP_STATE_PATH=state/dedup_ids.json

# Watchdog
WATCHDOG_TIMEOUT=120
WATCHDOG_POLL_INTERVAL=5
```

### 配置说明

| 变量                     | 必填 | 默认值                                             | 说明                                 |
| ------------------------ | ---- | -------------------------------------------------- | ------------------------------------ |
| `TG_BOT_TOKEN`           | 是   | 空                                                 | Telegram Bot API token               |
| `TG_CHAT_ID`             | 是   | 空                                                 | Telegram 目标群组或频道 ID           |
| `PROXY_URL`              | 否   | `http://127.0.0.1:42001`                           | Playwright 浏览器代理                |
| `SECURITY_URL`           | 否   | `https://gmgn.ai/security?chain=bsc`               | 登录状态检测页面                     |
| `MONITOR_URL`            | 否   | `https://gmgn.ai/follow?target=xTracker&chain=bsc` | GMGN 监听页                          |
| `STATE_DIR`              | 否   | `state`                                            | 运行状态文件目录                     |
| `BROWSER_DATA_DIR`       | 否   | `browser_data`                                     | Playwright 持久化浏览器数据目录      |
| `TG_OUTBOX_PATH`         | 否   | `state/telegram_outbox.json`                       | Telegram 待发送/待重试消息队列       |
| `TG_FAILED_PATH`         | 否   | `state/failed_telegram.jsonl`                      | 旧失败队列迁移文件，通常不用手动配置 |
| `DEDUP_STATE_PATH`       | 否   | `state/dedup_ids.json`                             | 最近已处理 GMGN 消息 ID              |
| `TG_QUEUE_MAX`           | 否   | `1000`                                             | outbox 最大消息数，`0` 表示不限制    |
| `WATCHDOG_TIMEOUT`       | 否   | `120`                                              | watchdog 超时时间，单位秒            |
| `WATCHDOG_POLL_INTERVAL` | 否   | `5`                                                | watchdog 检查间隔，单位秒            |

## 运行

```powershell
uv run python main.py
```

首次运行时，如果检测到未登录，控制台会提示：

```text
当前未登录，请粘贴授权链接:
```

把 GMGN Bot 给你的授权登录链接粘贴进去。程序会打开该链接并等待 8 秒，让 GMGN 写入登录 cookie。登录成功后，会进入监听页并等待 GMGN 数据。

## 状态文件

这些目录和文件会在运行时生成，已经在 `.gitignore` 中忽略：

- `browser_data/`：浏览器登录态和 cookie。删除后需要重新登录。
- `state/telegram_outbox.json`：Telegram 待发送或待重试消息。文件里有消息表示还没成功发出。
- `state/dedup_ids.json`：最近处理过的 GMGN 内部消息 ID，用于重启后继续去重。
- `state/failed_telegram.jsonl`：旧失败队列兼容文件；启动时会迁移到 outbox。

不要把 `.env`、`browser_data/`、`state/` 提交到 GitHub。

## 可靠性说明

消息处理链路是：

```text
GMGN WS / polling -> parser -> deduplicator -> Telegram outbox -> Telegram Bot API
```

关键策略：

- `cp=0` 消息会先等待 500ms；如果 `cp=1` 完整版到达，则发送完整版。
- 如果 `cp=1` 没来，超时后发送 `cp=0` 快照版，避免漏消息。
- 消息成功写入 Telegram outbox 后，才会写入 dedup 历史。
- Telegram API 发送成功后，才会从 outbox 删除。
- 如果发送失败，消息会保留在 outbox 中并按退避延迟重试。

极端情况下，如果 Telegram 已经成功接收消息，但程序在删除 outbox 前崩溃，重启后可能重复推送一次。这个取舍保证优先不丢消息。

## 测试

项目测试使用 Python 标准库 `unittest`，不需要额外安装测试框架：

```powershell
python -m unittest discover -s tests -v
```

语法检查：

```powershell
python -m py_compile actions.py browser_manager.py settings.py gmgn_parser.py telegram_client.py telegram_formatter.py telegram_outbox.py telegram_sender.py main.py deduplicator.py models.py watchdog.py
```

## 常见问题

### Telegram 没收到消息

先检查：

- `.env` 中的 `TG_BOT_TOKEN` 和 `TG_CHAT_ID` 是否正确。
- Bot 是否已经加入目标群组。
- Bot 是否有发消息权限。
- `state/telegram_outbox.json` 是否有待发送消息。
- 控制台是否有 Telegram 限流、超时或网络异常日志。

### outbox 文件里有消息正常吗

正常。它表示这些消息还没有被 Telegram API 确认发送成功。网络恢复或下次运行时，程序会继续发送。

### 重启后会重复推送吗

一般不会。项目同时使用 outbox 消息 ID 和 `dedup_ids.json` 做去重。只有在 Telegram 已成功收消息、但程序还没来得及删除 outbox 就崩溃时，才可能重复一次。

### 删除 `browser_data/` 会怎样

会丢失 GMGN 登录态。下次启动时需要重新粘贴授权链接登录。

### 需要一直开着浏览器吗

需要。程序依赖 Playwright 打开真实浏览器页面来获取 GMGN 的页面内 WebSocket / polling 数据。

## 项目结构

```text
.
├── main.py                 # 程序入口
├── settings.py             # 环境变量配置
├── browser_manager.py      # Playwright 浏览器和监听页管理
├── gmgn_parser.py          # GMGN WS / polling 数据解析
├── models.py               # 标准消息数据结构
├── deduplicator.py         # cp 去重和 dedup 状态持久化
├── telegram_sender.py      # Telegram 推送协调器
├── telegram_outbox.py      # Telegram outbox 持久化队列
├── telegram_client.py      # Telegram Bot API client
├── telegram_formatter.py   # Telegram 消息格式化
├── actions.py              # 动作常量和文案
├── watchdog.py             # 超时检测
├── tests/                  # 单元测试
├── WS_DATA_FORMAT.md       # GMGN 数据格式说明
└── warp-proxy.md           # 可选代理配置说明
```
