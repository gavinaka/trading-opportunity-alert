# 运行手册

当前第一版是 TradingView 事件驱动的 Taker 候选预警，不使用 Codex cron 自动化，不做 Maker 策略，不做小时级轮询。

## 每天早盘设置

每天 10:00 前，在 TradingView 为当天关键位置设置警报。每个警报必须包含：

- 计划ID
- 位置名称
- 关键位
- 区间下沿
- 区间上沿
- 失效参考
- 触发场景
- 信号、方向、周期、价格、时间

模板见 `docs/tradingview_alert_messages.md`。

同一 `计划ID + 信号 + 方向 + 周期` 的重复触发会被去重。若同一关键位置后来需要重新启用，请新建一个新的计划ID。

## 启动事件接收器

```powershell
cd "<REPO_ROOT>"
.\tools\start_event_receiver.ps1 -NotifyCandidates
```

## 停止事件接收器

```powershell
.\tools\stop_event_receiver.ps1
```

## Telegram 测试

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json send-test --text "Taker alert receiver test"
```

## 手动检查候选队列

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json next-taker-candidate
```

## 手动准备 Taker 分析包

只有当你明确要求 Codex 分析某个候选事件时才运行：

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json prepare-taker-analysis --event-hash <event_hash>
```

该命令只读取 TradingView 候选和规则，不会自动抓取外部源。

## 正式预警发送

先写入正式中文消息文件，再校验：

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json validate-taker-message --message <message_file>
```

校验通过且二次判断满足硬条件时发送：

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json send-taker-message --message <message_file> --send --signal <signal> --direction <long|short> --event-hash <event_hash>
```

## 禁止事项

- 禁止创建 Codex 每分钟自动化来轮询候选队列。
- 禁止在 Webhook 收到候选后自动调用 Codex。
- 禁止在 Webhook 收到候选后自动抓取外部源。
- 禁止用旧 Maker 命令发送 Telegram。
- 禁止修改 `<REPO_ROOT>`。

> Publication note: sensitive literals and machine-specific paths were generalized for review.
