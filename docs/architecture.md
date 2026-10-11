# TV-only Taker 预警架构

## 目标

在不修改 `Trading-System` 的前提下，把 TradingView 警报转换为 Taker 候选事件，并在用户明确要求时执行一次 Codex 二次判断。

## 核心原则

- 触发源只来自 TradingView webhook。
- Webhook 只接收候选，不发送正式交易信号。
- Codex 不通过定时自动化轮询候选。
- `Trading-System` 只读，用作规则和历史边界来源。
- Telegram 候选提醒必须标明“非交易信号”。

## 组件

1. TradingView 警报  
   发送固定 JSON 到 Webhook。

2. Webhook 接收器  
   解析、校验、脱敏、去重、保存候选事件。

3. Telegram 候选提醒  
   快速提示“候选已收到”，不包含入场建议。

4. Codex 二次判断  
   用户明确要求后，读取候选事件、规则包和只读依据，判断是否满足正式 Taker 预警条件。

5. Telegram 正式预警  
   只有格式校验、置信度阈值和风控字段全部通过时才发送。

## 不使用旧链路的原因

旧报告链路适合定时综合分析，不适合 Taker 的短时触发。第一版不自动拉取旧报告源，不运行旧抓取脚本，不生成 Maker 报告。

## 生产边界

- 接收器可以长期运行。
- Codex 分析必须是单次显式动作。
- Cloudflare trycloudflare URL 是临时隧道地址，重启后可能变化。
- 正式生产可改成固定域名或 Cloudflare named tunnel，但不改变事件驱动原则。
