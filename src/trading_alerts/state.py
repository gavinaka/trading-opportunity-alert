from __future__ import annotations

import json
from pathlib import Path

from .lease import atomic_write_json
from .state_safety import exclusive_state_lock, load_json_state
from .timeutil import local_timestamp


def _state_path(project_root: Path) -> Path:
    return project_root / "runtime_state" / "alerts_sent.json"


def load_sent(project_root: Path) -> dict:
    return load_json_state(_state_path(project_root), expected_mapping="sent")


def was_sent(project_root: Path, plan_hash: str) -> bool:
    record = load_sent(project_root)["sent"].get(plan_hash)
    return isinstance(record, dict) and record.get("status", "sent") in {"sending", "sent"}


def reserve_send(project_root: Path, plan_hash: str, metadata: dict, *, force: bool = False) -> bool:
    path = _state_path(project_root)
    with exclusive_state_lock(path):
        payload = load_sent(project_root)
        existing = payload["sent"].get(plan_hash)
        if existing and existing.get("status", "sent") in {"sending", "sent"} and not force:
            return False
        payload["sent"][plan_hash] = {
            "status": "sending",
            "reserved_at": local_timestamp(),
            **metadata,
        }
        atomic_write_json(path, payload)
    return True


def mark_sent(project_root: Path, plan_hash: str, metadata: dict) -> None:
    path = _state_path(project_root)
    with exclusive_state_lock(path):
        payload = load_sent(project_root)
        payload["sent"][plan_hash] = {
            "status": "sent",
            "sent_at": local_timestamp(),
            **metadata,
        }
        atomic_write_json(path, payload)


def mark_send_failed(project_root: Path, plan_hash: str, error: str) -> None:
    path = _state_path(project_root)
    with exclusive_state_lock(path):
        payload = load_sent(project_root)
        payload["sent"][plan_hash] = {
            "status": "failed",
            "failed_at": local_timestamp(),
            "error": error,
        }
        atomic_write_json(path, payload)
