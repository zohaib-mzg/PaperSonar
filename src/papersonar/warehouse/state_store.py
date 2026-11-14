"""Durable pipeline state in Snowflake: runs, per-source checkpoints, raw batch
registry and quarantine.

Rules enforced here:
- The completed watermark is separate from in-progress pagination state.
- Checkpoint writes are transactional; a failure rolls back and the watermark
  stays unchanged.
- Raw batch rows are registered before a page is marked complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

from papersonar.errors import CheckpointError
from papersonar.timeutil import utc_now
from papersonar.warehouse.adapter import Warehouse

_RUN_COLUMNS = (
    "RUN_ID",
    "MODE",
    "STARTED_AT",
    "FINISHED_AT",
    "STATUS",
    "GIT_COMMIT",
    "CONFIG_CHECKSUM",
    "CODE_VERSION",
    "SOURCE_STATUSES",
    "RAW_ROWS",
    "STAGING_ROWS",
    "QUARANTINED_ROWS",
    "WAREHOUSE_ROWS",
    "RETRY_COUNT",
    "QUALITY_GATE_RESULT",
    "ERROR_SUMMARY",
)

_SYNC_STATE_COLUMNS = (
    "SOURCE_NAME",
    "STREAM_NAME",
    "SYNC_MODE",
    "WINDOW_START",
    "WINDOW_END",
    "CURSOR_OR_TOKEN",
    "LAST_SUCCESSFUL_WATERMARK",
    "LAST_ATTEMPT_AT",
    "LAST_SUCCESS_AT",
    "LAST_RUN_ID",
    "STATUS",
    "PAGES_COMPLETED",
    "RECORDS_SEEN",
    "RECORDS_WRITTEN",
    "RECORDS_QUARANTINED",
    "ERROR_CODE",
    "ERROR_SUMMARY",
    "CONFIG_CHECKSUM",
    "UPDATED_AT",
)

_RAW_BATCH_COLUMNS = (
    "BATCH_ID",
    "RUN_ID",
    "SOURCE_NAME",
    "STREAM_NAME",
    "WINDOW_START",
    "WINDOW_END",
    "PAGE_SEQ",
    "PAGE_CURSOR",
    "RETRIEVED_AT_UTC",
    "HTTP_STATUS",
    "PAYLOAD_STAGE_PATH",
    "PAYLOAD_SHA256",
    "RECORDS_SEEN",
    "PARSER_VERSION",
    "SCHEMA_VERSION",
    "COMPLETE",
    "REQUEST_DESCRIPTOR",
)


@dataclass(frozen=True)
class SyncState:
    """Durable per-source/per-stream checkpoint."""

    source_name: str
    stream_name: str
    sync_mode: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    cursor_or_token: str | None = None
    last_successful_watermark: str | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_run_id: str | None = None
    status: str = "idle"
    pages_completed: int = 0
    records_seen: int = 0
    records_written: int = 0
    records_quarantined: int = 0
    error_code: str | None = None
    error_summary: str | None = None
    config_checksum: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RawBatch:
    """One durable raw page/batch of source payloads."""

    batch_id: str
    run_id: str
    source_name: str
    stream_name: str | None
    window_start: str | None
    window_end: str | None
    page_seq: int | None
    page_cursor: str | None
    retrieved_at_utc: datetime
    http_status: int | None
    payload_stage_path: str
    payload_sha256: str
    records_seen: int | None
    parser_version: str
    schema_version: str
    complete: bool = False
    request_descriptor: dict[str, Any] | None = None

    def row(self) -> list[Any]:
        return [
            self.batch_id,
            self.run_id,
            self.source_name,
            self.stream_name,
            self.window_start,
            self.window_end,
            self.page_seq,
            self.page_cursor,
            self.retrieved_at_utc,
            self.http_status,
            self.payload_stage_path,
            self.payload_sha256,
            self.records_seen,
            self.parser_version,
            self.schema_version,
            self.complete,
            self.request_descriptor,
        ]


class StateStore:
    """Transactional access to PROJECT_OPS state tables."""

    def __init__(self, warehouse: Warehouse) -> None:
        self._warehouse = warehouse

    # -- checkpoints ---------------------------------------------------------

    def get_sync_state(self, source_name: str, stream_name: str) -> SyncState | None:
        columns = ", ".join(_SYNC_STATE_COLUMNS)
        rows = self._warehouse.execute(
            f"SELECT {columns} FROM PROJECT_OPS.SOURCE_SYNC_STATE "
            "WHERE SOURCE_NAME = %s AND STREAM_NAME = %s",
            [source_name, stream_name],
        )
        if not rows:
            return None
        values = dict(zip(_SYNC_STATE_COLUMNS, rows[0], strict=True))
        return SyncState(
            **{
                _snake(key): value
                for key, value in values.items()
                if _snake(key) in {f.name for f in fields(SyncState)}
            }
        )

    def save_sync_state(self, state: SyncState) -> None:
        """Upsert the checkpoint row (no transaction wrapper - caller decides).

        ``None`` fields mean "preserve the stored value" - a partial state can
        never wipe the durable watermark. To clear a field explicitly, store an
        empty string instead of ``None``.
        """
        values = {column: getattr(state, _snake(column)) for column in _SYNC_STATE_COLUMNS}
        update_columns = [
            column
            for column in _SYNC_STATE_COLUMNS
            if column not in ("SOURCE_NAME", "STREAM_NAME") and values.get(column) is not None
        ]
        stamped = SyncState(**{**asdict(state), "updated_at": utc_now()})
        row = [getattr(stamped, _snake(column)) for column in _SYNC_STATE_COLUMNS]
        self._warehouse.upsert_rows(
            "PROJECT_OPS.SOURCE_SYNC_STATE",
            ["SOURCE_NAME", "STREAM_NAME"],
            list(_SYNC_STATE_COLUMNS),
            [row],
            update_columns=update_columns,
        )

    def save_sync_state_transactional(self, state: SyncState) -> None:
        """Upsert the checkpoint with transaction guarantees.

        Any failure rolls back and raises CheckpointError so the caller knows
        the watermark did NOT advance.
        """
        try:
            self._warehouse.begin()
            self.save_sync_state(state)
            self._warehouse.commit()
        except Exception as exc:
            self._warehouse.rollback()
            raise CheckpointError(
                f"Checkpoint write for {state.source_name}/{state.stream_name} failed; "
                "watermark unchanged."
            ) from exc

    # -- runs ----------------------------------------------------------------

    def create_run(
        self,
        run_id: str,
        mode: str,
        started_at: datetime,
        git_commit: str | None = None,
        config_checksum: str | None = None,
        code_version: str | None = None,
    ) -> None:
        self._warehouse.upsert_rows(
            "PROJECT_OPS.ETL_RUN",
            ["RUN_ID"],
            list(_RUN_COLUMNS),
            [[
                run_id,
                mode,
                started_at,
                None,
                "started",
                git_commit,
                config_checksum,
                code_version,
                None,
                0,
                0,
                0,
                0,
                0,
                None,
                None,
            ]],
        )

    def finish_run(
        self,
        run_id: str,
        status: str,
        finished_at: datetime,
        source_statuses: dict[str, str] | None = None,
        raw_rows: int = 0,
        staging_rows: int = 0,
        quarantined_rows: int = 0,
        warehouse_rows: int = 0,
        retry_count: int = 0,
        quality_gate_result: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        # MODE/STARTED_AT/GIT_COMMIT/CONFIG_CHECKSUM/CODE_VERSION are preserved
        # from create_run via the limited update column list.
        self._warehouse.upsert_rows(
            "PROJECT_OPS.ETL_RUN",
            ["RUN_ID"],
            list(_RUN_COLUMNS),
            [[
                run_id,
                None,
                finished_at,
                finished_at,
                status,
                None,
                None,
                None,
                source_statuses,
                raw_rows,
                staging_rows,
                quarantined_rows,
                warehouse_rows,
                retry_count,
                quality_gate_result,
                error_summary,
            ]],
            update_columns=[
                "FINISHED_AT",
                "STATUS",
                "SOURCE_STATUSES",
                "RAW_ROWS",
                "STAGING_ROWS",
                "QUARANTINED_ROWS",
                "WAREHOUSE_ROWS",
                "RETRY_COUNT",
                "QUALITY_GATE_RESULT",
                "ERROR_SUMMARY",
            ],
        )

    # -- raw batches ---------------------------------------------------------

    def register_raw_batch(self, batch: RawBatch) -> None:
        self._warehouse.insert_rows(
            "PROJECT_OPS.RAW_BATCH", list(_RAW_BATCH_COLUMNS), [batch.row()]
        )

    def mark_batch_complete(self, batch_id: str) -> None:
        self._warehouse.execute(
            "UPDATE PROJECT_OPS.RAW_BATCH SET COMPLETE = TRUE WHERE BATCH_ID = %s", [batch_id]
        )

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        columns = ", ".join(_RAW_BATCH_COLUMNS)
        rows = self._warehouse.execute(
            f"SELECT {columns} FROM PROJECT_OPS.RAW_BATCH WHERE BATCH_ID = %s", [batch_id]
        )
        if not rows:
            return None
        return dict(zip(_RAW_BATCH_COLUMNS, rows[0], strict=True))

    # -- quarantine ----------------------------------------------------------

    def quarantine(
        self,
        quarantine_id: str,
        run_id: str,
        source_name: str,
        source_record_id: str | None,
        reason_code: str,
        detail: str | None = None,
        batch_id: str | None = None,
    ) -> None:
        """Idempotent quarantine upsert: re-quarantining updates last-seen."""
        now = utc_now()
        self._warehouse.upsert_rows(
            "PROJECT_STAGING.STG_QUARANTINE",
            ["QUARANTINE_ID"],
            [
                "QUARANTINE_ID",
                "RUN_ID",
                "BATCH_ID",
                "SOURCE_NAME",
                "SOURCE_RECORD_ID",
                "REASON_CODE",
                "DETAIL",
                "FIRST_SEEN_AT",
                "LAST_SEEN_AT",
                "RESOLUTION_STATUS",
            ],
            [[
                quarantine_id,
                run_id,
                batch_id,
                source_name,
                source_record_id,
                reason_code,
                detail,
                now,
                now,
                "open",
            ]],
        )


def _snake(name: str) -> str:
    return name.lower()
