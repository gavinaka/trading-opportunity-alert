from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_AUTHORITY_FILES = (
    "AGENTS.md",
    "scoring/chart_methodology.md",
    "risk/risk_checklist.md",
    "risk/floating_defense.md",
    "risk/entry_exit_rules.md",
    "execution/entry_models.md",
    "execution/taker_history.md",
    "execution/maker_execution.md",
    "constitution/cannot_do_mapping.md",
    "constitution/trading_constitution.md",
)


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    trading_system_root: Path
    slot: str
    trigger_win_rate: float
    trigger_operator: str
    telegram_bot_token_env: str
    telegram_chat_id_env: str
    webhook_secret_env: str
    send_dry_run_by_default: bool
    max_message_chars: int
    authority_files: tuple[str, ...]

    @property
    def telegram_bot_token(self) -> str | None:
        return os.getenv(self.telegram_bot_token_env)

    @property
    def telegram_chat_id(self) -> str | None:
        return os.getenv(self.telegram_chat_id_env)

    @property
    def webhook_secret(self) -> str | None:
        return os.getenv(self.webhook_secret_env)


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config(path: Path | None = None, env_file: Path | None = None) -> AppConfig:
    project_root = Path.cwd().resolve()
    if env_file is None:
        env_file = project_root / ".env"
    load_env_file(env_file)

    payload: dict[str, Any] = {}
    if path is not None:
        payload = json.loads(path.read_text(encoding="utf-8"))

    trading_system_root = Path(
        payload.get("trading_system_root", "C:<REPO_ROOT>")
    ).resolve()
    slot = str(payload.get("slot", "midday"))
    if slot not in {"morning", "midday", "evening"}:
        raise ValueError("slot must be one of: morning, midday, evening")

    operator = str(payload.get("trigger_operator", "gte")).lower()
    if operator not in {"gte", "gt"}:
        raise ValueError("trigger_operator must be 'gte' or 'gt'")

    authority = payload.get("authority_files", DEFAULT_AUTHORITY_FILES)
    if not isinstance(authority, list | tuple):
        raise ValueError("authority_files must be a list")

    return AppConfig(
        project_root=project_root,
        trading_system_root=trading_system_root,
        slot=slot,
        trigger_win_rate=float(payload.get("trigger_win_rate", 75)),
        trigger_operator=operator,
        telegram_bot_token_env=str(payload.get("telegram_bot_token_env", "TELEGRAM_BOT_TOKEN")),
        telegram_chat_id_env=str(payload.get("telegram_chat_id_env", "TELEGRAM_CHAT_ID")),
        webhook_secret_env=str(payload.get("webhook_secret_env", "WEBHOOK_SECRET")),
        send_dry_run_by_default=bool(payload.get("send_dry_run_by_default", True)),
        max_message_chars=int(payload.get("max_message_chars", 3900)),
        authority_files=tuple(str(item) for item in authority),
    )
