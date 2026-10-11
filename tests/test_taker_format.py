from trading_alerts.taker_format import (
    extract_taker_fields,
    taker_alert_hash,
    validate_taker_message,
)


TAKER = """## Taker 预警

### BTC（流动性猎杀反转多）：Taker 触发　置信度78%

触发：15m 扫前低后收回关键区间。
入场：现价附近或回踩确认后，不追涨。
失效：15m 重新跌破扫低位置。
止损：扫低下方。
TP1：上一压力区，减仓50%。
TP2：4H 阻力区，清理剩余仓位。
取消：触发后 30 分钟无延续，或 CVD/OI 转弱。
风控：单笔亏损不超过3%，盈亏比不低于1:2.5。
理由：扫流动性后快速收回，追空资金存在被困风险。
"""


def test_taker_message_validation_and_hash():
    validate_taker_message(TAKER, min_confidence=75)
    fields = extract_taker_fields(TAKER)
    assert fields.confidence == 78
    assert len(taker_alert_hash(TAKER)) == 64
