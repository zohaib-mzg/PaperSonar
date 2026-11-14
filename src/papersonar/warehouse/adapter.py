"""Snowflake warehouse adapter.

Snowflake is the only production warehouse target for PaperSonar Phase 2.
This module provides the warehouse protocol used by all pipeline stages and
the real Snowflake implementation with key-pair authentication.

Deterministic tests inject a mock implementation of the same protocol; a mock
is a testing technique and never a production fallback.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from papersonar.config import Settings
from papersonar.errors import ConfigurationError

logger = logging.getLogger(__name__)


class Warehouse(Protocol):
    """Storage protocol implemented by the Snowflake adapter (and test mocks)."""

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        """Execute a statement and return fetched rows."""
        ...

    def upsert_rows(
        self,
        table: str,
        key_columns: Sequence[str],
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
        update_columns: Sequence[str] | None = None,
    ) -> int:
        """Idempotent MERGE-based upsert by key columns.

        ``update_columns`` limits the WHEN MATCHED update set; omitted columns
        keep their stored values.
        """
        ...

    def insert_rows(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> int:
        """Append-only batch insert (e.g. immutable raw/manifest evidence)."""
        ...

    def execute_script(self, sql_text: str) -> None:
        """Execute a multi-statement SQL script (migrations)."""
        ...

    def put_file(self, local_path: Path, stage_path: str) -> None:
        """Upload a durable raw payload to the warehouse raw stage."""
        ...

    def get_file(self, stage_path: str, local_path: Path) -> None:
        """Download a raw payload from the warehouse raw stage."""
        ...

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class SnowflakeAdapter:
    """Snowflake implementation with key-pair authentication."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    @classmethod
    def from_settings(cls, settings: Settings) -> SnowflakeAdapter:
        """Fail-closed factory: requires full Snowflake configuration before connecting."""
        settings.require_snowflake()
        try:
            import snowflake.connector
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:  # pragma: no cover - dependency is pinned in pyproject
            raise ConfigurationError(
                "snowflake-connector-python is required for the production warehouse"
            ) from exc

        pem = settings.snowflake.private_key_pem()
        passphrase = settings.snowflake.private_key_passphrase
        try:
            key = serialization.load_pem_private_key(
                pem,
                password=passphrase.encode("utf-8") if passphrase else None,
            )
        except Exception as exc:
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
            )
        except Exception as exc:
            # Message must never include key material; connector errors may embed params.
            raise ConfigurationError(
                f"Snowflake connection failed (account/user/role/network). "
                f"Type: {type(exc).__name__}"
            ) from exc
        logger.info(
            "Snowflake connection established (account=%s role=%s)",
            settings.snowflake.account,
            settings.snowflake.role,
        )
        return cls(connection)

    # -- statements ----------------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params or None)
            if cursor.description is not None:
                return list(cursor.fetchall())
            return []
        finally:
            cursor.close()

    # -- bulk loaders --------------------------------------------------------

    def upsert_rows(
        self,
        table: str,
        key_columns: Sequence[str],
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
        update_columns: Sequence[str] | None = None,
    ) -> int:
        """Chunked MERGE upsert. Idempotent: replaying the same rows is a no-op.

        ``update_columns`` limits which columns the WHEN MATCHED branch updates;
        omitted columns (e.g. ``MODE``, ``STARTED_AT``) keep their stored values.
        Defaults to every non-key column.
        """
        if not rows:
            return 0
        if update_columns is None:
            update_columns = [c for c in columns if c not in key_columns]
        merged = 0
        for chunk in _chunk(rows, _MERGE_CHUNK):
            merged += self._merge_chunk(table, key_columns, columns, update_columns, chunk)
        return merged

    def _merge_chunk(
        self,
        table: str,
        key_columns: Sequence[str],
        columns: Sequence[str],
        update_columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> int:
        row_selects = []
        params: list[Any] = []
        for row in rows:
            parts = []
            for column, value in zip(columns, row, strict=True):
                if _is_json_value(value):
                    # dict/list -> JSON text, parsed to VARIANT inside Snowflake.
                    parts.append(f"PARSE_JSON(%s) AS {column}")
                    params.append(json.dumps(value, default=str))
                else:
                    parts.append(f"%s AS {column}")
                    params.append(value)
            row_selects.append("SELECT " + ", ".join(parts))
        source_sql = "\nUNION ALL\n".join(row_selects)
        on_clause = " AND ".join(f"t.{k} = s.{k}" for k in key_columns)
        if update_columns:
            set_clause = ", ".join(f"t.{c} = s.{c}" for c in update_columns)
            matched = f"WHEN MATCHED THEN UPDATE SET {set_clause}\n"
        else:
            matched = ""
        insert_cols = ", ".join(columns)
        insert_vals = ", ".join(f"s.{c}" for c in columns)
        sql = (
            f"MERGE INTO {table} t\n"
            f"USING (\n{source_sql}\n) s\n"
            f"ON {on_clause}\n"
            f"{matched}"
            f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
        )
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else len(rows)
        finally:
            cursor.close()

    def insert_rows(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> int:
        if not rows:
            return 0
        # Columns holding dict/list values are sent as JSON text and parsed to VARIANT.
        json_cols = {i for i in range(len(columns)) if any(_is_json_value(r[i]) for r in rows)}
        placeholders = ", ".join(
            "PARSE_JSON(%s)" if i in json_cols else "%s" for i in range(len(columns))
        )
        col_list = ", ".join(columns)
        # PARSE_JSON is not allowed inside VALUES, so this uses INSERT ... SELECT.
        sql = f"INSERT INTO {table} ({col_list}) SELECT {placeholders}"
        prepared = [
            [
                json.dumps(v, default=str) if i in json_cols and v is not None else v
                for i, v in enumerate(r)
            ]
            for r in rows
        ]
        cursor = self._conn.cursor()
        try:
            # executemany() only supports INSERT ... VALUES, so run one statement per row.
            for params in prepared:
                cursor.execute(sql, params)
            return len(rows)
        finally:
            cursor.close()

    # -- scripts and raw storage --------------------------------------------

    def execute_script(self, sql_text: str) -> None:
        cursor = self._conn.cursor()
        try:
            for statement in _split_statements(sql_text):
                cursor.execute(statement)
        finally:
            cursor.close()

    def put_file(self, local_path: Path, stage_path: str) -> None:
        remote = local_path.as_posix()
        self.execute(
            f"PUT 'file://{remote}' {_stage_ref(stage_path)} PARALLEL=1 AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )

    def get_file(self, stage_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        target = local_path.parent.as_posix()
        self.execute(f"GET {_stage_ref(stage_path)} 'file://{target}' PARALLEL=1")

    # -- transactions --------------------------------------------------------

    def begin(self) -> None:
        self.execute("BEGIN TRANSACTION")

    def commit(self) -> None:
        self.execute("COMMIT")

    def rollback(self) -> None:
        try:
            self.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - rollback is best-effort
            logger.warning("ROLLBACK failed; connection state should be revalidated")

    def close(self) -> None:
        self._conn.close()


_MERGE_CHUNK = 500


def _stage_ref(stage_path: str) -> str:
    """Normalize a stage path like ``PROJECT_OPS.RAW_STAGE/raw/...``."""
    return stage_path if stage_path.startswith("@") else f"@{stage_path}"


def _chunk(seq: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _is_json_value(value: Any) -> bool:
    """True for values the Snowflake connector cannot bind directly (dict/list)."""
    return isinstance(value, (dict, list))


def _split_statements(sql_text: str) -> list[str]:
    """Snowflake-aware statement split (see papersonar.warehouse.sqlsplit)."""
    from papersonar.warehouse.sqlsplit import split_sql_statements
    return split_sql_statements(sql_text)

