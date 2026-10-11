from __future__ import annotations

from dataclasses import dataclass

import requests


class TelegramError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramClient:
    bot_token: str
    chat_id: str
    max_message_chars: int = 3900

    def send_text(self, text: str) -> list[dict]:
        chunks = split_message(text, self.max_message_chars)
        responses: list[dict] = []
        for chunk in chunks:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "link_preview_options": {"is_disabled": True},
                },
                timeout=30,
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise TelegramError(f"Telegram returned non-JSON response: {response.text}") from exc
            if response.status_code >= 400 or not payload.get("ok"):
                raise TelegramError(f"Telegram sendMessage failed: {payload}")
            responses.append(payload)
        return responses


def split_message(text: str, limit: int) -> list[str]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current).rstrip())
                current = []
                current_len = 0
            for index in range(0, len(line), limit):
                chunks.append(line[index : index + limit].rstrip())
            continue
        if current_len + len(line) > limit:
            chunks.append("".join(current).rstrip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current).rstrip())
    return [chunk for chunk in chunks if chunk]

