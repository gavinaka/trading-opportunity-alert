# 交易机会触发（预警）

这是 `Trading-System` 的只读变种项目。第一版只做 TradingView 事件驱动的 Taker 候选预警，不做 Maker 策略，不做报告交付，不做 Codex 定时轮询，也不自动抓取旧报告源。

## 当前边界

- `<REPO_ROOT>` 只能读取，禁止修改。
- TradingView 警报触发后，Webhook 只负责校验、脱敏、去重、落盘，并可发送 Telegram 候选提醒。
- 候选提醒不是交易信号。
- 不创建 Codex 自动化，不每分钟打开新窗口。
- 不自动抓取 BlockBeats、Coinglass、Exocharts、FedWatch 等旧报告源。
- 正式 Taker 预警必须经过一次明确的 Codex 二次判断：TV 结构确认、Taker 逻辑成立、置信度不低于 75%、风控通过。
- 公网接收器必须配置并轮换 `WEBHOOK_SECRET`；没有 secret 时启动脚本 fail-closed，不创建 Cloudflare Tunnel。
- 接收器采用原子去重、持久通知 outbox、损坏状态隔离和 heartbeat。`runtime_state/processes/event_receiver.json` 不能单独证明服务存活。
- JSON/JSONL 运行状态采用流式读取和硬容量上限；超过上限时以 `state_capacity_exceeded` 明确失败，禁止无界内存增长或静默丢弃历史。运行手册中的归档/压缩动作完成前不要强行重试。

## 第一版信号

- 突破确认
- 假突破 / 假跌破
- 流动性猎杀反转
- 2B 反转

2B 规则来自你的 Notion 记录与 `Trading-System` 只读依据：只接受 15m 以上级别，必须右侧确认，不做左侧猜顶/猜底，不在延伸末端追价。

## 正确链路

```text
每天 10:00 前：用户在 TradingView 设置当天关键位置警报
→ 每个警报携带计划ID、关键位、区间、失效参考和触发场景
→ 等待盘中价格行为触发
→ TradingView 警报
→ Webhook 接收
→ 校验、脱敏、去重、落盘
→ Telegram 候选提醒
→ 用户明确要求 Codex 分析该候选
→ Codex 单次读取 TV 候选与只读规则
→ 判断是否发送正式 Taker 预警或给出不触发原因
```

## 盘中处理链路

```text
TradingView 警报
→ Webhook 接收
→ 校验、脱敏、去重、落盘
→ Telegram 候选提醒
→ 用户明确要求 Codex 分析该候选
→ Codex 单次读取 TV 候选与只读规则
→ 判断是否发送正式 Taker 预警
```

## 启动 / 停止事件接收器

启动：

```powershell
cd "<REPO_ROOT>"
.\tools\start_event_receiver.ps1 -NotifyCandidates
```

停止：

```powershell
.\tools\stop_event_receiver.ps1
```

启动脚本只启动本地 Webhook 和 Cloudflare Tunnel，不会创建 Codex 自动化。

状态检查：

```powershell
.\tools\event_receiver_status.ps1
```

只有进程、`/health` 和30秒内 heartbeat 同时通过才返回 `healthy`。

## TradingView 消息

TradingView 的消息框请填写中文 JSON，不要填写自由文本。模板见：

- [TradingView 警报消息填写](docs/tradingview_alert_messages.md)

## 质量检查

```powershell
.\tools\quality_gate.ps1
```

## 关键文档

- [事件驱动设计](docs/event_driven_design.md)
- [Taker 候选分析提示词](docs/codex_taker_event_prompt.md)
- [运行手册](docs/runbook.md)
- [质量门禁](docs/quality.md)

> Publication note: sensitive literals and machine-specific paths were generalized for review.
