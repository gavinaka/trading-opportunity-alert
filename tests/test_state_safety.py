import json
import threading

import pytest

from trading_alerts.state import mark_sent, reserve_send
from trading_alerts.state_safety import (
    StateCapacityError,
    StateCorruptionError,
    assert_jsonl_append_capacity,
    iter_jsonl_records,
    load_json_state,
)


def test_corrupt_state_is_quarantined_not_silently_reset(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(StateCorruptionError):
        load_json_state(path, expected_mapping="sent")
    assert not path.exists()
    assert list(tmp_path.glob("state.json.corrupt.*"))


def test_send_reservation_is_atomic_across_threads(tmp_path):
    accepted = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        accepted.append(reserve_send(tmp_path, "same-hash", {"source": "test"}))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert accepted.count(True) == 1
    assert accepted.count(False) == 7


def test_jsonl_reader_is_streamed_and_capacity_bounded(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event_hash":"a"}\n{"event_hash":"b"}\n', encoding="utf-8")
    assert [item["event_hash"] for item in iter_jsonl_records(path)] == ["a", "b"]
    with pytest.raises(StateCapacityError):
        list(iter_jsonl_records(path, max_bytes=1))
    with pytest.raises(StateCapacityError):
        list(iter_jsonl_records(path, max_records=1))
    with pytest.raises(StateCapacityError):
        assert_jsonl_append_capacity(path, 1, max_bytes=path.stat().st_size)
