from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .taker_event import TakerEventError, format_candidate_notification, parse_taker_candidate
from .telegram import TelegramClient
from .notification_outbox import NotificationOutbox
from .state_safety import StateCapacityError, assert_jsonl_append_capacity, iter_jsonl_records


class WebhookHandler(BaseHTTPRequestHandler):
    server: "WebhookHTTPServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/health":
            self._send_json(404, {"status": "not_found"})
            return
        self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/tv-webhook":
            self._send_json(404, {"status": "not_found"})
            return

        content_length = _content_length(self.headers.get("Content-Length"))
        if content_length is None:
            self._send_json(413, {"status": "payload_too_large"})
            return

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"status": "invalid_json"})
            return

        if self.server.secret and not _valid_secret(payload, self.server.secret):
            try:
                self.server.append_rejected_event(
                    {
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "remote_addr": self.client_address[0],
                        "payload": _redact_secret(payload),
                        "error": "unauthorized",
                    }
                )
            except StateCapacityError as exc:
                self._send_json(507, {"status": "state_capacity_exceeded", "error": str(exc)})
                return
            self._send_json(401, {"status": "unauthorized"})
            return

        received_at = datetime.now(timezone.utc).isoformat()
        event = {
            "received_at": received_at,
            "remote_addr": self.client_address[0],
            "payload": _redact_secret(payload),
        }
        try:
            candidate = parse_taker_candidate(payload, received_at=received_at)
        except TakerEventError as exc:
            try:
                self.server.append_rejected_event({**event, "error": str(exc)})
            except StateCapacityError as capacity_exc:
                self._send_json(
                    507,
                    {"status": "state_capacity_exceeded", "error": str(capacity_exc)},
                )
                return
            self._send_json(422, {"status": "rejected", "error": str(exc)})
            return

        try:
            self.server.append_event(event)
            accepted = self.server.accept_candidate(candidate.to_json_dict())
        except StateCapacityError as exc:
            self._send_json(507, {"status": "state_capacity_exceeded", "error": str(exc)})
            return
        if not accepted:
            self._send_json(
                200,
                {
                    "status": "received",
                    "candidate_status": "duplicate",
                    "telegram_status": "suppressed",
                    "event_hash": candidate.event_hash,
                },
            )
            return

        telegram_status = "disabled"
        if self.server.notify_candidates:
            self.server.queue_candidate_notification(
                candidate.event_hash,
                format_candidate_notification(candidate),
                {**event, "event_hash": candidate.event_hash},
            )
            telegram_status = "queued"
        self._send_json(
            200,
            {
                "status": "received",
                "candidate_status": "accepted",
                "telegram_status": telegram_status,
                "event_hash": candidate.event_hash,
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        line = f"{datetime.now(timezone.utc).isoformat()} {self.address_string()} {format % args}\n"
        self.server.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.server.file_lock:
            with self.server.log_file.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebhookHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        event_file: Path,
        candidate_file: Path,
        rejected_file: Path,
        log_file: Path,
        secret: str | None,
        telegram_client: TelegramClient | None,
        notify_candidates: bool,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.event_file = event_file
        self.candidate_file = candidate_file
        self.rejected_file = rejected_file
        self.log_file = log_file
        self.secret = secret
        self.telegram_client = telegram_client
        self.notify_candidates = notify_candidates
        self.file_lock = threading.RLock()
        self.seen_candidates = _load_candidate_hashes(candidate_file)
        self.outbox = NotificationOutbox(candidate_file.parent)

    def append_event(self, event: dict[str, Any]) -> None:
        self._append_jsonl(self.event_file, event)

    def accept_candidate(self, candidate: dict[str, Any]) -> bool:
        event_hash = candidate.get("event_hash")
        if not isinstance(event_hash, str):
            raise ValueError("candidate event_hash is required")
        with self.file_lock:
            if event_hash in self.seen_candidates:
                return False
            self._append_jsonl(self.candidate_file, candidate)
            self.seen_candidates.add(event_hash)
            return True

    def append_rejected_event(self, event: dict[str, Any]) -> None:
        self._append_jsonl(self.rejected_file, event)

    def queue_candidate_notification(self, event_hash: str, message: str, event: dict[str, Any]) -> None:
        self.outbox.enqueue(event_hash, message, event)
        thread = threading.Thread(
            target=self._drain_notifications,
            daemon=True,
        )
        thread.start()

    def _drain_notifications(self) -> None:
        if self.telegram_client is None:
            return
        self.outbox.drain_once(self.telegram_client.send_text)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self.file_lock:
            assert_jsonl_append_capacity(path, len(line.encode("utf-8")))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)


def serve_webhook(
    project_root: Path,
    host: str,
    port: int,
    secret: str | None,
    telegram_client: TelegramClient | None = None,
    notify_candidates: bool = False,
    require_secret: bool = False,
) -> None:
    if require_secret and not secret:
        raise RuntimeError("WEBHOOK_SECRET is required for public receiver mode")
    state_dir = project_root / "runtime_state" / "webhooks"
    event_file = state_dir / "tradingview_events.jsonl"
    candidate_file = state_dir / "taker_candidates.jsonl"
    rejected_file = state_dir / "rejected_events.jsonl"
    log_file = state_dir / "server.log"
    server = WebhookHTTPServer(
        (host, port),
        WebhookHandler,
        event_file,
        candidate_file,
        rejected_file,
        log_file,
        secret,
        telegram_client,
        notify_candidates,
    )
    _write_heartbeat(project_root, port, bool(secret), status="started")
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(project_root, port, bool(secret), heartbeat_stop),
        daemon=True,
    )
    heartbeat.start()
    if notify_candidates and telegram_client is not None:
        threading.Thread(target=server._drain_notifications, daemon=True).start()
    print(
        json.dumps(
            {
                "status": "listening",
                "local_url": f"http://{host}:{port}/tv-webhook",
                "health_url": f"http://{host}:{port}/health",
                "event_file": str(event_file),
                "candidate_file": str(candidate_file),
                "rejected_file": str(rejected_file),
                "secret_required": bool(secret),
                "candidate_notifications": notify_candidates,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        heartbeat_stop.set()
        _write_heartbeat(project_root, port, bool(secret), status="stopped")


def add_serve_webhook_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("serve-webhook", help="receive TradingView webhook alerts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--secret", default=None, help="optional shared secret expected in JSON")
    parser.add_argument("--require-secret", action="store_true", help="fail closed when no shared secret is configured")
    parser.add_argument(
        "--notify-candidates",
        action="store_true",
        help="send a Telegram test notice for accepted TV candidate events",
    )


def _content_length(value: str | None) -> int | None:
    if not value:
        return 0
    try:
        length = int(value)
    except ValueError:
        return 0
    if length < 0:
        return 0
    if length > 256_000:
        return None
    return length


def _valid_secret(payload: Any, secret: str) -> bool:
    if not isinstance(payload, dict):
        return False
    supplied = payload.get("secret") or payload.get("密钥")
    if not isinstance(supplied, str):
        return False
    return hmac.compare_digest(supplied, secret)


def _redact_secret(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    redacted = dict(payload)
    if "secret" in redacted:
        redacted["secret"] = "<redacted>"
    if "密钥" in redacted:
        redacted["密钥"] = "<redacted>"
    return redacted


def _load_candidate_hashes(path: Path) -> set[str]:
    hashes: set[str] = set()
    for payload in iter_jsonl_records(path, strict=True):
        event_hash = payload.get("event_hash")
        if isinstance(event_hash, str):
            hashes.add(event_hash)
    return hashes


def _write_heartbeat(project_root: Path, port: int, secret_required: bool, *, status: str = "running") -> None:
    path = project_root / "runtime_state" / "processes" / "webhook_heartbeat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "status": status,
        "pid": os.getpid(),
        "port": port,
        "secret_required": secret_required,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _heartbeat_loop(project_root: Path, port: int, secret_required: bool, stop: threading.Event) -> None:
    while not stop.wait(10):
        _write_heartbeat(project_root, port, secret_required)
