from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


CONFIDENCE_RE = re.compile(r"置信度\s*([0-9]+(?:\.[0-9]+)?)\s*%")
TITLE_RE = re.compile(r"###\s*BTC[^\n]*")


@dataclass(frozen=True)
class TakerFields:
    confidence: float
    title: str
    trigger_line: str
    entry_line: str
    invalidation_line: str
    stop_line: str
    cancel_line: str


def extract_taker_fields(text: str) -> TakerFields:
    confidence = CONFIDENCE_RE.search(text)
    if not confidence:
        raise ValueError("Taker message missing confidence field")
    title = TITLE_RE.search(text)
    if not title:
        raise ValueError("Taker message missing BTC title line")
    return TakerFields(
        confidence=float(confidence.group(1)),
        title=title.group(0).strip(),
        trigger_line=_required_prefixed_line(text, "触发"),
        entry_line=_required_prefixed_line(text, "入场"),
        invalidation_line=_required_prefixed_line(text, "失效"),
        stop_line=_required_prefixed_line(text, "止损"),
        cancel_line=_required_prefixed_line(text, "取消"),
    )


def validate_taker_message(message: str, min_confidence: float | None = None) -> None:
    if "Taker" not in message:
        raise ValueError("Taker message must contain Taker label")
    for field in ("触发", "入场", "失效", "止损", "TP1", "TP2", "取消", "风控", "理由"):
        if f"{field}：" not in message and f"{field}:" not in message:
            raise ValueError(f"Taker message missing field: {field}")
    fields = extract_taker_fields(message)
    if min_confidence is not None and fields.confidence < min_confidence:
        raise ValueError(
            f"Taker confidence {fields.confidence:g}% is below threshold {min_confidence:g}%"
        )


def taker_alert_hash(message: str) -> str:
    fields = extract_taker_fields(message)
    stable = "\n".join(
        (
            fields.title,
            fields.trigger_line,
            fields.entry_line,
            fields.invalidation_line,
            fields.stop_line,
            fields.cancel_line,
            f"confidence={fields.confidence:g}",
        )
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _required_prefixed_line(text: str, label: str) -> str:
    pattern = re.compile(rf"^{re.escape(label)}[：:]\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Taker message missing field: {label}")
    value = match.group(0).strip()
    if not match.group(1).strip():
        raise ValueError(f"Taker message has empty field: {label}")
    return value
