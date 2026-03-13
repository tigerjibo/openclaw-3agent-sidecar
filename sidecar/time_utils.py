from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    Naive values are interpreted as UTC for backward compatibility with the
    existing SQLite timestamp strings and older test fixtures.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_utc_datetime(value: Any) -> datetime | None:
    """Parse supported datetime representations as timezone-aware UTC."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return ensure_utc(datetime.strptime(text, pattern))
        except ValueError:
            continue
    try:
        return ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def utc_isoformat(value: datetime) -> str:
    """Serialize a datetime as an ISO string while preserving legacy shape.

    The returned string intentionally omits the timezone suffix so existing API
    payloads and tests keep their current format, while internal calculations
    remain timezone-aware.
    """
    return ensure_utc(value).replace(tzinfo=None).isoformat()