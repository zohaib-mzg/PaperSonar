"""Versioned, repeatable, non-destructive migration runner.

Migrations live in ``papersonar/warehouse/migrations`` as numbered SQL files.
Applied versions are recorded in ``PROJECT_OPS.SCHEMA_MIGRATION`` with a
checksum; already-applied versions are skipped, and a checksum mismatch on a
previously applied version raises an error instead of silently re-running.
"""

from __future__ import annotations

import importlib.resources
import logging
import re
from dataclasses import dataclass

from papersonar.errors import IngestionError
from papersonar.identifiers import sha256_hex
from papersonar.timeutil import utc_now
from papersonar.warehouse.adapter import Warehouse

logger = logging.getLogger(__name__)

_BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS PROJECT_OPS;
CREATE TABLE IF NOT EXISTS PROJECT_OPS.SCHEMA_MIGRATION (
  VERSION STRING NOT NULL,
  NAME STRING NOT NULL,
  CHECKSUM STRING NOT NULL,
  APPLIED_AT TIMESTAMP_TZ NOT NULL,
  CONSTRAINT PK_SCHEMA_MIGRATION PRIMARY KEY (VERSION)
)
"""

_FILE_RE = re.compile(r"^(\d+)_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return sha256_hex(self.sql.encode("utf-8"))


def load_migrations() -> list[Migration]:
    """Load numbered migration files from the package, sorted by version."""
    root = importlib.resources.files("papersonar.warehouse.migrations")
    migrations: list[Migration] = []
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        match = _FILE_RE.match(entry.name)
        if not match:
            continue
        sql = entry.read_text(encoding="utf-8")
        migrations.append(Migration(version=match.group(1), name=match.group(2), sql=sql))
    if not migrations:
        raise IngestionError("No migration files found in papersonar.warehouse.migrations")
    return migrations


class MigrationRunner:
    """Applies pending migrations exactly once, transactionally."""

    def __init__(self, warehouse: Warehouse) -> None:
        self._warehouse = warehouse

    def bootstrap(self) -> None:
        self._warehouse.execute_script(_BOOTSTRAP_SQL)

    def applied(self) -> dict[str, str]:
        """Map of applied version -> checksum."""
        rows = self._warehouse.execute(
            "SELECT VERSION, CHECKSUM FROM PROJECT_OPS.SCHEMA_MIGRATION ORDER BY VERSION"
        )
        return {version: checksum for version, checksum in rows}

    def apply_all(self) -> list[str]:
        """Apply all pending migrations; return versions applied in this call."""
        self.bootstrap()
        applied = self.applied()
        pending: list[str] = []
        for migration in load_migrations():
            recorded = applied.get(migration.version)
            if recorded is not None:
                if recorded != migration.checksum:
                    raise IngestionError(
                        f"Migration {migration.version} changed since it was applied "
                        f"(checksum mismatch). Write a new migration instead of editing "
                        f"applied history."
                    )
                continue
            pending.append(migration.version)
            logger.info("Applying migration %s_%s", migration.version, migration.name)
            self._warehouse.begin()
            try:
                self._warehouse.execute_script(migration.sql)
                self._warehouse.insert_rows(
                    "PROJECT_OPS.SCHEMA_MIGRATION",
                    ["VERSION", "NAME", "CHECKSUM", "APPLIED_AT"],
                    [[migration.version, migration.name, migration.checksum, utc_now()]],
                )
                self._warehouse.commit()
            except Exception:
                self._warehouse.rollback()
                raise
        if not pending:
            logger.info("No pending migrations")
        return pending
