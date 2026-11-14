"""UTC time helpers. All pipeline timestamps are UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def iso_utc(dt: datetime) -> str:
    """Format an aware datetime as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp that may use a trailing ``Z``.

    Returns ``None`` for blank/None input; raises ValueError for malformed input.
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def today_utc() -> date:
    """Current UTC calendar date."""
    return utc_now().date()
