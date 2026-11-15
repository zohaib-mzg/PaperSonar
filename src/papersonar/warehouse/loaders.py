"""Warehouse loading: staging upsert, canonical/dimension/fact/bridge loads.

Every load path is MERGE-based (via ``Warehouse.upsert_rows``) and therefore
idempotent: replaying the same batch produces no duplicate rows. Dimension keys
are deterministic natural keys (source-qualified IDs or hashes of normalized
names), so loads from repeated runs converge.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from papersonar.canonical import (
    _CROSSWALK_COLUMNS,
    _DIM_WORK_COLUMNS,
    CanonicalOutcome,
    CanonicalResolver,
)
from papersonar.identifiers import normalize_title
from papersonar.staging import StagingOutcome, StagingRow
from papersonar.timeutil import utc_now
from papersonar.warehouse.adapter import Warehouse
from papersonar.warehouse.state_store import StateStore

logger = logging.getLogger(__name__)

STAGING_COLUMNS = (
    "STAGING_ID",
    "RUN_ID",
    "BATCH_ID",
    "SOURCE_NAME",
    "SOURCE_RECORD_ID",
    "SOURCE_UPDATED_AT",
    "DOI_RAW",
    "DOI_NORMALIZED",
    "TITLE",
    "TITLE_NORMALIZED",
    "PUBLICATION_DATE",
    "PUBLICATION_YEAR",
    "WORK_TYPE",
    "VENUE_NAME",
    "OA_IS_OA",
    "OA_STATUS",
    "CITED_BY_COUNT",
    "REFERENCED_WORKS",
    "TOPICS",
    "AUTHORSHIPS",
    "RELATED_IDENTIFIERS",
    "PAYLOAD_SHA256",
    "PARSER_VERSION",
    "SCHEMA_VERSION",
    "VALIDATION_STATUS",
    "VALIDATION_REASON",
    "INGESTED_AT",
)

_UNKNOWN = "-1"


class WarehouseLoader:
    """Idempotent MERGE-based loads for staging and the dimensional warehouse."""

    def __init__(self, warehouse: Warehouse, resolver: CanonicalResolver | None = None) -> None:
        self._warehouse = warehouse
        self._resolver = resolver or CanonicalResolver(warehouse)
        self._state = StateStore(warehouse)

    # -- staging -------------------------------------------------------------

    def load_staging(self, outcome: StagingOutcome) -> int:
        """Upsert staging rows; PK (source, record id, payload hash) keeps history."""
        rows = [row.row(STAGING_COLUMNS) for row in outcome.accepted]
        return self._warehouse.upsert_rows(
            "PROJECT_STAGING.STG_WORK_RECORD",
            ["SOURCE_NAME", "SOURCE_RECORD_ID", "PAYLOAD_SHA256"],
            list(STAGING_COLUMNS),
            rows,
        )

    def load_quarantine(self, outcome: StagingOutcome) -> int:
        for entry in outcome.quarantined:
            self._state.quarantine(
                quarantine_id=entry.quarantine_id,
                run_id=entry.run_id,
                source_name=entry.source_name,
                source_record_id=entry.source_record_id,
                reason_code=entry.reason_code,
                detail=entry.detail,
                batch_id=entry.batch_id,
            )
        return len(outcome.quarantined)

    # -- canonical -----------------------------------------------------------

    def load_canonical(self, outcome: CanonicalOutcome) -> int:
        loaded = 0
        if outcome.crosswalk_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.WORK_SOURCE_XW",
                ["SOURCE_NAME", "SOURCE_RECORD_ID"],
                list(_CROSSWALK_COLUMNS),
                [[row[column] for column in _CROSSWALK_COLUMNS] for row in outcome.crosswalk_rows],
            )
            self._sync_surrogate(
                "WORK", "PROJECT_DW.WORK_SOURCE_XW", "WORK_KEY", "WORK_SK", outcome.crosswalk_rows
            )
        if outcome.canonical_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_WORK",
                ["WORK_KEY"],
                list(_DIM_WORK_COLUMNS),
                [[row[column] for column in _DIM_WORK_COLUMNS] for row in outcome.canonical_rows],
            )
            self._sync_surrogate(
                "WORK", "PROJECT_DW.DIM_WORK", "WORK_KEY", "WORK_SK", outcome.canonical_rows
            )
        return loaded
    # -- dimensions and bridges ----------------------------------------------

    def load_dimensions(self, resolved_rows: list[StagingRow]) -> int:
        loaded = 0
        now = utc_now()
        topic_rows, topic_bridge = _topic_rows(resolved_rows, now)
        author_rows, author_bridge, institution_rows, institution_bridge = _author_rows(resolved_rows, now)
        venue_rows = _venue_rows(resolved_rows)
        type_rows = _type_rows(resolved_rows)
        access_rows = _access_rows(resolved_rows)

        if topic_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_TOPIC",
                ["TOPIC_KEY"],
                ["TOPIC_KEY", "SOURCE_NAME", "TOPIC_ID", "TOPIC_NAME"],
                [[r[c] for c in ("TOPIC_KEY", "SOURCE_NAME", "TOPIC_ID", "TOPIC_NAME")] for r in topic_rows],
            )
        if topic_bridge:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.BRIDGE_WORK_TOPIC",
                ["WORK_KEY", "TOPIC_KEY", "SOURCE_NAME"],
                ["WORK_KEY", "TOPIC_KEY", "IS_PRIMARY", "SCORE", "SOURCE_NAME"],
                [[r[c] for c in ("WORK_KEY", "TOPIC_KEY", "IS_PRIMARY", "SCORE", "SOURCE_NAME")] for r in topic_bridge],
            )
        if author_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_AUTHOR",
                ["AUTHOR_KEY"],
                ["AUTHOR_KEY", "SOURCE_NAME", "AUTHOR_ID", "AUTHOR_NAME", "ORCID"],
                [
                    [r[c] for c in ("AUTHOR_KEY", "SOURCE_NAME", "AUTHOR_ID", "AUTHOR_NAME", "ORCID")]
                    for r in author_rows
                ],
            )
        if author_bridge:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.BRIDGE_WORK_AUTHOR",
                ["WORK_KEY", "AUTHOR_KEY", "SOURCE_NAME"],
                ["WORK_KEY", "AUTHOR_KEY", "POSITION", "SOURCE_NAME"],
                [[r[c] for c in ("WORK_KEY", "AUTHOR_KEY", "POSITION", "SOURCE_NAME")] for r in author_bridge],
            )
        if institution_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_INSTITUTION",
                ["INSTITUTION_KEY"],
                ["INSTITUTION_KEY", "SOURCE_NAME", "INSTITUTION_ID", "INSTITUTION_NAME"],
                [
                    [r[c] for c in ("INSTITUTION_KEY", "SOURCE_NAME", "INSTITUTION_ID", "INSTITUTION_NAME")]
                    for r in institution_rows
                ],
            )
        if institution_bridge:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.BRIDGE_WORK_INSTITUTION",
                ["WORK_KEY", "INSTITUTION_KEY", "AUTHOR_KEY", "SOURCE_NAME"],
                ["WORK_KEY", "INSTITUTION_KEY", "AUTHOR_KEY", "SOURCE_NAME"],
                [
                    [r[c] for c in ("WORK_KEY", "INSTITUTION_KEY", "AUTHOR_KEY", "SOURCE_NAME")]
                    for r in institution_bridge
                ],
            )
        if venue_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_VENUE",
                ["VENUE_KEY"],
                ["VENUE_KEY", "SOURCE_NAME", "VENUE_ID", "VENUE_NAME"],
                [[r[c] for c in ("VENUE_KEY", "SOURCE_NAME", "VENUE_ID", "VENUE_NAME")] for r in venue_rows],
            )
        if type_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_WORK_TYPE",
                ["WORK_TYPE_KEY"],
                ["WORK_TYPE_KEY", "WORK_TYPE_NAME"],
                [[r["WORK_TYPE_KEY"], r["WORK_TYPE_NAME"]] for r in type_rows],
            )
        if access_rows:
            loaded += self._warehouse.upsert_rows(
                "PROJECT_DW.DIM_ACCESS_STATUS",
                ["ACCESS_STATUS_KEY"],
                ["ACCESS_STATUS_KEY", "ACCESS_STATUS_NAME"],
                [[r["ACCESS_STATUS_KEY"], r["ACCESS_STATUS_NAME"]] for r in access_rows],
            )
        self._sync_surrogate("TOPIC", "PROJECT_DW.DIM_TOPIC", "TOPIC_KEY", "TOPIC_SK", topic_rows)
        self._sync_surrogate("AUTHOR", "PROJECT_DW.DIM_AUTHOR", "AUTHOR_KEY", "AUTHOR_SK", author_rows)
        self._sync_surrogate(
            "INSTITUTION", "PROJECT_DW.DIM_INSTITUTION", "INSTITUTION_KEY", "INSTITUTION_SK", institution_rows
        )
        self._sync_surrogate("VENUE", "PROJECT_DW.DIM_VENUE", "VENUE_KEY", "VENUE_SK", venue_rows)
        self._sync_surrogate("WORK_TYPE", "PROJECT_DW.DIM_WORK_TYPE", "WORK_TYPE_KEY", "WORK_TYPE_SK", type_rows)
        self._sync_surrogate(
            "ACCESS_STATUS", "PROJECT_DW.DIM_ACCESS_STATUS", "ACCESS_STATUS_KEY", "ACCESS_STATUS_SK", access_rows
        )
        self._sync_surrogate("WORK", "PROJECT_DW.BRIDGE_WORK_TOPIC", "WORK_KEY", "WORK_SK", topic_bridge)
        self._sync_surrogate("TOPIC", "PROJECT_DW.BRIDGE_WORK_TOPIC", "TOPIC_KEY", "TOPIC_SK", topic_bridge)
        self._sync_surrogate("WORK", "PROJECT_DW.BRIDGE_WORK_AUTHOR", "WORK_KEY", "WORK_SK", author_bridge)
        self._sync_surrogate("AUTHOR", "PROJECT_DW.BRIDGE_WORK_AUTHOR", "AUTHOR_KEY", "AUTHOR_SK", author_bridge)
        self._sync_surrogate("WORK", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "WORK_KEY", "WORK_SK", institution_bridge)
        self._sync_surrogate(
            "INSTITUTION", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "INSTITUTION_KEY", "INSTITUTION_SK",
            institution_bridge,
        )
        self._sync_surrogate(
            "AUTHOR", "PROJECT_DW.BRIDGE_WORK_INSTITUTION", "AUTHOR_KEY", "AUTHOR_SK", institution_bridge
        )
        self._load_date_dimensions([row.publication_date for row in resolved_rows])
        return loaded

    def _sync_surrogate(
        self, dimension: str, table: str, business_column: str, surrogate_column: str,
        rows: list[dict[str, Any]],
    ) -> None:
        keys = [str(row[business_column]) for row in rows if row.get(business_column) is not None]
        self._warehouse.sync_surrogate_key_column(
            dimension, table, business_column, surrogate_column, keys
        )

    def _load_date_dimensions(self, values: list[Any]) -> None:
        from datetime import date

        unique_dates: dict[int, date] = {}
        for value in values:
            parsed = None
            if isinstance(value, date):
                parsed = value
            elif isinstance(value, str) and len(value) == 10:
                try:
                    parsed = date.fromisoformat(value)
                except ValueError:
                    parsed = None
            if parsed is not None:
                unique_dates[int(parsed.strftime("%Y%m%d"))] = parsed
        rows = [[0, None, None, None, None, "Unknown", None, None, False]]
        for key, full_date in sorted(unique_dates.items()):
            rows.append([
                key, full_date, full_date.year, (full_date.month - 1) // 3 + 1, full_date.month,
                full_date.strftime("%B"), full_date.day, full_date.isoweekday(), full_date.weekday() >= 5,
            ])
        self._warehouse.upsert_rows(
            "PROJECT_DW.DIM_DATE", ["DATE_KEY"],
            ["DATE_KEY", "FULL_DATE", "YEAR_NUMBER", "QUARTER", "MONTH_NUMBER",
             "MONTH_NAME", "DAY_OF_MONTH", "DAY_OF_WEEK", "IS_WEEKEND"], rows,
        )
        self._sync_surrogate(
            "DATE", "PROJECT_DW.DIM_DATE", "DATE_KEY", "DATE_SK",
            [{"DATE_KEY": row[0]} for row in rows],
        )
    # -- facts ---------------------------------------------------------------

    def load_facts(self, outcome: CanonicalOutcome, run_id: str) -> int:
        loaded = 0
        now = utc_now()
        self._load_date_dimensions([now.date().isoformat()])
        loaded += self._load_fact_publication(outcome.canonical_rows, now)
        loaded += self._load_fact_snapshot(outcome.canonical_rows, run_id, now)
        loaded += self._load_fact_citation(outcome.resolved_rows, now)
        self._sync_fact_surrogates(outcome, now)
        return loaded

    def _sync_fact_surrogates(self, outcome: CanonicalOutcome, now: datetime) -> None:
        canonical = outcome.canonical_rows
        work_rows = [{"WORK_KEY": row["WORK_KEY"]} for row in canonical]
        self._sync_surrogate("WORK", "PROJECT_DW.FACT_PUBLICATION", "WORK_KEY", "WORK_SK", work_rows)
        self._sync_surrogate("WORK", "PROJECT_DW.FACT_WORK_SNAPSHOT", "WORK_KEY", "WORK_SK", work_rows)
        self._sync_surrogate(
            "DATE", "PROJECT_DW.FACT_PUBLICATION", "PUBLICATION_DATE_KEY", "PUBLICATION_DATE_SK",
            [{"PUBLICATION_DATE_KEY": _publication_date_key(row.get("PUBLICATION_DATE"))} for row in canonical],
        )
        self._sync_surrogate(
            "DATE", "PROJECT_DW.FACT_WORK_SNAPSHOT", "SNAPSHOT_DATE_KEY", "SNAPSHOT_DATE_SK",
            [{"SNAPSHOT_DATE_KEY": int(now.strftime("%Y%m%d"))}],
        )
        self._sync_surrogate(
            "WORK_TYPE", "PROJECT_DW.FACT_PUBLICATION", "WORK_TYPE_KEY", "WORK_TYPE_SK",
            [{"WORK_TYPE_KEY": _type_key(row.get("WORK_TYPE"))} for row in canonical],
        )
        self._sync_surrogate(
            "VENUE", "PROJECT_DW.FACT_PUBLICATION", "VENUE_KEY", "VENUE_SK",
            [{"VENUE_KEY": _venue_key(row.get("SOURCE_PRIORITY"), row.get("VENUE_NAME"))} for row in canonical],
        )
        status_rows = [{"ACCESS_STATUS_KEY": _access_key(row.get("OA_STATUS"))} for row in canonical]
        self._sync_surrogate(
            "ACCESS_STATUS", "PROJECT_DW.FACT_PUBLICATION", "ACCESS_STATUS_KEY", "ACCESS_STATUS_SK", status_rows
        )
        self._sync_surrogate(
            "ACCESS_STATUS", "PROJECT_DW.FACT_WORK_SNAPSHOT", "ACCESS_STATUS_KEY", "ACCESS_STATUS_SK", status_rows
        )
        work_keys = [self._resolver.work_key_for(row) for row in outcome.resolved_rows]
        self._sync_surrogate(
            "WORK", "PROJECT_DW.FACT_CITATION", "WORK_KEY", "WORK_SK", [{"WORK_KEY": key} for key in work_keys]
        )
        from papersonar.identifiers import normalize_doi
        cited_rows = []
        for row in outcome.resolved_rows:
            for entry in row.referenced_works or []:
                if isinstance(entry, dict) and entry.get("kind") == "doi" and entry.get("value"):
                    cited = self._resolver.lookup_work_key_by_doi(normalize_doi(str(entry["value"])) or "")
                    if cited:
                        cited_rows.append({"CITED_WORK_KEY": cited})
        self._sync_surrogate(
            "WORK", "PROJECT_DW.FACT_CITATION", "CITED_WORK_KEY", "CITED_WORK_SK", cited_rows
        )
    def _load_fact_publication(self, canonical_rows: list[dict[str, Any]], now: datetime) -> int:
        if not canonical_rows:
            return 0
        rows = []
        for canonical in canonical_rows:
            source = canonical.get("SOURCE_PRIORITY")
            rows.append(
                [
                    canonical["WORK_KEY"],
                    canonical.get("DOI_NORMALIZED"),
                    canonical.get("PUBLICATION_DATE"),
                    _publication_date_key(canonical.get("PUBLICATION_DATE")),
                    canonical.get("PUBLICATION_YEAR"),
                    _type_key(canonical.get("WORK_TYPE")),
                    _venue_key(source, canonical.get("VENUE_NAME")),
                    _access_key(canonical.get("OA_STATUS")),
                    canonical.get("CITED_BY_COUNT"),
                    source,
                    canonical.get("FIRST_SEEN_AT") or now,
                    canonical.get("LAST_UPDATED_AT") or now,
                ]
            )
        return self._warehouse.upsert_rows(
            "PROJECT_DW.FACT_PUBLICATION",
            ["WORK_KEY"],
            [
                "WORK_KEY",
                "DOI_NORMALIZED",
                "PUBLICATION_DATE",
                "PUBLICATION_DATE_KEY",
                "PUBLICATION_YEAR",
                "WORK_TYPE_KEY",
                "VENUE_KEY",
                "ACCESS_STATUS_KEY",
                "CITED_BY_COUNT",
                "SOURCE_PRIORITY",
                "FIRST_SEEN_AT",
                "LAST_UPDATED_AT",
            ],
            rows,
        )

    def _load_fact_snapshot(self, canonical_rows: list[dict[str, Any]], run_id: str, now: datetime) -> int:
        if not canonical_rows:
            return 0
        date_key = int(now.strftime("%Y%m%d"))
        rows = [
            [
                canonical["WORK_KEY"],
                date_key,
                canonical.get("CITED_BY_COUNT"),
                canonical.get("OA_IS_OA"),
                canonical.get("OA_STATUS"),
                _access_key(canonical.get("OA_STATUS")),
                run_id,
            ]
            for canonical in canonical_rows
        ]
        return self._warehouse.upsert_rows(
            "PROJECT_DW.FACT_WORK_SNAPSHOT",
            ["WORK_KEY", "SNAPSHOT_DATE_KEY"],
            ["WORK_KEY", "SNAPSHOT_DATE_KEY", "CITED_BY_COUNT", "OA_IS_OA", "OA_STATUS", "ACCESS_STATUS_KEY", "RUN_ID"],
            rows,
        )

    def _load_fact_citation(self, resolved_rows: list[StagingRow], now: datetime) -> int:
        if not resolved_rows:
            return 0
        from papersonar.identifiers import normalize_doi

        rows: dict[tuple[str, str, str, str], list[Any]] = {}
        for row in resolved_rows:
            work_key = self._resolver.work_key_for(row)
            for entry in row.referenced_works or []:
                kind = entry.get("kind") if isinstance(entry, dict) else None
                value = str(entry.get("value")) if isinstance(entry, dict) and entry.get("value") else None
                if not value:
                    continue
                if kind == "doi":
                    cited_doi = normalize_doi(value) or ""
                    cited_provider = ""
                    cited_work_key = self._resolver.lookup_work_key_by_doi(cited_doi) or "" if cited_doi else ""
                else:
                    cited_doi = ""
                    cited_provider = value
                    cited_work_key = ""
                key = (work_key, cited_doi, cited_provider, row.source_name)
                if key not in rows:
                    rows[key] = [work_key, cited_work_key, cited_doi, cited_provider, row.source_name, now]
        if not rows:
            return 0
        return self._warehouse.upsert_rows(
            "PROJECT_DW.FACT_CITATION",
            ["WORK_KEY", "CITED_DOI", "CITED_PROVIDER_ID", "SOURCE_NAME"],
            ["WORK_KEY", "CITED_WORK_KEY", "CITED_DOI", "CITED_PROVIDER_ID", "SOURCE_NAME", "FIRST_SEEN_AT"],
            list(rows.values()),
        )

    def refresh_citation_resolution(self) -> int:
        """Re-resolve unresolved citation edges against the current crosswalk.

        Cited works may be ingested after the citing record; this back-fills
        ``CITED_WORK_KEY`` for open edges using the DOI crosswalk.
        """
        rows = self._warehouse.execute(
            "SELECT WORK_KEY, CITED_DOI, CITED_PROVIDER_ID, SOURCE_NAME "
            "FROM PROJECT_DW.FACT_CITATION WHERE CITED_WORK_KEY = '' AND CITED_DOI != ''"
        )
        if not rows:
            return 0
        now = utc_now()
        updated = 0
        for work_key, cited_doi, provider, source in rows:
            resolved = self._resolver.lookup_work_key_by_doi(str(cited_doi))
            if not resolved:
                continue
            self._warehouse.upsert_rows(
                "PROJECT_DW.FACT_CITATION",
                ["WORK_KEY", "CITED_DOI", "CITED_PROVIDER_ID", "SOURCE_NAME"],
                ["WORK_KEY", "CITED_WORK_KEY", "CITED_DOI", "CITED_PROVIDER_ID", "SOURCE_NAME", "FIRST_SEEN_AT"],
                [[work_key, resolved, cited_doi, provider, source, now]],
                update_columns=["CITED_WORK_KEY"],
            )
            self._warehouse.sync_surrogate_key_column(
                "WORK", "PROJECT_DW.FACT_CITATION", "CITED_WORK_KEY", "CITED_WORK_SK", [resolved]
            )
            updated += 1
        return updated


# ---------------------------------------------------------------------------
# Deterministic key helpers
# ---------------------------------------------------------------------------


def _publication_date_key(value: Any) -> int:
    if not isinstance(value, str) or len(value) != 10:
        return 0
    from datetime import date

    try:
        return int(date.fromisoformat(value).strftime("%Y%m%d"))
    except ValueError:
        return 0

def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _clean_key_part(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _topic_rows(resolved_rows: list[StagingRow], now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dims: dict[str, dict[str, Any]] = {}
    bridges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in resolved_rows:
        work_key = _work_key_direct(row)
        for topic in row.topics or []:
            if not isinstance(topic, dict):
                continue
            topic_id = _clean_key_part(topic.get("id"))
            name = _clean_key_part(topic.get("name"))
            name_hash_part = f"name:{_hash_text(name or '')}"
            key = f"{row.source_name}:{topic_id or name_hash_part}"
            dims[key] = {
                "TOPIC_KEY": key,
                "SOURCE_NAME": row.source_name,
                "TOPIC_ID": topic_id,
                "TOPIC_NAME": name,
            }
            bridge_key = (work_key, key, row.source_name)
            bridges[bridge_key] = {
                "WORK_KEY": work_key,
                "TOPIC_KEY": key,
                "IS_PRIMARY": bool(topic.get("primary")),
                "SCORE": topic.get("score"),
                "SOURCE_NAME": row.source_name,
            }
    return list(dims.values()), list(bridges.values())


def _author_rows(
    resolved_rows: list[StagingRow], now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    authors: dict[str, dict[str, Any]] = {}
    author_bridges: dict[tuple[str, str, str], dict[str, Any]] = {}
    institutions: dict[str, dict[str, Any]] = {}
    institution_bridges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in resolved_rows:
        work_key = _work_key_direct(row)
        for authorship in row.authorships or []:
            if not isinstance(authorship, dict):
                continue
            author_id = _clean_key_part(authorship.get("author_id"))
            name = _clean_key_part(authorship.get("author_name"))
            author_name_part = f"name:{_hash_text(name or '')}"
            author_key = f"{row.source_name}:{author_id or author_name_part}"
            authors[author_key] = {
                "AUTHOR_KEY": author_key,
                "SOURCE_NAME": row.source_name,
                "AUTHOR_ID": author_id,
                "AUTHOR_NAME": name,
                "ORCID": _clean_key_part(authorship.get("orcid")),
            }
            author_bridges[(work_key, author_key, row.source_name)] = {
                "WORK_KEY": work_key,
                "AUTHOR_KEY": author_key,
                "POSITION": _clean_key_part(authorship.get("position")),
                "SOURCE_NAME": row.source_name,
            }
            for institution in authorship.get("institutions") or []:
                if not isinstance(institution, dict):
                    continue
                inst_id = _clean_key_part(institution.get("id"))
                inst_name = _clean_key_part(institution.get("name"))
                inst_name_part = f"name:{_hash_text(inst_name or '')}"
                inst_key = f"{row.source_name}:{inst_id or inst_name_part}"
                institutions[inst_key] = {
                    "INSTITUTION_KEY": inst_key,
                    "SOURCE_NAME": row.source_name,
                    "INSTITUTION_ID": inst_id,
                    "INSTITUTION_NAME": inst_name,
                }
                institution_bridges[(work_key, inst_key, author_key, row.source_name)] = {
                    "WORK_KEY": work_key,
                    "INSTITUTION_KEY": inst_key,
                    "AUTHOR_KEY": author_key,
                    "SOURCE_NAME": row.source_name,
                }
    return (
        list(authors.values()),
        list(author_bridges.values()),
        list(institutions.values()),
        list(institution_bridges.values()),
    )


def _venue_rows(resolved_rows: list[StagingRow]) -> list[dict[str, Any]]:
    dims: dict[str, dict[str, Any]] = {}
    for row in resolved_rows:
        if row.venue_name:
            key = _venue_key(row.source_name, row.venue_name)
            dims[key] = {
                "VENUE_KEY": key,
                "SOURCE_NAME": row.source_name,
                "VENUE_ID": None,
                "VENUE_NAME": row.venue_name,
            }
    return list(dims.values())


def _type_rows(resolved_rows: list[StagingRow]) -> list[dict[str, Any]]:
    dims: dict[str, dict[str, Any]] = {}
    for row in resolved_rows:
        key = _type_key(row.work_type)
        if key != _UNKNOWN:
            dims[key] = {"WORK_TYPE_KEY": key, "WORK_TYPE_NAME": str(row.work_type)}
    return list(dims.values())


def _access_rows(resolved_rows: list[StagingRow]) -> list[dict[str, Any]]:
    dims: dict[str, dict[str, Any]] = {}
    for row in resolved_rows:
        key = _access_key(row.oa_status)
        if key != _UNKNOWN:
            dims[key] = {"ACCESS_STATUS_KEY": key, "ACCESS_STATUS_NAME": str(row.oa_status)}
    return list(dims.values())


def _venue_key(source: str | None, venue_name: str | None) -> str:
    source = source or "unknown"
    name = _clean_key_part(venue_name)
    if not name:
        return _UNKNOWN
    return f"{source}:name:{_hash_text(normalize_title(name) or '')}"


def _type_key(work_type: str | None) -> str:
    value = _clean_key_part(work_type)
    if not value:
        return _UNKNOWN
    return value.strip().lower()


def _access_key(oa_status: str | None) -> str:
    value = _clean_key_part(oa_status)
    if not value:
        return _UNKNOWN
    return value.strip().lower()


def _work_key_direct(row: StagingRow) -> str:
    from papersonar.identifiers import normalize_doi

    doi = row.doi_normalized or normalize_doi(row.doi_raw)
    if doi:
        return f"doi:{doi}"
    return f"src:{row.source_name}:{row.source_record_id}"
