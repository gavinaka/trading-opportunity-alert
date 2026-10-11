from __future__ import annotations

import argparse
import json
from pathlib import Path

from .candidate_queue import mark_candidate, next_unprocessed_candidate
from .config import load_config
from .state import mark_send_failed, mark_sent, reserve_send, was_sent
from .taker_analysis import prepare_taker_analysis
from .taker_format import extract_taker_fields, taker_alert_hash, validate_taker_message
from .telegram import TelegramClient
from .webhook_server import add_serve_webhook_parser, serve_webhook


def main() -> int:
    parser = argparse.ArgumentParser(description="TradingView-driven Taker candidate alert receiver")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    send_test = sub.add_parser("send-test", help="send a Telegram smoke-test message")
    send_test.add_argument("--text", default="Trading opportunity alert test.")

    validate_taker = sub.add_parser("validate-taker-message", help="validate a Taker alert file")
    validate_taker.add_argument("--message", type=Path, required=True)

    send_taker = sub.add_parser(
        "send-taker-message",
        help="send a Codex-authored Taker alert through Telegram with duplicate suppression",
    )
    send_taker.add_argument("--message", type=Path, required=True)
    send_taker.add_argument("--dry-run", action="store_true")
    send_taker.add_argument("--send", action="store_true")
    send_taker.add_argument("--force-send", action="store_true")
    send_taker.add_argument("--signal")
    send_taker.add_argument("--direction")
    send_taker.add_argument("--event-hash")

    prepare_taker = sub.add_parser(
        "prepare-taker-analysis",
        help="create a Codex analysis packet from the latest TV Taker candidate",
    )
    prepare_taker.add_argument("--event-hash")

    next_candidate = sub.add_parser(
        "next-taker-candidate",
        help="print the oldest unprocessed TV Taker candidate event",
    )

    mark_candidate_parser = sub.add_parser(
        "mark-taker-candidate",
        help="mark a TV Taker candidate event as processed",
    )
    mark_candidate_parser.add_argument("--event-hash", required=True)
    mark_candidate_parser.add_argument(
        "--status",
        choices=("skipped", "alert_sent", "error"),
        required=True,
    )
    mark_candidate_parser.add_argument("--reason")

    add_serve_webhook_parser(sub)

    args = parser.parse_args()
    config = load_config(args.config, args.env_file)

    if args.command == "send-test":
        client = _telegram_client(config)
        client.send_text(args.text)
        print("telegram test sent")
        return 0

    if args.command == "validate-taker-message":
        text = args.message.read_text(encoding="utf-8")
        validate_taker_message(text, min_confidence=config.trigger_win_rate)
        print(json.dumps({"status": "ok", "alert_hash": taker_alert_hash(text)}))
        return 0

    if args.command == "send-taker-message":
        text = args.message.read_text(encoding="utf-8")
        validate_taker_message(text, min_confidence=config.trigger_win_rate)
        fields = extract_taker_fields(text)
        return _send_text(
            config,
            text,
            args.dry_run,
            args.send,
            args.force_send,
            {
                "confidence": fields.confidence,
                "signal": args.signal,
                "direction": args.direction,
                "event_hash": args.event_hash,
                "mode": "taker",
            },
            alert_hash=taker_alert_hash(text),
        )

    if args.command == "prepare-taker-analysis":
        packet = prepare_taker_analysis(
            config,
            event_hash=args.event_hash,
        )
        print(json.dumps({"status": "prepared", "packet_path": str(packet)}, ensure_ascii=False))
        return 0

    if args.command == "next-taker-candidate":
        candidate = next_unprocessed_candidate(config.project_root)
        if candidate is None:
            print(json.dumps({"status": "no_candidate"}, ensure_ascii=False))
            return 0
        print(
            json.dumps(
                {
                    "status": "candidate",
                    "event_hash": candidate.get("event_hash"),
                    "candidate": candidate,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "mark-taker-candidate":
        payload = mark_candidate(
            config.project_root,
            args.event_hash,
            args.status,
            args.reason,
        )
        print(
            json.dumps(
                {"status": "marked", "event_hash": args.event_hash, "state": payload},
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "serve-webhook":
        telegram_client = _telegram_client(config) if args.notify_candidates else None
        serve_webhook(
            config.project_root,
            args.host,
            args.port,
            args.secret or config.webhook_secret,
            telegram_client=telegram_client,
            notify_candidates=args.notify_candidates,
            require_secret=args.require_secret,
        )
        return 0

    raise ValueError(f"unsupported command: {args.command}")


def _send_text(
    config,
    message: str,
    dry_run_flag: bool,
    send_flag: bool,
    force_send: bool,
    metadata: dict,
    alert_hash: str | None = None,
) -> int:
    if alert_hash is None:
        raise RuntimeError("message hash is required; Maker send paths are disabled")
    plan_hash = alert_hash
    dry_run = dry_run_flag or (config.send_dry_run_by_default and not send_flag)
    if dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run_alert",
                    "plan_hash": plan_hash,
                    "message": message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not reserve_send(config.project_root, plan_hash, metadata, force=force_send):
        print(json.dumps({"status": "duplicate_suppressed", "plan_hash": plan_hash}))
        return 0
    client = _telegram_client(config)
    try:
        client.send_text(message)
    except Exception as exc:
        mark_send_failed(config.project_root, plan_hash, str(exc))
        raise
    mark_sent(
        config.project_root,
        plan_hash,
        metadata,
    )
    print(json.dumps({"status": "sent", "plan_hash": plan_hash}))
    return 0


def _telegram_client(config) -> TelegramClient:
    token = config.telegram_bot_token
    chat_id = config.telegram_chat_id
    if not token:
        raise RuntimeError(f"missing Telegram bot token env var: {config.telegram_bot_token_env}")
    if not chat_id:
        raise RuntimeError(f"missing Telegram chat id env var: {config.telegram_chat_id_env}")
    return TelegramClient(token, chat_id, config.max_message_chars)
