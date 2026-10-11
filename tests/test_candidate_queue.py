import json

import pytest

from trading_alerts.candidate_queue import mark_candidate, next_unprocessed_candidate
from trading_alerts.state_safety import StateCorruptionError


def test_candidate_queue_returns_oldest_unprocessed(tmp_path):
    events = tmp_path / "runtime_state" / "webhooks" / "taker_candidates.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        "\n".join(
            [
                json.dumps({"event_hash": "a", "symbol": "BTCUSDT"}),
                json.dumps({"event_hash": "b", "symbol": "BTCUSDT"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert next_unprocessed_candidate(tmp_path)["event_hash"] == "a"
    mark_candidate(tmp_path, "a", "skipped", "test")
    assert next_unprocessed_candidate(tmp_path)["event_hash"] == "b"
    mark_candidate(tmp_path, "b", "alert_sent", "test")
    assert next_unprocessed_candidate(tmp_path) is None


def test_candidate_queue_fails_closed_on_corrupt_jsonl(tmp_path):
    events = tmp_path / "runtime_state" / "webhooks" / "taker_candidates.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"event_hash":"a"}\n{broken\n', encoding="utf-8")
    with pytest.raises(StateCorruptionError):
        next_unprocessed_candidate(tmp_path)
