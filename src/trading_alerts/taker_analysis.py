from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .candidate_queue import next_unprocessed_candidate
from .config import AppConfig
from .state_safety import iter_jsonl_records
from .taker_event import ALLOWED_SIGNALS
from .taker_logic import taker_logic_payload
from .timeutil import local_timestamp


def load_latest_candidate(project_root: Path, event_hash: str | None = None) -> dict[str, Any]:
    path = project_root / "runtime_state" / "webhooks" / "taker_candidates.jsonl"
    latest: dict[str, Any] | None = None
    for payload in iter_jsonl_records(path, strict=True):
        if event_hash is None or payload.get("event_hash") == event_hash:
            latest = payload
    if latest is None:
        if event_hash:
            raise FileNotFoundError(f"candidate event not found: {event_hash}")
        raise FileNotFoundError(f"no candidate events found in {path}")
    return latest


def prepare_taker_analysis(
    config: AppConfig,
    event_hash: str | None = None,
) -> Path:
    if event_hash is None:
        candidate = next_unprocessed_candidate(config.project_root)
        if candidate is None:
            raise FileNotFoundError("no unprocessed candidate events found")
    else:
        candidate = load_latest_candidate(config.project_root, event_hash)
    packet = {
        "schema_version": "1.3",
        "created_at": local_timestamp(),
        "mode": "taker_event_analysis",
        "data_scope": "tradingview_event_only",
        "candidate": candidate,
        "candidate_context": _candidate_context(candidate),
        "capture": None,
        "thresholds": {
            "min_confidence": config.trigger_win_rate,
            "operator": config.trigger_operator,
        },
        "allowed_signals": sorted(ALLOWED_SIGNALS),
        "taker_logic": taker_logic_payload(),
        "trading_system_root": str(config.trading_system_root),
        "authority_manifest": _authority_manifest(config),
        "hard_boundaries": [
            "Trading-System is read-only.",
            "TradingView event is only a candidate, not a trade signal.",
            "No automatic external source capture is allowed in this Taker event path.",
            "Formal Telegram Taker alert requires TradingView structure confirmation, confidence threshold, and risk gate pass.",
        ],
    }
    target_dir = config.project_root / "runtime_state" / "taker_analysis"
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"packet_{local_timestamp().replace(':', '').replace('+', '_')}.json"
    target = target_dir / filename
    target.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _authority_manifest(config: AppConfig) -> list[dict[str, Any]]:
    records = []
    for relative in config.authority_files:
        path = (config.trading_system_root / relative).resolve()
        try:
            path.relative_to(config.trading_system_root.resolve())
        except ValueError as exc:
            raise ValueError(f"authority file escapes Trading-System: {relative}") from exc
        if not path.is_file():
            raise FileNotFoundError(f"authority file missing: {relative}")
        records.append(
            {
                "path": str(relative).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        )
    return records


def _candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    missing = candidate.get("missing_context_fields", ())
    if not isinstance(missing, list | tuple):
        missing = ()
    return {
        "complete": len(missing) == 0,
        "missing_fields": list(missing),
        "dedupe_key": candidate.get("dedupe_key"),
        "default_action_if_incomplete": "skip_formal_alert",
    }
