from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class StateCorruptionError(RuntimeError):
    pass


class StateCapacityError(RuntimeError):
    """Raised before a state file can consume unbounded memory or disk."""


DEFAULT_JSON_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_JSONL_MAX_BYTES = 32 * 1024 * 1024
DEFAULT_JSONL_MAX_RECORDS = 100_000


def load_json_state(
    path: Path,
    *,
    expected_mapping: str,
    max_bytes: int = DEFAULT_JSON_MAX_BYTES,
) -> dict:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return {"schema_version": "1.0", expected_mapping: {}}
    if size > max_bytes:
        raise StateCapacityError(
            f"state file exceeds {max_bytes} bytes; archive/compact it before retrying: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": "1.0", expected_mapping: {}}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        quarantine = path.with_name(
            f"{path.name}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        os.replace(path, quarantine)
        raise StateCorruptionError(
            f"state file was corrupt and quarantined: {quarantine}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get(expected_mapping), dict):
        raise StateCorruptionError(
            f"state file schema is invalid and was not overwritten: {path}"
        )
    return payload


def iter_jsonl_records(
    path: Path,
    *,
    strict: bool = False,
    max_bytes: int = DEFAULT_JSONL_MAX_BYTES,
    max_records: int = DEFAULT_JSONL_MAX_RECORDS,
):
    """Stream a bounded JSONL state file without materializing it in memory."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    if size > max_bytes:
        raise StateCapacityError(
            f"JSONL state exceeds {max_bytes} bytes; archive/compact it before retrying: {path}"
        )
    record_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record_count += 1
            if record_count > max_records:
                raise StateCapacityError(
                    f"JSONL state exceeds {max_records} records; archive/compact it before retrying: {path}"
                )
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                if strict:
                    raise StateCorruptionError(
                        f"invalid JSONL record at {path}:{line_number}"
                    ) from exc
                continue
            if isinstance(payload, dict):
                yield payload
            elif strict:
                raise StateCorruptionError(
                    f"JSONL record is not an object at {path}:{line_number}"
                )


def assert_jsonl_append_capacity(
    path: Path,
    incoming_bytes: int,
    *,
    max_bytes: int = DEFAULT_JSONL_MAX_BYTES,
) -> None:
    try:
        current_bytes = path.stat().st_size
    except FileNotFoundError:
        current_bytes = 0
    if current_bytes + incoming_bytes > max_bytes:
        raise StateCapacityError(
            f"JSONL state would exceed {max_bytes} bytes; archive/compact it before retrying: {path}"
        )


@contextmanager
def exclusive_state_lock(path: Path, *, timeout_seconds: float = 5.0):
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError):
            try:
                age = time.time() - lock.stat().st_mtime
            except (FileNotFoundError, PermissionError):
                time.sleep(0.01)
                continue
            if age > 60:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out acquiring state lock: {lock}")
            time.sleep(0.05)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        for _ in range(20):
            try:
                lock.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(0.01)
