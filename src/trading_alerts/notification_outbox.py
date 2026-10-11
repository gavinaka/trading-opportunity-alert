from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from .lease import atomic_write_json
from .state_safety import assert_jsonl_append_capacity, iter_jsonl_records, load_json_state
from .timeutil import local_timestamp


class NotificationOutbox:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.events = directory / "notification_outbox.jsonl"
        self.state = directory / "notification_outbox_state.json"
        self.lock = threading.RLock()

    def enqueue(self, event_hash: str, message: str, context: dict) -> bool:
        with self.lock:
            state = self._load_state()
            if state["items"].get(event_hash, {}).get("status") in {"queued", "sending", "delivered"}:
                return False
            self.directory.mkdir(parents=True, exist_ok=True)
            record = {
                "event_hash": event_hash,
                "message": message,
                "context": context,
                "queued_at": local_timestamp(),
            }
            line = json.dumps(record, ensure_ascii=False) + "\n"
            assert_jsonl_append_capacity(self.events, len(line.encode("utf-8")))
            with self.events.open("a", encoding="utf-8") as handle:
                handle.write(line)
            state["items"][event_hash] = {"status": "queued", "attempts": 0, "updated_at": local_timestamp()}
            atomic_write_json(self.state, state)
            return True

    def drain_once(self, sender: Callable[[str], object], *, max_attempts: int = 3) -> dict:
        delivered = failed = 0
        records = self._records()
        with self.lock:
            state = self._load_state()
        for event_hash, record in records.items():
            item = state["items"].get(event_hash, {})
            if item.get("status") == "delivered":
                continue
            attempts = int(item.get("attempts", 0))
            while attempts < max_attempts:
                attempts += 1
                self._update(event_hash, "sending", attempts)
                try:
                    sender(record["message"])
                except Exception as exc:
                    self._update(event_hash, "queued", attempts, error=str(exc))
                    if attempts < max_attempts:
                        time.sleep(min(2 ** (attempts - 1), 4))
                    continue
                self._update(event_hash, "delivered", attempts)
                delivered += 1
                break
            else:
                failed += 1
        return {"delivered": delivered, "failed": failed}

    def _records(self) -> dict[str, dict]:
        records = {}
        for payload in iter_jsonl_records(self.events, strict=True):
            records[str(payload["event_hash"])] = payload
        return records

    def _load_state(self) -> dict:
        return load_json_state(self.state, expected_mapping="items")

    def _update(self, event_hash: str, status: str, attempts: int, *, error: str | None = None) -> None:
        with self.lock:
            state = self._load_state()
            item = {"status": status, "attempts": attempts, "updated_at": local_timestamp()}
            if error:
                item["last_error"] = error
            state["items"][event_hash] = item
            atomic_write_json(self.state, state)
