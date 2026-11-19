"""Window planning: full backfill chunks and incremental overlap windows.

A window is the unit of resumability. The deterministic batch id derived from a
window means a retried job reuses the same logical batch; only the watermark
advancement (inside Snowflake) decides whether the window is complete.
"""

from __future__ import annotations

from datetime import date, timedelta

from extract.base import FetchWindow
from runner.config import ConfigurationError, Settings

BACKFILL_MAX_WINDOWS = 60


def plan_windows(
    settings: Settings,
    source_name: str,
    mode: str,
    from_date: str | None = None,
    until_date: str | None = None,
    today: date | None = None,
    watermark_end: str | None = None,
) -> list[FetchWindow]:
    """Return the bounded windows for one source and run mode.

    ``mode`` is ``full`` or ``incremental``. Explicit dates override the
    configured backfill start / overlap policy. For incremental runs, a
    published watermark makes the runner catch up from the last committed
    window instead of assuming yesterday's schedule succeeded.
    """
    if mode not in ("full", "incremental"):
        raise ConfigurationError(f"Unknown extraction mode {mode!r}; use full or incremental")
    source = settings.require_source(source_name)
    current = today or date.today()
    start_override = _date_or_none(from_date)
    end_override = _date_or_none(until_date) or current

    if source_name == "openalex":
        return _openalex_windows(
            settings, source, mode, start_override, end_override, current, watermark_end
        )
    if source_name == "crossref":
        return _daily_windows(
            settings, source_name, source, mode, start_override, end_override, current, watermark_end
        )
    if source_name == "datacite":
        return _daily_windows(
            settings, source_name, source, mode, start_override, end_override, current, watermark_end
        )
    if source_name in ("arxiv", "zenodo"):
        return _single_window(
            source_name, source, mode, start_override, end_override, current, watermark_end
        )
    raise ConfigurationError(f"No window planner for source {source_name!r}")


def _openalex_windows(
    settings: Settings,
    source,
    mode: str,
    start_override: date | None,
    end_override: date,
    today: date,
    watermark_end: str | None,
) -> list[FetchWindow]:
    if mode == "full":
        start = start_override or date.fromisoformat(source.backfill_from)
        if start > end_override:
            raise ConfigurationError(
                f"Window start {start} is after end {end_override}"
            )
        windows: list[FetchWindow] = []
        for year in range(start.year, end_override.year + 1):
            window_start = max(date(year, 1, 1), start)
            window_end = min(date(year, 12, 31), end_override)
            windows.append(
                FetchWindow(
                    "openalex",
                    "work",
                    window_start.isoformat(),
                    window_end.isoformat(),
                    mode,
                )
            )
        return windows[: settings.max_windows_per_run]
    start = _incremental_start(source, end_override, start_override, watermark_end)
    return [FetchWindow("openalex", "work", start.isoformat(), end_override.isoformat(), mode)]


def _daily_windows(
    settings: Settings,
    source_name: str,
    source,
    mode: str,
    start_override: date | None,
    end_override: date,
    today: date,
    watermark_end: str | None,
) -> list[FetchWindow]:
    if mode == "full":
        start = start_override or date.fromisoformat(source.backfill_from)
        days = _days(start, end_override)
        return [
            FetchWindow(source_name, source.entity, day, day, mode)
            for day in days[:BACKFILL_MAX_WINDOWS]
        ]
    start = _incremental_start(source, end_override, start_override, watermark_end)
    days = _days(start, end_override)
    return [
        FetchWindow(source_name, source.entity, day, day, mode)
        for day in days[: settings.max_windows_per_run]
    ]


def _single_window(
    source_name: str,
    source,
    mode: str,
    start_override: date | None,
    end_override: date,
    today: date,
    watermark_end: str | None,
) -> list[FetchWindow]:
    if mode == "full":
        start = start_override or date.fromisoformat(source.backfill_from)
    else:
        start = _incremental_start(source, end_override, start_override, watermark_end)
    return [FetchWindow(source_name, source.entity, start.isoformat(), end_override.isoformat(), mode)]


def _incremental_start(
    source,
    end_override: date,
    start_override: date | None,
    watermark_end: str | None,
) -> date:
    """Start at the published watermark minus overlap, never before backfill."""
    if start_override is not None:
        return start_override
    base = end_override
    if watermark_end:
        try:
            published = date.fromisoformat(watermark_end[:10])
        except ValueError:
            published = None
        if published is not None:
            base = min(published, end_override)
    start = base - timedelta(days=source.overlap_days)
    backfill = date.fromisoformat(source.backfill_from)
    return max(start, backfill)


def _days(start: date, end: date) -> list[str]:
    if start > end:
        raise ConfigurationError(f"Window start {start} is after end {end}")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
