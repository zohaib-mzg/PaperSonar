"""Unit tests for the extraction contract (no network, no Snowflake)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from extract.base import (
    FetchWindow,
    batch_id_for,
    merge_oversize,
    ndjson_line,
    oversized,
    relative_shard_path,
    sha256_file,
    stable_window_id,
    validate_batch_id,
    validate_stage_path,
    write_ndjson_gzip,
)


def test_window_and_batch_ids_are_deterministic() -> None:
    first = batch_id_for("openalex", "work", "2024-01-01", "2024-01-31")
    second = batch_id_for("openalex", "work", "2024-01-01", "2024-01-31")
    other = batch_id_for("openalex", "work", "2024-02-01", "2024-02-29")
    assert first == second
    assert first != other
    assert validate_batch_id(first) == first
    assert len(stable_window_id("crossref", "work", "2024-01-01", "2024-01-01")) == 12


def test_shard_path_matches_contract() -> None:
    path = relative_shard_path("openalex", "work", "2024-01-01", "2024-12-31", 1)
    assert path.startswith("openalex/work/2024-01-01_2024-12-31/part-000001-")
    assert path.endswith(".ndjson.gz")
    assert validate_stage_path(path) == path
    with pytest.raises(ValueError):
        validate_stage_path("../../etc/passwd")


def test_ndjson_gzip_roundtrip_and_checksum(tmp_path: Path) -> None:
    target = tmp_path / "part.ndjson.gz"
    records = [{"id": "https://openalex.org/W1", "nested": {"b": 2, "a": 1}}, {"id": "W2"}]
    checksum, size, count = write_ndjson_gzip(target, records)
    assert count == 2
    assert size == target.stat().st_size
    assert checksum == sha256_file(target)
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    assert lines == records
    assert list(lines[0].keys()) == ["id", "nested"]


def test_ndjson_line_is_single_line_and_raw() -> None:
    line = ndjson_line({"title": "A\nB", "unicode": "a"})
    assert b"\n" not in line
    assert json.loads(line) == {"title": "A\nB", "unicode": "a"}


def test_oversized_records_are_detected_without_payload() -> None:
    record = {"blob": "x" * 100}
    assert not oversized(record)
    from extract import base

    original = base.MAX_RECORD_BYTES
    try:
        base.MAX_RECORD_BYTES = 10
        collected: list[dict] = []
        merge_oversize(collected, record)
        assert collected[0]["record_bytes"] > 10
        assert "x" * 100 not in json.dumps(collected)
    finally:
        base.MAX_RECORD_BYTES = original


def test_fetch_window_exposes_stable_id() -> None:
    window = FetchWindow("arxiv", "record", "2024-01-01", "2024-12-31", "full")
    assert window.window_id == stable_window_id(
        "arxiv", "record", "2024-01-01", "2024-12-31"
    )
