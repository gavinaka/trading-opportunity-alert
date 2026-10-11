import pytest

from trading_alerts.taker_event import (
    TakerEventError,
    format_candidate_notification,
    missing_plan_context_fields,
    parse_taker_candidate,
)


def test_parse_taker_candidate_normalizes_tradingview_payload():
    event = parse_taker_candidate(
        {
            "symbol": "btcusdt",
            "exchange": "binance",
            "timeframe": "15",
            "signal": "breakout_confirm",
            "direction": "long",
            "price": "62570.34",
            "trigger_time": "2026-07-04T13:45:00Z",
            "note": "TV webhook test",
        },
        received_at="2026-07-04T13:54:37Z",
    )

    assert event.symbol == "BTCUSDT"
    assert event.exchange == "BINANCE"
    assert event.timeframe == "15m"
    assert event.signal == "breakout_confirm"
    assert event.direction == "long"
    assert len(event.event_hash) == 64


def test_parse_taker_candidate_accepts_chinese_payload():
    event = parse_taker_candidate(
        {
            "品种": "btcusdt",
            "交易所": "binance",
            "周期": "15",
            "信号": "假跌破",
            "方向": "做多",
            "价格": "62,570.34",
            "时间": "2026-07-04T13:45:00Z",
            "计划ID": "BTC-20260704-R1",
            "位置名称": "62500压力区",
            "关键位": "62500",
            "区间下沿": "62000",
            "区间上沿": "62500",
            "失效参考": "站稳62650",
            "触发场景": "早盘压力区假跌破测试",
            "备注": "扫低后收回",
        }
    )

    assert event.symbol == "BTCUSDT"
    assert event.exchange == "BINANCE"
    assert event.timeframe == "15m"
    assert event.signal == "false_breakdown"
    assert event.direction == "long"
    assert event.price == "62570.34"
    assert event.setup_id == "BTC-20260704-R1"
    assert event.level_name == "62500压力区"
    assert event.key_level == "62500"
    assert event.zone_low == "62000"
    assert event.zone_high == "62500"
    assert event.invalidation == "站稳62650"
    assert event.scenario == "早盘压力区假跌破测试"
    assert event.missing_context_fields == ()
    assert missing_plan_context_fields(event) == ()


def test_parse_taker_candidate_accepts_2b_reversal_alias():
    event = parse_taker_candidate(
        {
            "品种": "BTCUSDT",
            "周期": "15m",
            "信号": "2B反转",
            "方向": "做空",
            "价格": "63120",
        }
    )

    assert event.signal == "two_b_reversal"
    assert event.direction == "short"
    assert "计划ID" in event.missing_context_fields


def test_parse_taker_candidate_rejects_unknown_signal():
    with pytest.raises(TakerEventError):
        parse_taker_candidate(
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "signal": "random_alert",
                "direction": "long",
                "price": "62570.34",
            }
        )


def test_parse_taker_candidate_rejects_non_numeric_price():
    with pytest.raises(TakerEventError):
        parse_taker_candidate(
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "signal": "breakout_confirm",
                "direction": "long",
                "price": "{{close}}",
            }
        )


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity"])
def test_parse_taker_candidate_rejects_non_finite_price(price):
    with pytest.raises(TakerEventError):
        parse_taker_candidate(
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "signal": "breakout_confirm",
                "direction": "long",
                "price": price,
            }
        )


def test_candidate_notification_is_explicitly_non_trade_signal():
    event = parse_taker_candidate(
        {
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "timeframe": "15",
            "signal": "false_breakdown",
            "direction": "long",
            "price": "62570.34",
            "setup_id": "BTC-20260704-S1",
            "level_name": "日内支撑区",
            "key_level": "62500",
            "zone_low": "62350",
            "zone_high": "62600",
            "invalidation": "跌回62300",
            "scenario": "支撑区假跌破收回",
        }
    )
    message = format_candidate_notification(event)
    assert "非交易信号" in message
    assert "TV结构确认" in message
    assert "计划ID：BTC-20260704-S1" in message
    assert "关键位置：日内支撑区" in message
    assert "区间：62350 - 62600" in message
    assert "失效参考：跌回62300" in message
    assert "上下文：完整" in message
    assert "五源" not in message
    assert "75%" in message


def test_candidate_notification_warns_when_plan_context_missing():
    event = parse_taker_candidate(
        {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "signal": "two_b_reversal",
            "direction": "short",
            "price": "63120",
        }
    )

    message = format_candidate_notification(event)

    assert "上下文：缺少" in message
    assert "默认不进入正式预警" in message


def test_setup_id_dedupes_repeated_tradingview_triggers():
    base = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "signal": "two_b_reversal",
        "direction": "short",
        "setup_id": "BTC-20260705-R1",
        "level_name": "62500压力区",
        "key_level": "62500",
        "zone_low": "62000",
        "zone_high": "62500",
        "invalidation": "15m站稳62650",
        "scenario": "上破压力区失败并跌回区间",
    }
    first = parse_taker_candidate({**base, "price": "62510", "trigger_time": "t1"})
    second = parse_taker_candidate({**base, "price": "62530", "trigger_time": "t2"})

    assert first.dedupe_key == second.dedupe_key
    assert first.event_hash == second.event_hash
