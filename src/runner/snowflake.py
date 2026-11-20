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
        """Execute a statement, retrying transient connector failures."""
        attempt = 0
        while True:
            try:
                return self._execute_once(sql, params)
            except Exception as exc:  # noqa: BLE001 - connector classes vary by version
                transient = type(exc).__name__ in {
                    "OperationalError", "InterfaceError", "DatabaseError",
                    "ServiceUnavailableError",
                }
                if not transient or attempt >= 6:
                    raise
                delay = min(2**attempt, 16)
                attempt += 1
                logger.warning(
                    "transient Snowflake error (%s); retrying in %ds", type(exc).__name__, delay
                )
                time.sleep(delay)

    def _execute_once(self, sql: str, params: Any = None) -> list[tuple]:
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params or None)
            if cursor.description is not None:
                return list(cursor.fetchall())
            return []
        finally:
            cursor.close()

    # -- batch lifecycle ------------------------------------------------------

    def requeue_failed_batch(self, batch_id: str) -> bool:
        """Move a FAILED transformation batch back to LOADED for a safe re-run."""
        rows = self.execute(
            "SELECT STATUS FROM PROJECT_AUDIT.BATCH WHERE BATCH_ID = %s", [batch_id]
        )
        if not rows or rows[0][0] != "FAILED":
            return False
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET STATUS = 'LOADED', ERROR_SUMMARY = NULL, "
            "UPDATED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = %s AND STATUS = 'FAILED'",
            [batch_id],
        )
        return True

    def source_summary(self) -> list[dict[str, Any]]:
        """Return per-source batch and record totals for operational reporting."""
        rows = self.execute(
            """
            SELECT SOURCE_NAME,
                   COUNT(*) AS BATCHES,
                   COUNT_IF(STATUS = 'LOADED') AS LOADED,
                   COUNT_IF(STATUS = 'PROCESSING') AS PROCESSING,
                   COUNT_IF(STATUS = 'PUBLISHED') AS PUBLISHED,
                   COUNT_IF(STATUS = 'FAILED') AS FAILED,
                   SUM(RECORD_COUNT) AS RECORDS
            FROM PROJECT_AUDIT.BATCH
            GROUP BY SOURCE_NAME ORDER BY SOURCE_NAME
            """
        )
        return [
            {
                "SOURCE_NAME": row[0], "BATCHES": int(row[1]), "LOADED": int(row[2]),
                "PROCESSING": int(row[3]), "PUBLISHED": int(row[4]),
                "FAILED": int(row[5]), "RECORDS": int(row[6] or 0),
            }
            for row in rows
        ]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            "SELECT BATCH_ID, SOURCE_NAME, ENTITY_NAME, STATUS, CURSOR_END, "
            "FILE_COUNT, RECORD_COUNT, IS_CAPPED FROM PROJECT_AUDIT.BATCH "
            "WHERE BATCH_ID = %s",
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
            "IS_CAPPED": bool(rows[0][7]),
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
        is_capped: bool = False,
    ) -> None:
        self.execute(
            """
            MERGE INTO PROJECT_AUDIT.BATCH t
            USING (
              SELECT %s AS BATCH_ID, UPPER(%s) AS SOURCE_NAME, UPPER(%s) AS ENTITY_NAME,
                     %s AS EXTRACTION_MODE, TO_DATE(%s) AS WINDOW_START,
                     TO_DATE(%s) AS WINDOW_END, %s AS CURSOR_START,
                     %s AS IS_CAPPED
            ) s
            ON t.BATCH_ID = s.BATCH_ID
            WHEN MATCHED AND (
              t.STATUS IN ('EXTRACTING', 'LOADED', 'FAILED')
              OR (t.STATUS = 'PUBLISHED' AND t.IS_CAPPED)
            ) THEN UPDATE SET
              t.STATUS = 'EXTRACTING',
              t.EXTRACTION_MODE = s.EXTRACTION_MODE,
              t.WINDOW_START = s.WINDOW_START,
              t.WINDOW_END = s.WINDOW_END,
              t.CURSOR_START = s.CURSOR_START,
              t.IS_CAPPED = s.IS_CAPPED,
              t.ERROR_SUMMARY = NULL,
              t.UPDATED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT
              (BATCH_ID, SOURCE_NAME, ENTITY_NAME, EXTRACTION_MODE, WINDOW_START,
               WINDOW_END, STATUS, CURSOR_START, IS_CAPPED, FILE_COUNT, RECORD_COUNT,
               CREATED_AT, UPDATED_AT)
              VALUES (s.BATCH_ID, s.SOURCE_NAME, s.ENTITY_NAME, s.EXTRACTION_MODE,
                      s.WINDOW_START, s.WINDOW_END, 'EXTRACTING', s.CURSOR_START,
                      s.IS_CAPPED, 0, 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """,
            [
                batch_id,
                source_name,
                entity_name,
                mode,
                window_start,
                window_end,
                cursor_start,
                is_capped,
            ],
        )

    def update_batch_progress(
        self,
        batch_id: str,
        cursor: str | None,
        file_count: int,
        record_count: int,
        is_capped: bool = False,
    ) -> None:
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET CURSOR_END = %s, FILE_COUNT = %s, "
            "RECORD_COUNT = %s, IS_CAPPED = %s, UPDATED_AT = CURRENT_TIMESTAMP() "
            "WHERE BATCH_ID = %s",
            [cursor, file_count, record_count, is_capped, batch_id],
        )

    def mark_batch_loaded(
        self,
        batch_id: str,
        file_count: int,
        record_count: int,
        is_capped: bool = False,
    ) -> None:
        self.execute(
            "UPDATE PROJECT_AUDIT.BATCH SET STATUS = 'LOADED', FILE_COUNT = %s, "
            "RECORD_COUNT = %s, IS_CAPPED = %s, UPDATED_AT = CURRENT_TIMESTAMP() "
            "WHERE BATCH_ID = %s AND STATUS = 'EXTRACTING'",
            [file_count, record_count, is_capped, batch_id],
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
            "FILE_COUNT = 0, RECORD_COUNT = 0, IS_CAPPED = FALSE, ERROR_SUMMARY = NULL, "
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

    def get_watermark_state(self, source_name: str, entity_name: str) -> dict[str, Any]:
        """Return the durable incremental resume state for one source/entity."""
        rows = self.execute(
            "SELECT WATERMARK_VALUE, WINDOW_START, WINDOW_END, CURSOR, STATUS, "
            "LAST_BATCH_ID FROM PROJECT_AUDIT.SOURCE_WATERMARK "
            "WHERE UPPER(SOURCE_NAME) = UPPER(%s) AND UPPER(ENTITY_NAME) = UPPER(%s)",
            [source_name, entity_name],
        )
        if not rows:
            return {}
        row = rows[0]
        return {
            "WATERMARK_VALUE": row[0],
            "WINDOW_START": row[1],
            "WINDOW_END": row[2],
            "CURSOR": row[3],
            "STATUS": row[4],
            "LAST_BATCH_ID": row[5],
        }

    def batch_statuses(self) -> list[dict[str, Any]]:
        """Return the current audit state of every recent batch."""
        rows = self.execute(
            "SELECT BATCH_ID, SOURCE_NAME, STATUS, FILE_COUNT, RECORD_COUNT, "
            "IS_CAPPED, TO_VARCHAR(UPDATED_AT) "
            "FROM PROJECT_AUDIT.BATCH ORDER BY CREATED_AT, BATCH_ID"
        )
        return [
            {
                "BATCH_ID": row[0],
                "SOURCE_NAME": row[1],
                "STATUS": row[2],
                "FILE_COUNT": int(row[3] or 0),
                "RECORD_COUNT": int(row[4] or 0),
                "IS_CAPPED": bool(row[5]),
                "UPDATED_AT": row[6],
            }
            for row in rows
        ]

    def task_history(self, *, hours: int = 1, limit: int = 20) -> list[dict[str, Any]]:
        """Recent task history with timestamps normalized to UTC for logs.

        Snowflake displays TIMESTAMP_LTZ in the session timezone (-0800 here),
        while GitHub cron and the runner use UTC. Converting explicitly avoids
        comparing wall-clock values from different zones.
        """
        rows = self.execute(
            """
            SELECT NAME, STATE, ERROR_MESSAGE,
                   TO_VARCHAR(CONVERT_TIMEZONE('UTC', SCHEDULED_TIME)),
                   TO_VARCHAR(CONVERT_TIMEZONE('UTC', STARTED_TIME)),
                   TO_VARCHAR(CONVERT_TIMEZONE('UTC', COMPLETED_TIME))
            FROM TABLE(PAPERSONAR.INFORMATION_SCHEMA.TASK_HISTORY(
              SCHEDULED_TIME_RANGE_START => DATEADD('hour', -%s, CURRENT_TIMESTAMP()),
              RESULT_LIMIT => %s
            ))
            ORDER BY SCHEDULED_TIME DESC
            """,
            [hours, limit],
        )
        return [
            {
                "NAME": row[0],
                "STATE": row[1],
                "ERROR": row[2],
                "SCHEDULED_UTC": row[3],
                "STARTED_UTC": row[4],
                "COMPLETED_UTC": row[5],
            }
            for row in rows
        ]

    def pending_batch_count(self) -> int:
        rows = self.execute(
            "SELECT COUNT(*) FROM PROJECT_AUDIT.BATCH "
            "WHERE STATUS IN ('LOADED', 'PROCESSING')"
        )
        return int(rows[0][0]) if rows else 0

    def wait_for_idle(self, *, timeout_seconds: int = 3600, poll_seconds: int = 10) -> None:
        """Compatibility wrapper retained for callers that only need to wait."""
        deadline = time.monotonic() + timeout_seconds
        while self.pending_batch_count():
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for Snowflake batches to drain")
            time.sleep(poll_seconds)

    def drain_batches(
        self,
        *,
        max_batches: int = 500,
        no_progress_seconds: int = 600,
        poll_seconds: int = 10,
    ) -> int:
        """Trigger one root per LOADED batch and fail fast on a stalled graph.

        The root task claims exactly one LOADED batch per EXECUTE TASK. The old
        loop triggered once and then waited for *all* pending batches to clear,
        leaving the other LOADED batches stranded. Here every poll logs batch
        status and a new root is triggered as soon as no graph is in flight.
        """
        rounds = 0
        last_signature: tuple | None = None
        last_progress = time.monotonic()
        deadline = time.monotonic() + no_progress_seconds
        while rounds < max_batches:
            statuses = self.batch_statuses()
            pending = [row for row in statuses if row["STATUS"] in ("LOADED", "PROCESSING")]
            counts = {
                status: sum(1 for row in statuses if row["STATUS"] == status)
                for status in ("LOADED", "PROCESSING", "PUBLISHED", "FAILED")
            }
            logger.info("ELT poll: rounds=%d counts=%s", rounds, counts)
            for row in pending:
                logger.info(
                    "ELT poll batch=%s status=%s capped=%s files=%d records=%d updated=%s",
                    row["BATCH_ID"], row["STATUS"], row["IS_CAPPED"], row["FILE_COUNT"],
                    row["RECORD_COUNT"], row["UPDATED_AT"],
                )
            if not pending:
                return rounds

            signature = tuple(
                (row["BATCH_ID"], row["STATUS"], row["UPDATED_AT"]) for row in statuses
            )
            if last_signature is None or signature != last_signature:
                last_signature = signature
                last_progress = time.monotonic()
            elif time.monotonic() - last_progress >= no_progress_seconds:
                history = self.task_history(hours=2, limit=20)
                logger.error("ELT task history (UTC): %s", json.dumps(history, default=str))
                raise RuntimeError(
                    f"No ELT progress for {no_progress_seconds}s with "
                    f"{len(pending)} batch(es) still LOADED/PROCESSING: "
                    f"{[row['BATCH_ID'] for row in pending]}"
                )
            if time.monotonic() >= deadline and not pending:
                return rounds

            in_flight = any(row["STATUS"] == "PROCESSING" for row in pending)
            if not in_flight:
                try:
                    self.execute_root_task()
                    rounds += 1
                    logger.info("ELT root triggered (round %d)", rounds)
                except Exception as exc:  # noqa: BLE001 - root may already be running
                    logger.warning("could not start TASK_ELT_ROOT (%s); repolling", exc)
            time.sleep(poll_seconds)

        remaining = [row for row in self.batch_statuses() if row["STATUS"] in ("LOADED", "PROCESSING")]
        if remaining:
            raise RuntimeError(f"{len(remaining)} batches still pending after {max_batches} rounds")
        return rounds

    def execute_root_task(self) -> None:
        """Run the root on demand; Snowflake allows EXECUTE TASK on a suspended root."""
        self.execute(f"EXECUTE TASK {ROOT_TASK}")

    def resume_task_graph(self) -> None:
        """Prepare the ELT graph after CREATE OR REPLACE TASK suspends every task.

        Snowflake requires SCHEDULE, AFTER, FINALIZE, or WHEN before a task can be
        RESUMED. The root deliberately has none, so it stays suspended and GitHub
        runs it with EXECUTE TASK. Only child tasks need RESUME; suspended children
        are skipped when the root runs.
        """
        self.execute(f"ALTER TASK {ROOT_TASK} SUSPEND")
        for task in ELT_CHILD_TASKS:
            self.execute(f"ALTER TASK {task} RESUME")
        logger.info(
            "resumed %d ELT child tasks; root remains suspended for EXECUTE TASK",
            len(ELT_CHILD_TASKS),
        )

    def deploy_sql(self, sql_dir: Path, *, include_setup: bool = False) -> list[str]:
        """Upload SQL files and execute them with ``EXECUTE IMMEDIATE FROM``.

        Files under ``99_tests`` are evidence queries, not deployable objects.
        Files whose header contains ``-- Deploy: manual`` are skipped because
        they depend on edition/feature verification (for example materialized
        views and dynamic tables). ``sql/00_setup`` is skipped by default
        because database/role/account grants require one-time administrative
        privileges; pass ``include_setup=True`` only for that controlled run.
        When the task graph SQL is deployed, child tasks are resumed afterwards
        and the root is left suspended for on-demand ``EXECUTE TASK`` calls.
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
