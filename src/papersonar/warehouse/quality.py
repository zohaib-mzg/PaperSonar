"""Data-quality gates executed as warehouse SQL (COUNT-based checks).

The checks are single-statement SQL executed through the warehouse adapter, so
the same code runs on Snowflake and (for deterministic tests) on the mock
warehouse. Join-based deep integrity SQL ships separately in
``papersonar/warehouse/sql/integrity_checks.sql`` for live Snowflake runs.

Gate policy: the run is marked ``partial`` (never ``succeeded``) when the gate
fails; quarantined records above the configured ratio fail the gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from papersonar.warehouse.adapter import Warehouse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityCheck:
    name: str
    sql: str
    params: list[Any] | None = None
    # pass_when: 'eq0' -> value must be 0; 'lte_ratio' handled by caller
    pass_when: str = "eq0"
    threshold: float | None = None


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    quarantine_ratio: float | None = None
    summary: str = ""


class QualityGate:
    """Runs the standard Phase 2 quality checks and returns a gate result."""

    def __init__(self, warehouse: Warehouse, max_quarantine_ratio: float = 0.20) -> None:
        self._warehouse = warehouse
        self._max_ratio = max_quarantine_ratio

    def run(self) -> QualityGateResult:
        checks_out: list[dict[str, Any]] = []
        accepted = self._count(
            "SELECT COUNT(*) FROM PROJECT_STAGING.STG_WORK_RECORD WHERE VALIDATION_STATUS = 'accepted'"
        )
        quarantined = self._count(
            "SELECT COUNT(*) FROM PROJECT_STAGING.STG_QUARANTINE WHERE RESOLUTION_STATUS = 'open'"
        )
        total = accepted + quarantined
        ratio = (quarantined / total) if total else 0.0

        checks_out.append(
            {
                "name": "staging_accepted_rows",
                "sql": "SELECT COUNT(*) FROM PROJECT_STAGING.STG_WORK_RECORD WHERE VALIDATION_STATUS = 'accepted'",
                "value": accepted,
                "passed": True,  # informational: zero accepted is not an anomaly by itself
                "threshold": None,
            }
        )
        checks_out.append(
            {
                "name": "quarantine_ratio_within_limit",
                "sql": "accepted/quarantine counts",
                "value": round(ratio, 4),
                "passed": ratio <= self._max_ratio,
                "threshold": self._max_ratio,
            }
        )

        simple_checks = (
            ("dim_work_rows", "SELECT COUNT(*) FROM PROJECT_DW.DIM_WORK"),
            ("crosswalk_rows", "SELECT COUNT(*) FROM PROJECT_DW.WORK_SOURCE_XW"),
            ("fact_publication_rows", "SELECT COUNT(*) FROM PROJECT_DW.FACT_PUBLICATION"),
            ("fact_snapshot_rows", "SELECT COUNT(*) FROM PROJECT_DW.FACT_WORK_SNAPSHOT"),
            ("fact_citation_rows", "SELECT COUNT(*) FROM PROJECT_DW.FACT_CITATION"),
        )
        for name, sql in simple_checks:
            value = self._count(sql)
            checks_out.append({"name": name, "sql": sql, "value": value, "passed": True, "threshold": None})

        # Cross-layer consistency: every crosswalk row must map to a canonical work.
        orphan_ratio = self._orphan_ratio()
        checks_out.append(
            {
                "name": "crosswalk_orphan_ratio",
                "sql": "crosswalk rows without canonical work (computed via adapter)",
                "value": round(orphan_ratio, 4),
                "passed": orphan_ratio <= 0.0,
                "threshold": 0.0,
            }
        )

        surrogate_checks = (
            ("dim_work_missing_sk", "PROJECT_DW.DIM_WORK", "WORK_SK"),
            ("dim_date_missing_sk", "PROJECT_DW.DIM_DATE", "DATE_SK"),
            ("dim_topic_missing_sk", "PROJECT_DW.DIM_TOPIC", "TOPIC_SK"),
            ("dim_venue_missing_sk", "PROJECT_DW.DIM_VENUE", "VENUE_SK"),
            ("dim_work_type_missing_sk", "PROJECT_DW.DIM_WORK_TYPE", "WORK_TYPE_SK"),
            ("dim_access_status_missing_sk", "PROJECT_DW.DIM_ACCESS_STATUS", "ACCESS_STATUS_SK"),
            ("dim_author_missing_sk", "PROJECT_DW.DIM_AUTHOR", "AUTHOR_SK"),
            ("dim_institution_missing_sk", "PROJECT_DW.DIM_INSTITUTION", "INSTITUTION_SK"),
            ("publication_work_missing_sk", "PROJECT_DW.FACT_PUBLICATION", "WORK_SK"),
            ("publication_date_missing_sk", "PROJECT_DW.FACT_PUBLICATION", "PUBLICATION_DATE_SK"),
            ("publication_type_missing_sk", "PROJECT_DW.FACT_PUBLICATION", "WORK_TYPE_SK"),
            ("publication_venue_missing_sk", "PROJECT_DW.FACT_PUBLICATION", "VENUE_SK"),
            ("publication_access_missing_sk", "PROJECT_DW.FACT_PUBLICATION", "ACCESS_STATUS_SK"),
            ("snapshot_work_missing_sk", "PROJECT_DW.FACT_WORK_SNAPSHOT", "WORK_SK"),
            ("snapshot_date_missing_sk", "PROJECT_DW.FACT_WORK_SNAPSHOT", "SNAPSHOT_DATE_SK"),
            ("snapshot_access_missing_sk", "PROJECT_DW.FACT_WORK_SNAPSHOT", "ACCESS_STATUS_SK"),
            ("citation_citing_missing_sk", "PROJECT_DW.FACT_CITATION", "WORK_SK"),
            ("topic_bridge_work_missing_sk", "PROJECT_DW.BRIDGE_WORK_TOPIC", "WORK_SK"),
            ("topic_bridge_topic_missing_sk", "PROJECT_DW.BRIDGE_WORK_TOPIC", "TOPIC_SK"),
            ("author_bridge_work_missing_sk", "PROJECT_DW.BRIDGE_WORK_AUTHOR", "WORK_SK"),
            ("author_bridge_author_missing_sk", "PROJECT_DW.BRIDGE_WORK_AUTHOR", "AUTHOR_SK"),
            ("institution_bridge_work_missing_sk", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "WORK_SK"),
            ("institution_bridge_institution_missing_sk", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "INSTITUTION_SK"),
            ("institution_bridge_author_missing_sk", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "AUTHOR_SK"),
        )
        for name, table, column in surrogate_checks:
            sql = f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
            value = self._count(sql)
            checks_out.append({"name": name, "sql": sql, "value": value, "passed": value == 0, "threshold": 0})
        cited_sql = (
            "SELECT COUNT(*) FROM PROJECT_DW.FACT_CITATION "
            "WHERE CITED_WORK_KEY != '' AND CITED_WORK_SK IS NULL"
        )
        cited_missing = self._count(cited_sql)
        checks_out.append(
            {
                "name": "citation_resolved_target_missing_sk",
                "sql": cited_sql,
                "value": cited_missing,
                "passed": cited_missing == 0,
                "threshold": 0,
            }
        )
        passed = all(check["passed"] for check in checks_out)
        summary = "PASS" if passed else "FAIL"
        return QualityGateResult(passed=passed, checks=checks_out, quarantine_ratio=ratio, summary=summary)

    def _count(self, sql: str) -> int:
        rows = self._warehouse.execute(sql)
        if not rows:
            return 0
        return int(rows[0][0] or 0)

    def _orphan_ratio(self) -> float:
        crosswalk_keys = self._warehouse.execute(
            "SELECT WORK_KEY FROM PROJECT_DW.WORK_SOURCE_XW"
        )
        if not crosswalk_keys:
            return 0.0
        dim_rows = self._warehouse.execute("SELECT WORK_KEY FROM PROJECT_DW.DIM_WORK")
        existing = {row[0] for row in dim_rows or []}
        missing = sum(1 for (work_key,) in crosswalk_keys if work_key not in existing)
        return missing / len(crosswalk_keys)

