"""Runner configuration and window-planning tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from extract.base import FetchWindow
from runner.config import ConfigurationError, Settings
from runner.windows import plan_windows

CONFIG = """
version: 1
runtime:
  target_file_bytes: 1048576
  raw_dir: data/extract
  max_windows_per_run: 3
sources:
  openalex:
    enabled: true
    entity: work
    page_size: 100
    filter: "topics.id:T1"
    overlap_days: 3
    backfill_from: "2022-01-01"
    total_timeout_seconds: 900
  crossref:
    enabled: true
    entity: work
    page_size: 1000
    max_records: 20000
    overlap_days: 2
    backfill_from: "2024-01-01"
  arxiv:
    enabled: false
    entity: record
    overlap_days: 7
    backfill_from: "2024-01-01"
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "sources.yml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def test_settings_load_sources_and_runtime(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    assert settings.enabled_sources() == ["openalex", "crossref"]
    assert settings.sources["openalex"].page_size == 100
    assert settings.sources["openalex"].adapter["filter"] == "topics.id:T1"
    assert settings.target_file_bytes == 1_048_576
    assert settings.raw_dir == Path("data/extract")
    assert settings.sources["openalex"].total_timeout_seconds == 900.0
    assert "total_timeout_seconds" not in settings.sources["openalex"].adapter
    assert settings.sources["crossref"].max_records == 20_000
    assert "max_records" not in settings.sources["crossref"].adapter


def test_missing_snowflake_lists_variable_names_only(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    with pytest.raises(ConfigurationError) as excinfo:
        settings.require_snowflake()
    message = str(excinfo.value)
    assert "SNOWFLAKE_ACCOUNT" in message
    assert "secret-value" not in message


def test_non_snowflake_target_is_rejected(config_path: Path) -> None:
    settings = Settings.from_env({"PAPERSONAR_TARGET": "sqlite"}, config_path=str(config_path))
    with pytest.raises(ConfigurationError):
        settings.require_snowflake()


def test_disabled_source_cannot_be_planned(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    with pytest.raises(ConfigurationError):
        plan_windows(settings, "arxiv", "incremental")


def test_openalex_full_is_chunked_by_year_and_bounded(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(settings, "openalex", "full", today=date(2024, 6, 1))
    assert len(windows) == 3
    assert windows[0] == FetchWindow("openalex", "work", "2022-01-01", "2022-12-31", "full")
    assert windows[-1].window_start == "2024-01-01"


def test_openalex_full_honors_explicit_dates(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "openalex",
        "full",
        from_date="2026-11-17",
        until_date="2026-11-18",
        today=date(2026, 11, 19),
    )
    assert windows == [
        FetchWindow("openalex", "work", "2026-11-17", "2026-11-18", "full")
    ]


def test_crossref_incremental_uses_overlap(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(settings, "crossref", "incremental", today=date(2024, 1, 10))
    assert windows == [
        FetchWindow("crossref", "work", day, day, "incremental")
        for day in ("2024-01-08", "2024-01-09", "2024-01-10")
    ]


def test_explicit_dates_override_config(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "crossref",
        "full",
        from_date="2024-02-01",
        until_date="2024-02-03",
        today=date(2024, 6, 1),
    )
    assert [window.window_start for window in windows] == [
        "2024-02-01",
        "2024-02-02",
        "2024-02-03",
    ]


def test_incremental_uses_published_watermark_over_overlap(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "openalex",
        "incremental",
        today=date(2024, 1, 10),
        watermark_end="2024-01-04",
    )
    assert windows == [
        FetchWindow("openalex", "work", "2024-01-01", "2024-01-10", "incremental")
    ]


def test_incremental_catches_up_after_a_gap(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "crossref",
        "incremental",
        today=date(2024, 1, 10),
        watermark_end="2024-01-08",
    )
    assert [window.window_start for window in windows] == [
        "2024-01-06",
        "2024-01-07",
        "2024-01-08",
    ]


def test_capped_watermark_replays_exact_window_and_cursor(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "crossref",
        "incremental",
        today=date(2024, 1, 20),
        watermark_state={
            "WATERMARK_VALUE": "2024-01-08",
            "WINDOW_START": "2024-01-08",
            "WINDOW_END": "2024-01-08",
            "CURSOR": "first-unread-cursor",
            "STATUS": "CAPPED",
        },
    )
    assert windows == [
        FetchWindow(
            "crossref",
            "work",
            "2024-01-08",
            "2024-01-08",
            "incremental",
            resume_cursor="first-unread-cursor",
        )
    ]


def test_non_positive_max_records_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text(CONFIG.replace("max_records: 20000", "max_records: 0"), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="max_records"):
        Settings.from_env({}, config_path=str(path))


def test_future_watermark_is_clamped_to_today(config_path: Path) -> None:
    settings = Settings.from_env({}, config_path=str(config_path))
    windows = plan_windows(
        settings,
        "openalex",
        "incremental",
        today=date(2024, 1, 10),
        watermark_end="2024-02-01",
    )
    assert windows == [
        FetchWindow("openalex", "work", "2024-01-07", "2024-01-10", "incremental")
    ]
