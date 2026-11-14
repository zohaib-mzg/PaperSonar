"""Time helper tests."""

from datetime import UTC, datetime, timezone

import pytest

from papersonar.timeutil import iso_utc, parse_iso_utc, utc_now


def test_utc_now_is_aware():
    assert utc_now().tzinfo is not None


def test_iso_utc_format():
    dt = datetime(2026, 11, 14, 10, 30, 5, tzinfo=UTC)
    assert iso_utc(dt) == "2026-11-14T10:30:05Z"


def test_iso_utc_converts_non_utc():
    from datetime import timedelta

    dt = datetime(2026, 11, 14, 10, 30, 5, tzinfo=UTC)
    shifted = timezone(timedelta(hours=2))
    assert iso_utc(dt.astimezone(shifted)) == "2026-11-14T10:30:05Z"


def test_parse_iso_utc_z_suffix():
    dt = parse_iso_utc("2026-11-14T10:30:05Z")
    assert dt is not None
    assert dt.year == 2026 and dt.minute == 30
    assert dt.tzinfo is not None


def test_parse_iso_utc_blank_none():
    assert parse_iso_utc(None) is None
    assert parse_iso_utc("   ") is None


def test_parse_iso_utc_malformed_raises():
    with pytest.raises(ValueError):
        parse_iso_utc("14/11/2026")
