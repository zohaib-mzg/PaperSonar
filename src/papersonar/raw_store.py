"""Raw layer: immutable payload + manifest persistence.

Every fetched page/batch is stored twice before it counts: a byte-exact payload
in the warehouse raw stage (durable copy) and a local development mirror, plus
a manifest recording retrieval metadata, checksums and redacted request
descriptors. Raw batches are append-only: re-fetching the same page creates a
new batch/observation rather than overwriting evidence.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from papersonar.timeutil import iso_utc
from papersonar.warehouse.adapter import Warehouse
from papersonar.warehouse.state_store import RawBatch, StateStore

logger = logging.getLogger(__name__)

_RAW_STAGE_ROOT = "PROJECT_OPS.RAW_STAGE/raw"

# Keys that must never survive into manifests or logs.
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|authorization|"
    r"password|passwd|passphrase|secret|private[_-]?key)"
)


def scrub_request_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Deep-redact secret-looking keys from a request descriptor."""

    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                key: ("***REDACTED***" if _SECRET_KEY_RE.search(key) else scrub(value))
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [scrub(item) for item in obj]
        return obj

    return scrub(descriptor)


@dataclass(frozen=True)
class RawBatchResult:
    batch_id: str
    payload_stage_path: str
    payload_sha256: str
    records_seen: int
    local_payload_path: Path
    local_manifest_path: Path


class RawStore:
    """Persists raw payloads/manifests durably and registers them for replay."""

    def __init__(
        self,
        warehouse: Warehouse,
        state_store: StateStore,
        raw_dir: Path,
        schema_version: str,
        parser_version: str = "1",
    ) -> None:
        self._warehouse = warehouse
        self._state = state_store
        self._raw_dir = raw_dir
        self._schema_version = schema_version
        self._parser_version = parser_version

    def persist_batch(
        self,
        *,
        run_id: str,
        source_name: str,
        stream_name: str | None,
        window_start: str | None,
        window_end: str | None,
        page_seq: int | None,
        page_cursor: str | None,
        retrieved_at_utc: datetime,
        http_status: int | None,
        payload_bytes: bytes,
        records_seen: int,
        request_descriptor: dict[str, Any],
        payload_format: str = "json",
    ) -> RawBatchResult:
        """Make one raw page durable: local mirror, warehouse stage, registry row."""
        if not payload_bytes:
            raise ValueError("Raw payload is empty; refusing to persist an empty batch")
        batch_id = uuid.uuid4().hex
        date_dir = retrieved_at_utc.strftime("%Y%m%d")
        local_dir = self._raw_dir / source_name / date_dir
        local_dir.mkdir(parents=True, exist_ok=True)
        local_payload = local_dir / f"{batch_id}.payload.{payload_format}"
        local_manifest = local_dir / f"{batch_id}.manifest.json"

        local_payload.write_bytes(payload_bytes)
        payload_sha256 = _sha256(payload_bytes)

        stage_path = f"{_RAW_STAGE_ROOT}/{source_name}/{date_dir}/{batch_id}.payload.{payload_format}"
        self._warehouse.put_file(local_payload, stage_path)

        batch = RawBatch(
            batch_id=batch_id,
            run_id=run_id,
            source_name=source_name,
            stream_name=stream_name,
            window_start=window_start,
            window_end=window_end,
            page_seq=page_seq,
            page_cursor=page_cursor,
            retrieved_at_utc=retrieved_at_utc,
            http_status=http_status,
            payload_stage_path=stage_path,
            payload_sha256=payload_sha256,
            records_seen=records_seen,
            parser_version=self._parser_version,
            schema_version=self._schema_version,
            complete=False,
            request_descriptor=scrub_request_descriptor(request_descriptor),
        )
        self._state.register_raw_batch(batch)

        manifest = self._build_manifest(batch)
        local_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "raw batch persisted source=%s batch=%s records=%s sha256=%s",
            source_name,
            batch_id,
            records_seen,
            payload_sha256[:12],
        )
        return RawBatchResult(
            batch_id=batch_id,
            payload_stage_path=stage_path,
            payload_sha256=payload_sha256,
            records_seen=records_seen,
            local_payload_path=local_payload,
            local_manifest_path=local_manifest,
        )

    def mark_complete(self, batch_id: str) -> None:
        """Mark a batch complete only after it parsed/validated successfully."""
        self._state.mark_batch_complete(batch_id)

    def load_payload(self, batch_id: str, into_dir: Path) -> Path:
        """Replay support: download a stored payload from the durable stage."""
        batch = self._state.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Unknown raw batch: {batch_id}")
        stage_path = str(batch["PAYLOAD_STAGE_PATH"]).lstrip("@")
        target = into_dir / f"{batch_id}.payload"
        self._warehouse.get_file(stage_path, target)
        return target

    def _build_manifest(self, batch: RawBatch) -> dict[str, Any]:
        return {
            "run_id": batch.run_id,
            "source_name": batch.source_name,
            "batch_id": batch.batch_id,
            "retrieved_at_utc": iso_utc(batch.retrieved_at_utc),
            "request_descriptor_redacted": batch.request_descriptor,
            "http_status": batch.http_status,
            "page_or_token_sequence": {
                "page_seq": batch.page_seq,
                "page_cursor": batch.page_cursor,
            },
            "payload_stage_path": batch.payload_stage_path,
            "payload_sha256": batch.payload_sha256,
            "records_seen": batch.records_seen,
            "parser_version": batch.parser_version,
            "schema_version": batch.schema_version,
            "window_start": batch.window_start,
            "window_end": batch.window_end,
            "complete": False,
            "note": "COMPLETE flag is authoritative in PROJECT_OPS.RAW_BATCH",
        }


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
