"""Shared extraction contracts: windows, pages, file naming and NDJSON writing.

Design rules enforced here (see docs/phase2/03_SOURCES_AND_EXTRACTION.md and
06_STAGING_BRONZE.md):

* One JSON object per line, serialised with ``sort_keys=False`` so the source
  payload byte order is preserved as far as the API delivered it.
* Deterministic file names for a logical window so a retry overwrites the same
  object key in the internal stage instead of creating a second logical batch.
* The Python layer never cleans fields, deduplicates records, assigns keys or
  interprets source semantics.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# Source payloads larger than this are routed to the audit/oversize artifact
# instead of being written into staging; the record is never silently dropped.
MAX_RECORD_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class FetchWindow:
    """One bounded extraction window for a source/entity pair."""

    source_name: str
    entity_name: str
    window_start: str
    window_end: str
    mode: str  # full | incremental
    # Set only when resuming a capped incremental window. Adapters ignore it;
    # the extraction runner passes it as the first page cursor.
    resume_cursor: str | None = None

    @property
    def window_id(self) -> str:
        return stable_window_id(
            self.source_name, self.entity_name, self.window_start, self.window_end
        )


@dataclass(frozen=True)
class Page:
    """One API page of raw records plus pagination state."""

    records: list[dict[str, Any]]
    next_cursor: str | None
    request: dict[str, Any]
    records_seen: int


@dataclass
class ShardResult:
    """A completed NDJSON gzip shard ready for upload."""

    relative_path: str
    local_path: Path
    checksum: str
    size_bytes: int
    record_count: int


@dataclass
class WindowWriteResult:
    """Outcome of writing one window to disk."""

    shards: list[ShardResult] = field(default_factory=list)
    record_count: int = 0
    oversize_records: list[dict[str, Any]] = field(default_factory=list)
    last_cursor: str | None = None


def stable_window_id(
    source_name: str, entity_name: str, window_start: str, window_end: str
) -> str:
    """Stable 12-hex-character identifier for a logical extraction window."""
    material = f"{source_name}|{entity_name}|{window_start}|{window_end}".encode()
    return hashlib.sha256(material).hexdigest()[:12]


def batch_id_for(
    source_name: str, entity_name: str, window_start: str, window_end: str
) -> str:
    """Deterministic batch id so retrying a window cannot fork a second batch."""
    material = (
        f"{source_name}|{entity_name}|{window_start}|{window_end}|batch-v1".encode()
    )
    return "BATCH_" + hashlib.sha256(material).hexdigest()[:24].upper()


def relative_shard_path(
    source_name: str,
    entity_name: str,
    window_start: str,
    window_end: str,
    shard_number: int,
) -> str:
    """Deterministic stage-relative path for one shard of a window.

    Format (03_SOURCES_AND_EXTRACTION.md):
    ``<source>/<entity>/<window_start>_<window_end>/part-000001-<window_id>.ndjson.gz``
    """
    window_id = stable_window_id(source_name, entity_name, window_start, window_end)
    return (
        f"{source_name}/{entity_name}/{window_start}_{window_end}/"
        f"part-{shard_number:06d}-{window_id}.ndjson.gz"
    )


def ndjson_line(record: Mapping[str, Any]) -> bytes:
    """Serialise one raw object to a single NDJSON line (UTF-8, no newline)."""
    return json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_ndjson_gzip(path: Path, records: Iterable[Mapping[str, Any]]) -> tuple[str, int, int]:
    """Write records to a gzip NDJSON file atomically.

    Returns ``(checksum_sha256, size_bytes, record_count)``. The checksum is over
    the compressed bytes, so it can be used to verify a staged file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    count = 0
    try:
        with tmp_path.open("wb") as raw_handle:
            with gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as gzip_handle:
                for record in records:
                    gzip_handle.write(ndjson_line(record))
                    gzip_handle.write(b"\n")
                    count += 1
        checksum = sha256_file(tmp_path)
        tmp_path.replace(path)
        return checksum, path.stat().st_size, count
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def oversized(record: Mapping[str, Any]) -> bool:
    """True when the serialised record exceeds the safe VARIANT payload size."""
    return len(ndjson_line(record)) > MAX_RECORD_BYTES


def validate_date(value: str) -> str:
    """Validate an ISO date string (raises ValueError when malformed)."""
    return date.fromisoformat(value).isoformat()


_BATCH_ID_RE = re.compile(r"^BATCH_[0-9A-F]{24}$")
_STAGE_PATH_RE = re.compile(
    r"^[a-z0-9_]+/[a-z0-9_]+/\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}/"
    r"part-\d{6}-[0-9a-f]{12}\.ndjson\.gz$"
)


def validate_batch_id(value: str) -> str:
    if not _BATCH_ID_RE.match(value):
        raise ValueError(f"Invalid batch id: {value!r}")
    return value


def validate_stage_path(value: str) -> str:
    """Reject anything that is not a path produced by ``relative_shard_path``."""
    if not _STAGE_PATH_RE.match(value):
        raise ValueError(f"Invalid stage path: {value!r}")
    return value


def merge_oversize(oversize: list[dict[str, Any]], record: Mapping[str, Any]) -> None:
    """Record an oversize payload reference without the payload body.

    Keeping only identity/hash metadata prevents a giant record from bloating
    audit storage while still making the rejection visible.
    """
    serialised = ndjson_line(record)
    oversize.append(
        {
            "record_sha256": hashlib.sha256(serialised).hexdigest(),
            "record_bytes": len(serialised),
            "top_level_keys": sorted(str(key) for key in record.keys())[:50],
        }
    )
