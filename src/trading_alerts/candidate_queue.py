from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .lease import atomic_write_json
from .state_safety import exclusive_state_lock, iter_jsonl_records, load_json_state
from .timeutil import local_timestamp


CandidateStatus = Literal["skipped", "alert_sent", "error"]


def next_unprocessed_candidate(project_root: Path) -> dict[str, Any] | None:
    state = _load_state(project_root)
    processed = state.get("processed", {})
    selected: dict[str, Any] | None = None
    for candidate in _iter_candidates(project_root):
        event_hash = candidate.get("event_hash")
        if not isinstance(event_hash, str):
            continue
        if event_hash not in processed and selected is None:
            selected = candidate
    # Finish scanning before returning so corruption later in the append-only
    # authority file cannot be hidden behind an earlier valid candidate.
    return selected


def mark_candidate(
    project_root: Path,
    event_hash: str,
    status: CandidateStatus,
    reason: str | None = None,
) -> dict[str, Any]:
    if not event_hash:
        raise ValueError("event_hash is required")
    path = _state_path(project_root)
    with exclusive_state_lock(path):
        state = _load_state(project_root)
        processed = state.setdefault("processed", {})
        processed[event_hash] = {
            "status": status,
            "reason": reason,
            "updated_at": local_timestamp(),
        }
        atomic_write_json(path, state)
        return processed[event_hash]


def _iter_candidates(project_root: Path):
    path = project_root / "runtime_state" / "webhooks" / "taker_candidates.jsonl"
    yield from iter_jsonl_records(path, strict=True)


def _load_state(project_root: Path) -> dict[str, Any]:
    return load_json_state(_state_path(project_root), expected_mapping="processed")


def _state_path(project_root: Path) -> Path:
    return project_root / "runtime_state" / "webhooks" / "taker_candidate_state.json"
