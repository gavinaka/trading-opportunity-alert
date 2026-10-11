from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


ALLOWED_SIGNALS = {
    "breakout_confirm",
    "false_breakout",
    "false_breakdown",
    "liquidity_sweep_reversal",
    "two_b_reversal",
}

ALLOWED_DIRECTIONS = {"long", "short"}

PLAN_CONTEXT_LABELS = {
    "setup_id": "计划ID",
    "level_name": "位置名称",
    "key_level": "关键位",
    "zone_low": "区间下沿",
    "zone_high": "区间上沿",
    "invalidation": "失效参考",
    "scenario": "触发场景",
}

SIGNAL_ALIASES = {
    "breakout_confirm": "breakout_confirm",
    "突破确认": "breakout_confirm",
    "真突破": "breakout_confirm",
    "false_breakout": "false_breakout",
    "假突破": "false_breakout",
    "false_breakdown": "false_breakdown",
    "假跌破": "false_breakdown",
    "liquidity_sweep_reversal": "liquidity_sweep_reversal",
    "流动性猎杀反转": "liquidity_sweep_reversal",
    "扫流动性反转": "liquidity_sweep_reversal",
    "two_b_reversal": "two_b_reversal",
    "2b": "two_b_reversal",
    "2b反转": "two_b_reversal",
    "2b交易": "two_b_reversal",
    "右侧2b": "two_b_reversal",
    "右侧2b反转": "two_b_reversal",
}

DIRECTION_ALIASES = {
    "long": "long",
    "做多": "long",
    "看多": "long",
    "多": "long",
    "short": "short",
    "做空": "short",
    "看空": "short",
    "空": "short",
}


class TakerEventError(ValueError):
    pass


@dataclass(frozen=True)
class TakerCandidateEvent:
    received_at: str
    symbol: str
    exchange: str | None
    timeframe: str
    signal: str
    direction: str
    price: str
    trigger_time: str | None
    setup_id: str | None
    level_name: str | None
    key_level: str | None
    zone_low: str | None
    zone_high: str | None
    invalidation: str | None
    scenario: str | None
    note: str | None
    dedupe_key: str
    missing_context_fields: tuple[str, ...]
    event_hash: str

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_taker_candidate(payload: Any, received_at: str | None = None) -> TakerCandidateEvent:
    if not isinstance(payload, dict):
        raise TakerEventError("payload must be a JSON object")

    symbol = _required_str(payload, "symbol", "品种", "交易品种", "标的").upper()
    signal = _normalize_signal(_required_str(payload, "signal", "信号"))
    direction = _normalize_direction(_required_str(payload, "direction", "方向"))
    timeframe = _normalize_timeframe(_required_str(payload, "timeframe", "周期", "级别"))
    price = _normalize_price(_required_str(payload, "price", "价格"))

    if signal not in ALLOWED_SIGNALS:
        raise TakerEventError(f"unsupported signal: {signal}")
    if direction not in ALLOWED_DIRECTIONS:
        raise TakerEventError(f"unsupported direction: {direction}")

    exchange = _optional_str(payload, "exchange", "交易所")
    trigger_time = _optional_str(payload, "trigger_time", "时间", "触发时间", "TV时间")
    setup_id = _optional_str(payload, "setup_id", "计划ID", "警报ID", "场景ID")
    level_name = _optional_str(payload, "level_name", "位置名称", "关键位置名称", "关键区名称")
    key_level = _optional_str(payload, "key_level", "关键位", "关键价", "关键价格")
    zone_low = _optional_str(payload, "zone_low", "区间下沿", "下沿", "支撑下沿")
    zone_high = _optional_str(payload, "zone_high", "区间上沿", "上沿", "压力上沿")
    invalidation = _optional_str(payload, "invalidation", "失效参考", "失效价", "失效", "止损参考")
    scenario = _optional_str(payload, "scenario", "触发场景", "场景", "计划场景")
    note = _optional_str(payload, "note", "备注", "说明")
    if received_at is None:
        received_at = datetime.now(timezone.utc).isoformat()

    event = TakerCandidateEvent(
        received_at=received_at,
        symbol=symbol,
        exchange=exchange.upper() if exchange else None,
        timeframe=timeframe,
        signal=signal,
        direction=direction,
        price=price,
        trigger_time=trigger_time,
        setup_id=setup_id,
        level_name=level_name,
        key_level=key_level,
        zone_low=zone_low,
        zone_high=zone_high,
        invalidation=invalidation,
        scenario=scenario,
        note=note,
        dedupe_key="",
        missing_context_fields=(),
        event_hash="",
    )
    dedupe_payload = _dedupe_payload(event)
    event_hash = _event_hash(dedupe_payload)
    return TakerCandidateEvent(
        **{
            **event.to_json_dict(),
            "dedupe_key": _dedupe_key(dedupe_payload),
            "missing_context_fields": missing_plan_context_fields(event),
            "event_hash": event_hash,
        }
    )


