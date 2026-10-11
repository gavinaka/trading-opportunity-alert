from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path


def sha256_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def begin_local_lease(project_root: Path, trading_date: str, slot: str) -> dict:
    token = uuid.uuid4().hex
    payload = {
        "schema_version": "local-alerts-v1",
        "status": "active",
        "trading_date": trading_date,
        "slot": slot,
        "token": token,
        "lease_id": sha256_token(token),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "owner": "trading-opportunity-alerts",
    }
    atomic_write_json(project_root / "runtime_state" / "workflow_lease.json", payload)
    return payload


def complete_local_lease(project_root: Path, token: str, artifact: str | None = None) -> None:
    path = project_root / "runtime_state" / "workflow_lease.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    if payload.get("token") != token:
        return
    payload["status"] = "complete"
    payload["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if artifact:
        payload["artifact"] = artifact
    atomic_write_json(path, payload)

