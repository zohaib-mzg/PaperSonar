"""End-to-end dry-run of the extraction runner (local files only)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from extract.base import FetchWindow, Page, batch_id_for
from extract.http import RetryableHttpError
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
{max_records_line}    filter: ""
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


class ExpiringOaiAdapter:
    """OAI adapter that expires its token twice before completing."""

    def __init__(self, progress: dict[str, Any]) -> None:
        self.progress = progress
        self.windows: list[FetchWindow] = []
        self.cursors: list[str | None] = []

    def iter_pages(self, http: Any, window: FetchWindow, cursor: str | None = None) -> Any:
        attempt = len(self.windows) + 1
        self.windows.append(window)
        self.cursors.append(cursor)
        datestamp = f"2026-11-14T10:00:0{attempt}Z"
        yield Page(
            records=[{"identifier": f"oai:{attempt}", "datestamp": datestamp}],
            next_cursor=f"token-{attempt}",
            request={},
            records_seen=1,
        )
        if attempt <= 2:
            self.progress["last_datestamp"] = datestamp
            raise RetryableHttpError("OAI-PMH resumption token rejected (HTTP 422)")


class FakeSnowflake:
    def __init__(self, batch: dict[str, Any] | None = None) -> None:
        self.batch = batch
        self.registered: dict[str, Any] | None = None
        self.progress: list[tuple[str | None, int, int]] = []
        self.progress_capped: list[bool] = []
        self.manifests: list[dict[str, Any]] = []
        self.loaded: list[tuple[int, int]] = []
        self.loaded_capped: list[bool] = []
        self.failed: str | None = None
        self.cleared: list[tuple[str, str]] = []
        self.puts: list[tuple[str, str]] = []
        self.oversize: list[dict[str, Any]] = []

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        return self.batch

    def register_batch(self, **kwargs: Any) -> None:
        self.registered = kwargs

    def update_batch_progress(
        self,
        batch_id: str,
        cursor: str | None,
        file_count: int,
        record_count: int,
        is_capped: bool = False,
    ) -> None:
        self.progress.append((cursor, file_count, record_count))
        self.progress_capped.append(is_capped)

    def mark_batch_loaded(
        self, batch_id: str, file_count: int, record_count: int, is_capped: bool = False
    ) -> None:
        self.loaded.append((file_count, record_count))
        self.loaded_capped.append(is_capped)

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


def _settings(tmp_path: Path, *, max_records: int | None = None) -> Settings:
    path = tmp_path / "sources.yml"
    max_records_line = f"    max_records: {max_records}\n" if max_records is not None else ""
    path.write_text(
        CONFIG.format(
            raw_dir=(tmp_path / "raw").as_posix(), max_records_line=max_records_line
        ),
        encoding="utf-8",
    )
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


def test_max_records_caps_real_run_and_keeps_first_unread_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_records=3)
    adapter = FakeAdapter(
        [
            Page(
                records=[{"id": "W1"}, {"id": "W2"}],
                next_cursor="p2",
                request={"params": {"cursor": "start"}},
                records_seen=2,
            ),
            Page(
                records=[{"id": "W3"}, {"id": "W4"}],
                next_cursor="p3",
                request={"params": {"cursor": "p2"}},
                records_seen=2,
            ),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-01-02", "incremental")
    snowflake = FakeSnowflake()

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert report.status == "loaded"
    assert report.record_limit == 3
    assert report.record_count == 3
    assert report.file_count == 1
    assert report.capped is True
    assert report.cap_cursor == "p2"
    assert adapter.calls == [None]
    assert sum(item["record_count"] for item in snowflake.manifests) == 3
    assert snowflake.manifests[-1]["cursor_end"] == "p2"
    assert snowflake.progress[-1] == ("p2", 1, 3)
    assert snowflake.progress_capped[-1] is True
    assert snowflake.loaded == [(1, 3)]
    assert snowflake.loaded_capped == [True]
    local = settings.raw_dir / report.shards[0]["file"]
    with gzip.open(local, "rt", encoding="utf-8") as handle:
        assert [json.loads(line) for line in handle] == [
            {"id": "W1"},
            {"id": "W2"},
            {"id": "W3"},
        ]


def test_capped_published_batch_resumes_from_persisted_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_records=3)
    adapter = FakeAdapter(
        [
            Page(
                records=[{"id": "W4"}],
                next_cursor=None,
                request={"params": {"cursor": "p2"}},
                records_seen=1,
            )
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow(
        "openalex", "work", "2024-01-01", "2024-01-02", "incremental", resume_cursor="p2"
    )
    snowflake = FakeSnowflake(
        {
            "BATCH_ID": "batch",
            "SOURCE_NAME": "openalex",
            "ENTITY_NAME": "work",
            "STATUS": "PUBLISHED",
            "CURSOR_END": "p2",
            "FILE_COUNT": 1,
            "RECORD_COUNT": 3,
            "IS_CAPPED": True,
        }
    )

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert adapter.calls == ["p2"]
    assert report.status == "loaded"
    assert report.record_count == 4
    assert report.capped is False
    assert snowflake.cleared == []
    assert snowflake.registered["cursor_start"] == "p2"


def test_max_records_at_page_boundary_keeps_next_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_records=2)
    adapter = FakeAdapter(
        [
            Page(
                records=[{"id": "W1"}, {"id": "W2"}],
                next_cursor="p2",
                request={"params": {"cursor": "start"}},
                records_seen=2,
            ),
            Page(
                records=[{"id": "W3"}],
                next_cursor=None,
                request={"params": {"cursor": "p2"}},
                records_seen=1,
            ),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-01-02", "incremental")
    snowflake = FakeSnowflake()

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert report.capped is True
    assert report.cap_cursor == "p2"
    assert report.record_count == 2
    assert snowflake.progress[-1] == ("p2", 1, 2)
    assert snowflake.loaded_capped == [True]


def test_exact_max_records_with_no_next_page_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_records=3)
    adapter = FakeAdapter(
        [
            Page(
                records=[{"id": "W1"}, {"id": "W2"}],
                next_cursor="p2",
                request={"params": {"cursor": "start"}},
                records_seen=2,
            ),
            Page(
                records=[{"id": "W3"}],
                next_cursor=None,
                request={"params": {"cursor": "p2"}},
                records_seen=1,
            ),
        ]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-01-02", "incremental")
    snowflake = FakeSnowflake()

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert report.capped is False
    assert report.cap_cursor is None
    assert report.record_count == 3
    assert snowflake.progress[-1] == (None, 1, 3)
    assert snowflake.progress_capped[-1] is False
    assert snowflake.loaded_capped == [False]


def test_interrupted_capped_batch_is_finalized_without_refetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_records=3)
    adapter = FakeAdapter(
        [Page(records=[{"id": "W4"}], next_cursor=None, request={}, records_seen=1)]
    )
    monkeypatch.setattr(extract_run, "build_adapter", lambda *args, **kwargs: adapter)
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-01-02", "incremental")
    snowflake = FakeSnowflake(
        {
            "STATUS": "FAILED",
            "CURSOR_END": "p2",
            "FILE_COUNT": 1,
            "RECORD_COUNT": 3,
            "IS_CAPPED": True,
        }
    )

    report = extract_run.run_extraction(
        settings, "openalex", window, execute_task=False, client=snowflake
    )

    assert adapter.calls == []
    assert report.status == "loaded"
    assert report.capped is True
    assert report.cap_cursor == "p2"
    assert snowflake.loaded == [(1, 3)]
    assert snowflake.loaded_capped == [True]


def test_repeated_oai_token_expiry_resumes_from_latest_datestamp() -> None:
    progress: dict[str, Any] = {
        "last_datestamp": None,
        "seen_ids": set(),
        "restarted": False,
    }
    adapter = ExpiringOaiAdapter(progress)
    window = FetchWindow(
        "zenodo", "record", "2026-11-14", "2026-11-21", "incremental", resume_cursor="expired"
    )

    pages = list(
        extract_run._pages_with_restart(
            adapter, object(), window, "expired", "BATCH_OAI", progress
        )
    )

    assert len(pages) == 3
    assert adapter.cursors == ["expired", None, None]
    assert adapter.windows[1].resume_from == "2026-11-14T10:00:01Z"
    assert adapter.windows[2].resume_from == "2026-11-14T10:00:02Z"
    assert progress["restarted"] is True