def format_candidate_notification(event: TakerCandidateEvent) -> str:
    signal_name = {
        "breakout_confirm": "突破确认",
        "false_breakout": "假突破",
        "false_breakdown": "假跌破",
        "liquidity_sweep_reversal": "流动性猎杀反转",
        "two_b_reversal": "2B反转",
    }.get(event.signal, event.signal)
    direction_name = {"long": "做多候选", "short": "做空候选"}.get(event.direction, event.direction)
    lines = [
        "【候选已收到｜非交易信号】",
        "",
        f"{event.symbol}｜{signal_name}｜{direction_name}",
        f"价格：{event.price}",
        f"周期：{event.timeframe}",
    ]
    if event.setup_id:
        lines.append(f"计划ID：{event.setup_id}")
    if event.scenario:
        lines.append(f"场景：{event.scenario}")
    if event.level_name:
        lines.append(f"关键位置：{event.level_name}")
    if event.key_level:
        lines.append(f"关键位：{event.key_level}")
    if event.zone_low or event.zone_high:
        lines.append(f"区间：{event.zone_low or '?'} - {event.zone_high or '?'}")
    if event.invalidation:
        lines.append(f"失效参考：{event.invalidation}")
    if event.missing_context_fields:
        lines.append(f"上下文：缺少{'、'.join(event.missing_context_fields)}")
    else:
        lines.append("上下文：完整")
    if event.exchange:
        lines.append(f"交易所：{event.exchange}")
    if event.trigger_time:
        lines.append(f"时间：{event.trigger_time}")
    if event.note:
        lines.append(f"备注：{event.note}")
    lines.extend(
        [
            "",
            "状态：仅记录候选，等待二次判断。",
            "正式提醒：TV结构确认 + Taker逻辑成立 + 置信度≥75% + 风控通过。",
        ]
    )
    if event.missing_context_fields:
        lines.append("限制：早盘关键位上下文不完整，默认不进入正式预警。")
    return "\n".join(lines)


def missing_plan_context_fields(event: TakerCandidateEvent) -> tuple[str, ...]:
    missing: list[str] = []
    for field, label in PLAN_CONTEXT_LABELS.items():
        if not getattr(event, field):
            missing.append(label)
    return tuple(missing)


def _required_str(payload: dict[str, Any], *keys: str) -> str:
    value = _first_value(payload, *keys)
    if value is None:
        raise TakerEventError(f"missing required field: {'/'.join(keys)}")
    text = str(value).strip()
    if not text:
        raise TakerEventError(f"empty required field: {'/'.join(keys)}")
    return text


def _optional_str(payload: dict[str, Any], *keys: str) -> str | None:
    value = _first_value(payload, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _normalize_signal(value: str) -> str:
    text = value.strip()
    normalized = SIGNAL_ALIASES.get(text.lower()) or SIGNAL_ALIASES.get(text)
    if normalized is None:
        raise TakerEventError(f"unsupported signal: {value}")
    return normalized


def _normalize_direction(value: str) -> str:
    text = value.strip()
    normalized = DIRECTION_ALIASES.get(text.lower()) or DIRECTION_ALIASES.get(text)
    if normalized is None:
        raise TakerEventError(f"unsupported direction: {value}")
    return normalized


def _normalize_timeframe(value: str) -> str:
    text = value.strip().lower()
    if text.isdigit():
        return f"{text}m"
    return text


def _normalize_price(value: str) -> str:
    text = value.strip().replace(",", "")
    try:
        parsed = float(text)
    except ValueError as exc:
        raise TakerEventError("price must be numeric") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise TakerEventError("price must be positive")
    return text


def _event_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dedupe_payload(event: TakerCandidateEvent) -> dict[str, Any]:
    if event.setup_id:
        return {
            "mode": "setup",
            "setup_id": event.setup_id,
            "symbol": event.symbol,
            "timeframe": event.timeframe,
            "signal": event.signal,
            "direction": event.direction,
        }
    return {
        "mode": "legacy_event",
        "symbol": event.symbol,
        "timeframe": event.timeframe,
        "signal": event.signal,
        "direction": event.direction,
        "price": event.price,
        "trigger_time": event.trigger_time,
    }


def _dedupe_key(payload: dict[str, Any]) -> str:
    return "|".join(str(payload[key] or "") for key in sorted(payload))
