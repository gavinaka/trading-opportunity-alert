from trading_alerts.notification_outbox import NotificationOutbox


def test_outbox_retries_and_persists_delivery(tmp_path):
    outbox = NotificationOutbox(tmp_path)
    assert outbox.enqueue("event-1", "hello", {"source": "test"})
    calls = []

    def sender(message):
        calls.append(message)
        if len(calls) == 1:
            raise RuntimeError("temporary")

    result = outbox.drain_once(sender, max_attempts=2)
    assert result == {"delivered": 1, "failed": 0}
    assert len(calls) == 2
    assert not outbox.enqueue("event-1", "hello", {})
