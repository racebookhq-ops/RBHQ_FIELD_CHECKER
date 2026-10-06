"""Date helpers. The racing day is an Australian calendar day, not UTC."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

RACING_TZ = ZoneInfo("Australia/Sydney")


def now_local() -> datetime:
    return datetime.now(RACING_TZ)


def today_local() -> date:
    return now_local().date()


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


def combine_local(day: date, hhmm: str) -> str | None:
    """Turn a meeting date + a '12:34' style time into a local ISO timestamp.

    Returns None when the time can't be understood, rather than guessing.
    """
    if not hhmm:
        return None
    text = hhmm.strip().upper().replace(".", ":")
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return datetime(
            day.year, day.month, day.day,
            parsed.hour, parsed.minute, parsed.second,
            tzinfo=RACING_TZ,
        ).isoformat()
    return None


def date_range(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]
