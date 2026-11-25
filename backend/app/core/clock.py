from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().display_timezone)


def today_local() -> date:
    return datetime.now(UTC).astimezone(local_tz()).date()


def local_date(v: datetime) -> date:
    return v.astimezone(local_tz()).date()
