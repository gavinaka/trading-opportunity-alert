# Codex Taker 候选事件分析提示词

在 `<REPO_ROOT>` 执行 Taker 候选事件二次判断。

## 硬边界

- `<REPO_ROOT>` 只能读取，禁止写入、修改、格式化、提交或运行会改变原库状态的命令。
- TradingView webhook 事件只是候选，不是交易信号。
- 第一版正式信号只允许：突破确认、假突破、假跌破、流动性猎杀反转、2B反转。
- 第一版只使用 TradingView 事件数据和只读规则，不自动抓取旧报告源。
- 不生成 Maker 策略，不使用 Maker 报告交付格式。
- 正式 Telegram Taker 预警必须全中文、简洁、包含完整风控字段。

## 执行步骤

1. 查找未处理候选事件：

   ```powershell
   .\.venv\Scripts\python -m trading_alerts --config config.json next-taker-candidate
   ```

2. 如果返回 `no_candidate`，立即结束，不分析、不发送 Telegram。

3. 如果返回 `candidate`，记录 `event_hash`，然后运行：

   ```powershell
   .\.venv\Scripts\python -m trading_alerts --config config.json prepare-taker-analysis --event-hash <event_hash>
   ```

4. 打开命令输出中的 `packet_path`，读取：

   - `candidate`
   - `data_scope`
   - `thresholds`
   - `allowed_signals`
   - `taker_logic`
   - `authority_files`

   `candidate` 中的早盘计划上下文必须纳入判断：

   - `setup_id`
   - `level_name`
   - `key_level`
   - `zone_low`
   - `zone_high`
   - `invalidation`
   - `scenario`

   如果 `candidate_context.complete=false`，默认不发送正式 Taker 预警；除非用户在当前对话里补齐缺失上下文。

5. 只读加载 `Trading-System` 权威文件，重点核对：

   - Taker 历史边界
   - 右侧入场定义
   - 流动性猎杀底层逻辑
   - 风控与入场/出场规则
   - 不能做 / 追单映射

## 2B 硬条件

2B 不是普通假突破。只有同时满足以下条件，才允许进入正式预警候选：

- 周期不低于 15m。
- 有明确前高、前低或关键区间边界。
- 价格短暂越过该位后失败。
- 失败后重新收回关键位内侧。
- 入场是右侧确认，不是左侧猜顶/猜底。
- 失效价、止损价、取消条件明确。
- 不是行情延伸末端追价。

## 评分框架

- TV 结构背景 40 分：趋势位置、关键支撑/压力、前高/前低、流动性位是否清晰。
- 触发质量 35 分：突破确认、假突破/假跌破、流动性猎杀反转、2B 是否真正完成。
- 执行安全 25 分：止损距离、滑点风险、盈亏比、取消条件、是否追在末端。

## Telegram 正式预警硬条件

- 总分 >= 75。
- 触发质量 >= 25/35。
- 执行安全 >= 18/25。
- 置信度 >= `config.json.trigger_win_rate`，默认 75%。
- 必须有：触发、入场、失效、止损、TP1、TP2、取消、风控、理由。
- 早盘关键位上下文必须完整；若缺失，用户必须在当前对话里补齐。

## 正式消息格式

```text
## Taker 预警

### BTC（信号类型+方向）：Taker 触发　置信度X%

触发：...
入场：...
失效：...
止损：...
TP1：...
TP2：...
取消：...
风控：...
理由：...
```

## 发送步骤

1. 将正式消息写入 `runtime_state/messages/taker_<timestamp>.txt`。
2. 先校验：

   ```powershell
   .\.venv\Scripts\python -m trading_alerts --config config.json validate-taker-message --message <message_file>
   ```

3. 只有校验通过且确实满足硬条件，才发送：

   ```powershell
   .\.venv\Scripts\python -m trading_alerts --config config.json send-taker-message --message <message_file> --send --signal <signal> --direction <long|short> --event-hash <event_hash>
   ```

## 不触发时

- 不发 Telegram 正式预警。
- 说明不触发原因，例如：关键位不成立、2B 未收回、只是插针、止损过宽、盈亏比不足、追价末端、风控字段不完整。
- 运行：

  ```powershell
  .\.venv\Scripts\python -m trading_alerts --config config.json mark-taker-candidate --event-hash <event_hash> --status skipped --reason "<原因>"
  ```

## 成功发送后

```powershell
.\.venv\Scripts\python -m trading_alerts --config config.json mark-taker-candidate --event-hash <event_hash> --status alert_sent --reason "formal taker alert sent"
```

> Publication note: sensitive literals and machine-specific paths were generalized for review.
