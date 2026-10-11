# 质量门禁

## 工程目标

- TradingView webhook 必须快速响应，避免同步外部调用拖慢接收。
- 候选事件必须结构化、校验、去重、脱敏后落盘。
- Telegram 候选提醒必须标注“非交易信号”。
- 正式 Taker 预警必须通过格式、置信度和风控字段校验。
- `Trading-System` 只能读取，不能被新项目写入。
- 生产路径不能暴露旧抓取入口、Maker 发送入口或 Codex 定时轮询入口。

## 运行

```powershell
cd "<REPO_ROOT>"
.\tools\quality_gate.ps1
```

## 当前覆盖

- Python 编译检查。
- 单元测试。
- Taker 候选事件解析。
- 中文 TV payload 解析。
- 2B 反转 alias 解析。
- 非法价格拒收。
- 候选通知文案检查。
- 正式 Taker 消息格式校验。
- 正式 Taker dry-run 发送路径。
- TV-only Taker 分析包生成。
- 候选事件队列状态标记。
- 旧 Maker / OpenAI / cron / 抓取入口扫描。
- `Trading-System` git 状态只读观察。

## 不能承诺

- 不能承诺市场判断 100% 正确。
- 不能承诺第三方服务 100% 可用，例如 TradingView、Cloudflare、Telegram。
- 不能在关键位不成立、2B 未完成、风控字段不完整、止损过宽或盈亏比不足时发送正式预警。

> Publication note: sensitive literals and machine-specific paths were generalized for review.
