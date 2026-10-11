from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    SHANGHAI = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


def local_now() -> datetime:
    return datetime.now(SHANGHAI)


def local_date() -> str:
    return local_now().strftime("%Y-%m-%d")


def local_timestamp() -> str:
    return local_now().isoformat(timespec="seconds")
