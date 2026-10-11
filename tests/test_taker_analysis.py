import json

from trading_alerts.config import AppConfig
from trading_alerts.taker_analysis import prepare_taker_analysis


def test_prepare_taker_analysis_is_tv_only(tmp_path):
    candidate_file = tmp_path / "runtime_state" / "webhooks" / "taker_candidates.jsonl"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_text(
        json.dumps(
            {
                "event_hash": "abc123",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "signal": "two_b_reversal",
                "direction": "short",
                "price": "63120",
                "dedupe_key": "mode|setup",
                "missing_context_fields": ["计划ID"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    config = AppConfig(
        project_root=tmp_path,
        trading_system_root=tmp_path / "Trading-System",
        slot="midday",
        trigger_win_rate=75,
        trigger_operator="gte",
        telegram_bot_token_env="TELEGRAM_BOT_TOKEN",
        telegram_chat_id_env="TELEGRAM_CHAT_ID",
        webhook_secret_env="WEBHOOK_SECRET",
        send_dry_run_by_default=True,
        max_message_chars=3900,
        authority_files=(),
    )

    packet_path = prepare_taker_analysis(config, event_hash="abc123")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert packet["data_scope"] == "tradingview_event_only"
    assert packet["schema_version"] == "1.3"
    assert packet["capture"] is None
    assert packet["candidate_context"]["complete"] is False
    assert packet["candidate_context"]["missing_fields"] == ["计划ID"]
    assert packet["candidate_context"]["default_action_if_incomplete"] == "skip_formal_alert"
    assert "two_b_reversal" in packet["allowed_signals"]
    assert "two_b_reversal" in packet["taker_logic"]["signal_playbook"]
    assert packet["taker_logic"]["data_policy"]["automatic_external_capture"] is False
    assert packet["authority_manifest"] == []
