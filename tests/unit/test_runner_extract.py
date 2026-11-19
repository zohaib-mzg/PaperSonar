"""End-to-end dry-run of the extraction runner (local files only)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from extract.base import FetchWindow, Page, batch_id_for
from runner import extract_run
from runner.config import Settings

CONFIG = """
version: 1
runtime:
  target_file_bytes: 4096
  raw_dir: "{raw_dir}"
  max_windows_per_run: 10
sources:
  openalex:
    enabled: true
    entity: work
    page_size: 100
    filter: ""
    overlap_days: 3
    backfill_from: "2024-01-01"
"""


class FakeAdapter:
    def __init__(self, pages: list[Page]) -> None:
        self._pages = pages
        self.calls: list[str | None] = []

    def iter_pages(self, http: Any, window: FetchWindow, cursor: str | None = None) -> Any:
        self.calls.append(cursor)
        yield from self._pages


class FakeSnowflake:
    def __init__(self, batch: dict[str, Any] | None = None) -> None:
        self.batch = batch
        self.registered: dict[str, Any] | None = None
        self.progress: list[tuple[str | None, int, int]] = []
        self.manifests: list[dict[str, Any]] = []
        self.loaded: list[tuple[int, int]] = []
        self.failed: str | None = None
        self.cleared: list[tuple[str, str]] = []
        self.puts: list[tuple[str, str]] = []
        self.oversize: list[dict[str, Any]] = []

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        return self.batch

    def register_batch(self, **kwargs: Any) -> None:
        self.registered = kwargs

    def update_batch_progress(
        self, batch_id: str, cursor: str | None, file_count: int, record_count: int
    ) -> None:
        self.progress.append((cursor, file_count, record_count))

    def mark_batch_loaded(self, batch_id: str, file_count: int, record_count: int) -> None:
        self.loaded.append((file_count, record_count))

    def mark_batch_failed(self, batch_id: str, error_summary: str) -> None:
        self.failed = error_summary

    def clear_batch_outputs(self, batch_id: str, stage_dir: str) -> None:
        self.cleared.append((batch_id, stage_dir))

    def put_file(self, local_path: Path, stage_dir: str) -> dict[str, Any]:
        self.puts.append((str(local_path), stage_dir))
        return {
            "target": local_path.name,
            "source_size": local_path.stat().st_size,
            "status": "UPLOADED",
        }

    def verify_staged_file(
        self,
        stage_dir: str,
        file_name: str,
        expected_size: int,
        upload: dict[str, Any] | None = None,
    ) -> None:
        return None

    def register_manifest(self, **kwargs: Any) -> None:
        self.manifests.append(kwargs)

    def register_oversize(self, **kwargs: Any) -> None:
        self.oversize.append(kwargs)


def _settings(tmp_path: Path) -> Settings:
    path = tmp_path / "sources.yml"
    path.write_text(CONFIG.format(raw_dir=(tmp_path / "raw").as_posix()), encoding="utf-8")
    return Settings.from_env({}, config_path=str(path))


def test_dry_run_writes_raw_ndjson_without_snowflake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter(
        [
            Page(records=[{"id": "W1"}, {"id": "W2"}], next_cursor="next", request={}, records_seen=2),
            Page(records=[{"id": "W3"}], next_cursor=None, request={}, records_seen=1),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")

    report = extract_run.run_extraction(settings, "openalex", window, dry_run=True)

    assert report.status == "extracted"
    assert report.record_count == 3
    assert report.file_count == 1
    assert report.task_triggered is False
    local = settings.raw_dir / report.shards[0]["file"]
    assert local.exists()
    with gzip.open(local, "rt", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    assert records == [{"id": "W1"}, {"id": "W2"}, {"id": "W3"}]
    assert adapter.calls == [None]


def test_dry_run_rolls_shards_at_target_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    big = "x" * 5000
    adapter = FakeAdapter(
        [
            Page(records=[{"id": "W1", "blob": big}], next_cursor="n1", request={}, records_seen=1),
            Page(records=[{"id": "W2", "blob": big}], next_cursor=None, request={}, records_seen=1),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")

    report = extract_run.run_extraction(settings, "openalex", window, dry_run=True)

    assert report.file_count == 2
    assert report.record_count == 2
    assert report.shards[0]["file"].endswith("part-000001-" + window.window_id + ".ndjson.gz")
    assert report.shards[1]["file"].endswith("part-000002-" + window.window_id + ".ndjson.gz")


def test_oversized_record_is_counted_not_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter(
        [Page(records=[{"id": "W1", "blob": "x" * 100}], next_cursor=None, request={}, records_seen=1)]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    from extract import base

    monkeypatch.setattr(base, "MAX_RECORD_BYTES", 10)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")

    report = extract_run.run_extraction(settings, "openalex", window, dry_run=True)

    assert report.oversize_count == 1
    assert report.record_count == 0
    assert report.file_count == 0


def test_resume_continues_from_cursor_and_keeps_prior_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter(
        [Page(records=[{"id": "W3"}], next_cursor=None, request={}, records_seen=1)]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")
    snowflake = FakeSnowflake(
        {
            "STATUS": "FAILED",
            "CURSOR_END": "resume-cursor",
            "FILE_COUNT": 1,
            "RECORD_COUNT": 2,
        }
    )

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert adapter.calls == ["resume-cursor"]
    assert report.record_count == 3
    assert report.file_count == 2
    assert report.shards[0]["file"].endswith("part-000002-" + window.window_id + ".ndjson.gz")
    assert snowflake.registered is not None
    assert snowflake.registered["cursor_start"] == "resume-cursor"
    assert snowflake.manifests[0]["cursor_start"] == "resume-cursor"
    assert snowflake.manifests[0]["cursor_end"] is None
    assert snowflake.progress[-1] == (None, 2, 3)
    assert snowflake.loaded == [(2, 3)]
    assert snowflake.cleared == []


def test_exhausted_batch_is_finalized_without_refetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter([])
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")
    snowflake = FakeSnowflake(
        {
            "STATUS": "FAILED",
            "CURSOR_END": None,
            "FILE_COUNT": 2,
            "RECORD_COUNT": 10,
        }
    )

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert adapter.calls == []
    assert report.status == "loaded"
    assert report.record_count == 10
    assert report.file_count == 2
    assert snowflake.loaded == [(2, 10)]


def test_force_restarts_a_loaded_batch_from_a_clean_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter(
        [Page(records=[{"id": "W1"}], next_cursor=None, request={}, records_seen=1)]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")
    batch_id = batch_id_for("openalex", "work", window.window_start, window.window_end)
    snowflake = FakeSnowflake(
        {
            "STATUS": "LOADED",
            "CURSOR_END": "stale-cursor",
            "FILE_COUNT": 5,
            "RECORD_COUNT": 500,
        }
    )

    report = extract_run.run_extraction(
        settings, "openalex", window, force=True, execute_task=False, client=snowflake
    )

    assert adapter.calls == [None]
    assert snowflake.cleared == [
        (batch_id, "openalex/work/2024-01-01_2024-12-31")
    ]
    assert snowflake.registered is not None
    assert snowflake.registered["cursor_start"] is None
    assert report.record_count == 1
    assert report.file_count == 1
    assert snowflake.loaded == [(1, 1)]


def test_shard_cursor_end_is_the_next_unread_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    big = "x" * 5000
    adapter = FakeAdapter(
        [
            Page(records=[{"id": "W1", "blob": big}], next_cursor="n1", request={}, records_seen=1),
            Page(records=[{"id": "W2", "blob": big}], next_cursor=None, request={}, records_seen=1),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")
    snowflake = FakeSnowflake()

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert report.file_count == 2
    assert snowflake.manifests[0]["cursor_start"] is None
    assert snowflake.manifests[0]["cursor_end"] == "n1"
    assert snowflake.manifests[1]["cursor_start"] == "n1"
    assert snowflake.manifests[1]["cursor_end"] is None


def test_empty_window_loads_zero_rows_and_exits_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    adapter = FakeAdapter(
        [Page(records=[], next_cursor=None, request={}, records_seen=0)]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-01-02", "incremental")
    snowflake = FakeSnowflake()

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert adapter.calls == [None]
    assert report.status == "loaded"
    assert report.record_count == 0
    assert report.file_count == 0
    assert report.shards == []
    assert snowflake.manifests == []
    assert snowflake.progress[-1] == (None, 0, 0)
    assert snowflake.loaded == [(0, 0)]
