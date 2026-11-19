"""Snowflake access for the extract-and-load runner.

The runner only performs operations a loader role needs: register the batch,
upload raw gzip NDJSON with ``PUT``, register manifest rows, verify the staged
file, mark the batch ``LOADED``, and optionally trigger the task graph. All
transformations run in Snowflake SQL (see ``sql/``).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runner.config import ConfigurationError, Settings

logger = logging.getLogger(__name__)

STAGE_ROOT = "@PAPERSONAR.PROJECT_STAGING.RAW_STAGE"
ROOT_TASK = "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_ROOT"
ELT_CHILD_TASKS = (
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_COPY",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_BRONZE",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_SILVER",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_CATEGORIZE",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_DIMENSIONS",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_FACTS",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_DQ",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_PUBLISH",
    "PAPERSONAR.PROJECT_AUDIT.TASK_ELT_FINALIZER",
)
TASK_GRAPH_SQL = "09_tasks/02_task_graph.sql"


class SnowflakeClient:
    """Thin, idempotent client around the Snowflake connector."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    @classmethod
    def from_settings(cls, settings: Settings) -> SnowflakeClient:
        settings.require_snowflake()
        try:
            import snowflake.connector
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ConfigurationError(
                "snowflake-connector-python and cryptography are required for load operations"
            ) from exc

        pem = _private_key_material(settings)
        passphrase = settings.snowflake.private_key_passphrase
        try:
            key = serialization.load_pem_private_key(
                pem, password=passphrase.encode("utf-8") if passphrase else None
            )
        except Exception as exc:  # noqa: BLE001 - normalize key errors
            raise ConfigurationError(
                "Could not load SNOWFLAKE_PRIVATE_KEY (wrong passphrase or malformed key)."
            ) from exc
        der_key = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        try:
            connection = snowflake.connector.connect(
                account=settings.snowflake.account,
                user=settings.snowflake.user,
                role=settings.snowflake.role,
                warehouse=settings.snowflake.warehouse,
                database=settings.snowflake.database,
                schema=settings.snowflake.schema_name,
                private_key=der_key,
                login_timeout=60,
                network_timeout=300,
                application="PaperSonar",
                session_parameters={"QUERY_TAG": "PaperSonar:extract"},
            )
        except Exception as exc:  # noqa: BLE001 - never leak parameters
            raise ConfigurationError(
                "Snowflake connection failed (account/user/role/network). "
                f"Type: {type(exc).__name__}"
            ) from exc
        logger.info(
            "Snowflake connection established (account=%s role=%s)",
            settings.snowflake.account,
            settings.snowflake.role,
        )
        return cls(connection)

    # -- statements -----------------------------------------------------------

    def execute(self, sql: str, params: Any = None) -> list[tuple]:
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params or None)
            if cursor.description is not None:
                return list(cursor.fetchall())
            return []
        finally:
            cursor.close()

    # -- batch lifecycle ------------------------------------------------------

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            "SELECT BATCH_ID, SOURCE_NAME, ENTITY_NAME, STATUS, CURSOR_END, "
            "FILE_COUNT, RECORD_COUNT FROM PROJECT_AUDIT.BATCH WHERE BATCH_ID = %s",
            [batch_id],
        )
        if not rows:
            return None
        return {
            "BATCH_ID": rows[0][0],
            "SOURCE_NAME": rows[0][1],
            "ENTITY_NAME": rows[0][2],
            "STATUS": rows[0][3],
            "CURSOR_END": rows[0][4],
            "FILE_COUNT": rows[0][5],
            "RECORD_COUNT": rows[0][6],
        }

    def register_batch(
        self,
        *,
        batch_id: str,
        source_name: str,
        entity_name: str,
        mode: str,
        window_start: str,
        window_end: str,
        cursor_start: str | None,
    ) -> None:
        self.execute(
            """
            MERGE INTO PROJECT_AUDIT.BATCH t
            USING (
              SELECT %s AS BATCH_ID, UPPER(%s) AS SOURCE_NAME, UPPER(%s) AS ENTITY_NAME,
                     %s AS EXTRACTION_MODE, TO_DATE(%s) AS WINDOW_START,
                     TO_DATE(%s) AS WINDOW_END, %s AS CURSOR_START
            ) s
            ON t.BATCH_ID = s.BATCH_ID
            WHEN MATCHED AND t.STATUS IN ('EXTRACTING', 'LOADED', 'FAILED') THEN UPDATE SET
              t.STATUS = 'EXTRACTING',
              t.EXTRACTION_MODE = s.EXTRACTION_MODE,
              t.WINDOW_START = s.WINDOW_START,
              t.WINDOW_END = s.WINDOW_END,
              t.CURSOR_START = s.CURSOR_START,
              t.ERROR_SUMMARY = NULL,
              t.UPDATED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT
              (BATCH_ID, SOURCE_NAME, ENTITY_NAME, EXTRACTION_MODE, WINDOW_START,
               WINDOW_END, STATUS, CURSOR_START, FILE_COUNT, RECORD_COUNT,
               CREATED_AT, UPDATED_AT)
              VALUES (s.BATCH_ID, s.SOURCE_NAME, s.ENTITY_NAME, s.EXTRACTION_MODE,
                      s.WINDOW_START, s.WINDOW_END, 'EXTRACTING', s.CURSOR_START,
                      0, 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """,
            [batch_id, source_name, entity_name, mode, window_start, window_end, cursor_start],
        )

    def update_batch_progress(
        self, batch_id: str, cursor: str | None, file_count: int, record_count: int
    ) -> None:
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET CURSOR_END = %s, FILE_COUNT = %s, "
            "RECORD_COUNT = %s, UPDATED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = %s",
            [cursor, file_count, record_count, batch_id],
        )

    def mark_batch_loaded(self, batch_id: str, file_count: int, record_count: int) -> None:
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET STATUS = 'LOADED', FILE_COUNT = %s, "
            "RECORD_COUNT = %s, UPDATED_AT = CURRENT_TIMESTAMP() "
            "WHERE BATCH_ID = %s AND STATUS = 'EXTRACTING'",
            [file_count, record_count, batch_id],
        )

    def mark_batch_failed(self, batch_id: str, error_summary: str) -> None:
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET STATUS = 'FAILED', ERROR_SUMMARY = %s, "
            "UPDATED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = %s",
            [error_summary[:2000], batch_id],
        )

    def clear_batch_outputs(self, batch_id: str, stage_dir: str) -> None:
        """Remove a batch's staged shards, manifest rows and progress.

        Used only for an explicit ``--force`` re-extract of a LOADED batch. The
        deterministic file names make an overwrite safe, but a restarted window
        can produce fewer shards; deleting the old directory prevents orphaned
        files from being picked up by the COPY step.
        """
        self.execute(f"REMOVE {STAGE_ROOT}/{stage_dir.strip('/')}/")
        self.execute(
            "DELETE FROM PROJECT_AUDIT.BATCH_MANIFEST WHERE BATCH_ID = %s", [batch_id]
        )
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET CURSOR_START = NULL, CURSOR_END = NULL, "
            "FILE_COUNT = 0, RECORD_COUNT = 0, ERROR_SUMMARY = NULL, "
            "UPDATED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = %s",
            [batch_id],
        )

    def register_manifest(
        self,
        *,
        batch_id: str,
        source_name: str,
        entity_name: str,
        file_name: str,
        checksum: str,
        size_bytes: int,
        record_count: int,
        window_start: str,
        window_end: str,
        cursor_start: str | None,
        cursor_end: str | None,
    ) -> None:
        self.execute(
            """
            MERGE INTO PROJECT_AUDIT.BATCH_MANIFEST t
            USING (
              SELECT %s AS BATCH_ID, UPPER(%s) AS SOURCE_NAME, UPPER(%s) AS ENTITY_NAME,
                     %s AS FILE_NAME, %s AS CHECKSUM, %s AS FILE_SIZE_BYTES,
                     %s AS RECORD_COUNT, TO_DATE(%s) AS WINDOW_START,
                     TO_DATE(%s) AS WINDOW_END, %s AS CURSOR_START, %s AS CURSOR_END
            ) s
            ON t.BATCH_ID = s.BATCH_ID AND t.FILE_NAME = s.FILE_NAME
            WHEN MATCHED THEN UPDATE SET
              t.CHECKSUM = s.CHECKSUM,
              t.FILE_SIZE_BYTES = s.FILE_SIZE_BYTES,
              t.RECORD_COUNT = s.RECORD_COUNT,
              t.CURSOR_START = s.CURSOR_START,
              t.CURSOR_END = s.CURSOR_END,
              t.EXTRACTED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT
              (BATCH_ID, SOURCE_NAME, ENTITY_NAME, FILE_NAME, CHECKSUM,
               FILE_SIZE_BYTES, RECORD_COUNT, WINDOW_START, WINDOW_END,
               CURSOR_START, CURSOR_END, EXTRACTED_AT, STATUS)
              VALUES (s.BATCH_ID, s.SOURCE_NAME, s.ENTITY_NAME, s.FILE_NAME,
                      s.CHECKSUM, s.FILE_SIZE_BYTES, s.RECORD_COUNT,
                      s.WINDOW_START, s.WINDOW_END, s.CURSOR_START,
                      s.CURSOR_END, CURRENT_TIMESTAMP(), 'REGISTERED')
            """,
            [
                batch_id,
                source_name,
                entity_name,
                file_name,
                checksum,
                size_bytes,
                record_count,
                window_start,
                window_end,
                cursor_start,
                cursor_end,
            ],
        )

    def register_oversize(
        self,
        *,
        batch_id: str,
        source_name: str,
        entity_name: str,
        record_sha256: str,
        detail: dict[str, Any],
    ) -> None:
        self.execute(
            """
            INSERT INTO PROJECT_AUDIT.QUARANTINE_RECORD
              (QUARANTINE_ID, BATCH_ID, SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID,
               RECORD_HASH, REASON_CODE, DETAIL, RAW_REFERENCE, CREATED_AT)
            SELECT %s, %s, %s, %s, NULL, %s, 'OVERSIZE_RECORD', PARSE_JSON(%s), NULL,
                   CURRENT_TIMESTAMP()
            WHERE NOT EXISTS (
              SELECT 1 FROM PROJECT_AUDIT.QUARANTINE_RECORD q
              WHERE q.QUARANTINE_ID = %s
            )
            """,
            [
                f"{batch_id}:{record_sha256}"[:255],
                batch_id,
                source_name,
                entity_name,
                record_sha256,
                json.dumps(detail, default=str),
                f"{batch_id}:{record_sha256}"[:255],
            ],
        )

    # -- stage ----------------------------------------------------------------

    # PUT returns one row per file: source, target, source_size, target_size,
    # source_compression, target_compression, status, message.
    _PUT_COLUMNS = (
        "source",
        "target",
        "source_size",
        "target_size",
        "source_compression",
        "target_compression",
        "status",
        "message",
    )

    def put_file(self, local_path: Path, stage_dir: str) -> dict[str, Any]:
        remote = local_path.resolve().as_posix()
        target = f"{STAGE_ROOT}/{stage_dir.strip('/')}/"
        rows = self.execute(
            f"PUT 'file://{remote}' {target} "
            "PARALLEL=1 AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
        if not rows:
            raise RuntimeError(f"PUT returned no result for {local_path.name}")
        upload = dict(zip(self._PUT_COLUMNS, rows[0], strict=False))
        expected = local_path.stat().st_size
        if int(upload.get("source_size") or -1) != expected:
            raise RuntimeError(
                f"PUT source size mismatch for {local_path.name}: "
                f"expected {expected}, reported {upload.get('source_size')}"
            )
        if str(upload.get("status") or "") != "UPLOADED":
            raise RuntimeError(
                f"PUT did not complete for {local_path.name}: "
                f"{upload.get('status')} {upload.get('message')}"
            )
        if str(upload.get("target") or "") != local_path.name:
            raise RuntimeError(
                f"PUT target name mismatch for {local_path.name}: "
                f"reported {upload.get('target')}"
            )
        logger.debug(
            "PUT %s source=%s target=%s compression=%s/%s",
            local_path.name,
            upload.get("source_size"),
            upload.get("target_size"),
            upload.get("source_compression"),
            upload.get("target_compression"),
        )
        return upload

    def list_stage(self, stage_dir: str) -> list[dict[str, Any]]:
        rows = self.execute(f"LIST {STAGE_ROOT}/{stage_dir.strip('/')}/")
        return [
            {"name": str(row[0]), "size": int(row[1] or 0), "md5": str(row[2] or "")}
            for row in rows
        ]

    def verify_staged_file(
        self,
        stage_dir: str,
        file_name: str,
        expected_size: int,
        upload: dict[str, Any] | None = None,
    ) -> None:
        """Confirm the file is visible on the stage and the upload read it fully.

        Snowflake's ``LIST`` size includes an internal object header; for gzip
        shards it is 4 bytes larger than the bytes ``GET`` returns, and for plain
        files the difference varies. Compare ``PUT``'s ``source_size`` instead,
        and use ``LIST`` only as an existence check.
        """
        if upload is not None:
            if int(upload.get("source_size") or -1) != expected_size:
                raise RuntimeError(
                    f"Staged file source size mismatch for {file_name}: "
                    f"expected {expected_size}, reported {upload.get('source_size')}"
                )
            if str(upload.get("status") or "") != "UPLOADED":
                raise RuntimeError(
                    f"Staged file was not uploaded for {file_name}: {upload.get('status')}"
                )
        entries = self.list_stage(stage_dir)
        for entry in entries:
            if entry["name"].endswith(file_name):
                return
        raise RuntimeError(f"Staged file not found after PUT: {stage_dir}/{file_name}")

    # -- orchestration --------------------------------------------------------

    def get_watermark(self, source_name: str, entity_name: str) -> str | None:
        """Return the last published watermark value, if any."""
        rows = self.execute(
            "SELECT WATERMARK_VALUE FROM PROJECT_AUDIT.SOURCE_WATERMARK "
            "WHERE UPPER(SOURCE_NAME) = UPPER(%s) AND UPPER(ENTITY_NAME) = UPPER(%s)",
            [source_name, entity_name],
        )
        return rows[0][0] if rows else None

    def pending_batch_count(self) -> int:
        rows = self.execute(
            "SELECT COUNT(*) FROM PROJECT_AUDIT.BATCH "
            "WHERE STATUS IN ('LOADED', 'PROCESSING')"
        )
        return int(rows[0][0]) if rows else 0

    def wait_for_idle(self, *, timeout_seconds: int = 3600, poll_seconds: int = 10) -> None:
        """Wait until no batch is LOADED or PROCESSING.

        LOADED covers a batch that the root task has not claimed yet; PROCESSING
        covers an in-flight graph. Timeout is a fail-closed guard against a
        suspended or broken task graph.
        """
        deadline = time.monotonic() + timeout_seconds
        while True:
            if self.pending_batch_count() == 0:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for Snowflake batches to leave LOADED/PROCESSING; "
                    "inspect PROJECT_AUDIT.BATCH, RUN_LOG and task history."
                )
            time.sleep(poll_seconds)

    def drain_batches(self, *, max_batches: int = 500, timeout_seconds: int = 3600) -> int:
        """Trigger the root task until every LOADED/PROCESSING batch is resolved."""
        rounds = 0
        while rounds < max_batches:
            if self.pending_batch_count() == 0:
                return rounds
            try:
                self.execute_root_task()
            except Exception as exc:
                logger.warning(
                    "could not start TASK_ELT_ROOT (%s); waiting for the in-flight graph",
                    exc,
                )
            self.wait_for_idle(timeout_seconds=timeout_seconds)
            rounds += 1
        remaining = self.pending_batch_count()
        if remaining:
            raise RuntimeError(
                f"{remaining} batches still pending after {max_batches} trigger rounds"
            )
        return rounds

    def execute_root_task(self) -> None:
        self.execute(f"EXECUTE TASK {ROOT_TASK}")

    def resume_task_graph(self) -> None:
        """Resume the ELT graph after CREATE OR REPLACE TASK suspends every task.

        Child tasks must be resumed before the root so GitHub's `EXECUTE TASK`
        never fires into a graph whose children are still suspended.
        """
        self.execute(f"ALTER TASK {ROOT_TASK} SUSPEND")
        for task in ELT_CHILD_TASKS:
            self.execute(f"ALTER TASK {task} RESUME")
        self.execute(f"ALTER TASK {ROOT_TASK} RESUME")
        logger.info("resumed %d ELT tasks plus the root task", len(ELT_CHILD_TASKS))

    def deploy_sql(self, sql_dir: Path, *, include_setup: bool = False) -> list[str]:
        """Upload SQL files and execute them with ``EXECUTE IMMEDIATE FROM``.

        Files under ``99_tests`` are evidence queries, not deployable objects.
        Files whose header contains ``-- Deploy: manual`` are skipped because
        they depend on edition/feature verification (for example materialized
        views and dynamic tables). ``sql/00_setup`` is skipped by default
        because database/role/account grants require one-time administrative
        privileges; pass ``include_setup=True`` only for that controlled run.
        When the task graph SQL is deployed, the graph is resumed afterwards so
        ``CREATE OR REPLACE TASK`` does not leave it suspended.
        """
        deployed: list[str] = []
        task_graph_deployed = False
        for path in sorted(sql_dir.rglob("*.sql")):
            if "99_tests" in path.parts:
                continue
            relative_parts = path.relative_to(sql_dir).parts
            if not include_setup and "00_setup" in relative_parts[:-1]:
                logger.warning("skipped setup SQL %s; run it with an administrator", path)
                continue
            relative = path.relative_to(sql_dir).as_posix()
            header = path.read_text(encoding="utf-8")[:4000]
            if "-- Deploy: manual" in header:
                logger.warning("skipped manual-only SQL %s", relative)
                continue
            self.put_file(path, f"sql/{relative.rsplit('/', 1)[0]}")
            self.execute(f"EXECUTE IMMEDIATE FROM '{STAGE_ROOT}/sql/{relative}'")
            deployed.append(relative)
            task_graph_deployed = task_graph_deployed or relative == TASK_GRAPH_SQL
            logger.info("deployed SQL %s", relative)
        if task_graph_deployed:
            self.resume_task_graph()
        return deployed

    def close(self) -> None:
        self._conn.close()


def _private_key_material(settings: Settings) -> bytes:
    value = settings.snowflake.private_key or ""
    if "BEGIN" in value:
        return value.encode("utf-8")
    path = Path(value)
    if not path.exists():
        raise ConfigurationError(
            "SNOWFLAKE_PRIVATE_KEY must be PEM content or a path to an existing key file."
        )
    return path.read_bytes()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
