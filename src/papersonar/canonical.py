"""Canonical identity resolution: DOI crosswalk, conflict quarantine, field merge.

Resolution rules (documented, deterministic, testable):

- ``work_key``: ``doi:<normalized_doi>`` when a usable DOI exists, else
  ``src:<source_name>:<source_record_id>``.
- DOI-bearing records whose loose-normalized title conflicts with the stored
  canonical title are quarantined for review (never auto-merged silently).
- A source record keeps its crosswalk work_key; a changed mapping is
  quarantined (``doi_change_review``) instead of silently re-pointing.
- Canonical field merge: records are applied lowest to highest source priority
  (openalex > crossref > datacite > zenodo > arxiv), latest observation first
  within a source. Lower-priority values only fill missing fields;
  higher-priority non-null values may update. A null never overwrites an
  existing non-null value. Identical (priority, timestamp) records tiebreak on
  payload hash, so multiple content versions in one batch can never produce
  ambiguous updates.

All reads and writes go through warehouse SQL (SELECT + MERGE upserts).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from papersonar.identifiers import normalize_doi, normalize_title
from papersonar.staging import QUARANTINE_CONFLICTING_DOI, QuarantineEntry, StagingRow
from papersonar.timeutil import utc_now
from papersonar.warehouse.adapter import Warehouse

logger = logging.getLogger(__name__)

# Canonical field precedence (highest wins). Configurable via extra PRIORITY.
DEFAULT_SOURCE_PRIORITY: tuple[str, ...] = ("openalex", "crossref", "datacite", "zenodo", "arxiv")

QUARANTINE_DOI_CHANGE = "doi_change_review"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_DIM_WORK_COLUMNS = (
    "WORK_KEY",
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
    "SOURCE_PRIORITY",
    "FIRST_SEEN_AT",
    "LAST_UPDATED_AT",
)

_CROSSWALK_COLUMNS = (
    "SOURCE_NAME",
    "SOURCE_RECORD_ID",
    "WORK_KEY",
    "DOI_NORMALIZED",
    "FIRST_SEEN_AT",
    "LAST_SEEN_AT",
)


@dataclass
class CanonicalOutcome:
    canonical_rows: list[dict[str, Any]] = field(default_factory=list)
    crosswalk_rows: list[dict[str, Any]] = field(default_factory=list)
    quarantine_entries: list[QuarantineEntry] = field(default_factory=list)
    resolved_rows: list[StagingRow] = field(default_factory=list)
    works_resolved: int = 0
    conflicts: int = 0


class CanonicalResolver:
    """Resolves staging rows into canonical works via the warehouse."""

    def __init__(self, warehouse: Warehouse, source_priority: tuple[str, ...] = DEFAULT_SOURCE_PRIORITY) -> None:
        self._warehouse = warehouse
        self.source_priority = source_priority
        # Per-batch read caches (None = not prefetching; fall back to single-row queries).
        self._dim_cache: dict[str, dict[str, Any] | None] | None = None
        self._xw_cache: dict[tuple[str, str], dict[str, Any] | None] | None = None

    # -- public API ----------------------------------------------------------

    def resolve_batch(self, rows: list[StagingRow], run_id: str) -> CanonicalOutcome:
        """Resolve a batch of validated staging rows."""
        outcome = CanonicalOutcome()
        by_key: dict[str, list[StagingRow]] = {}
        for row in rows:
            by_key.setdefault(self.work_key_for(row), []).append(row)
        now = utc_now()
        self._prefetch(list(by_key), rows)
        try:
            for work_key, group in sorted(by_key.items()):
                resolved = self._resolve_work(work_key, group, run_id, now, outcome)
                if resolved:
                    outcome.works_resolved += 1
        finally:
            self._dim_cache = None
            self._xw_cache = None
        return outcome

    def _prefetch(self, work_keys: list[str], rows: list[StagingRow]) -> None:
        """Bulk-load existing DIM_WORK and crosswalk rows for this batch."""
        dim_columns = ", ".join(_DIM_WORK_COLUMNS)
        dim_cache: dict[str, dict[str, Any] | None] = {key: None for key in work_keys}
        for chunk in _chunks(sorted(work_keys)):
            marks = ", ".join(["%s"] * len(chunk))
            result = self._warehouse.execute(
                f"SELECT WORK_KEY, {dim_columns} FROM PROJECT_DW.DIM_WORK WHERE WORK_KEY IN ({marks})",
                list(chunk),
            )
            for found in result or []:
                if dim_cache.get(found[0]) is None:
                    dim_cache[found[0]] = dict(zip(_DIM_WORK_COLUMNS, found[1:], strict=True))

        ids_by_source: dict[str, set[str]] = {}
        for row in rows:
            if row.source_record_id:
                ids_by_source.setdefault(row.source_name, set()).add(row.source_record_id)
        xw_columns = ", ".join(_CROSSWALK_COLUMNS)
        xw_cache: dict[tuple[str, str], dict[str, Any] | None] = {
            (source, record_id): None for source, ids in ids_by_source.items() for record_id in ids
        }
        for source, ids in sorted(ids_by_source.items()):
            for chunk in _chunks(sorted(ids)):
                marks = ", ".join(["%s"] * len(chunk))
                result = self._warehouse.execute(
                    f"SELECT SOURCE_NAME, SOURCE_RECORD_ID, {xw_columns} "
                    "FROM PROJECT_DW.WORK_SOURCE_XW "
                    f"WHERE SOURCE_NAME = %s AND SOURCE_RECORD_ID IN ({marks})",
                    [source, *chunk],
                )
                for found in result or []:
                    if xw_cache.get((found[0], found[1])) is None:
                        xw_cache[(found[0], found[1])] = dict(
                            zip(_CROSSWALK_COLUMNS, found[2:], strict=True)
                        )
        self._dim_cache = dim_cache
        self._xw_cache = xw_cache

    def work_key_for(self, row: StagingRow) -> str:
        doi = row.doi_normalized or normalize_doi(row.doi_raw)
        if doi:
            return f"doi:{doi}"
        if not row.source_record_id:
            # Defensive: validator should have quarantined this earlier.
            raise ValueError(f"staging row without source_record_id: {row.staging_id}")
        return f"src:{row.source_name}:{row.source_record_id}"

    def lookup_work_key_by_doi(self, doi_normalized: str) -> str | None:
        """Citation resolution helper: DOI -> canonical work key."""
        rows = self._warehouse.execute(
            "SELECT WORK_KEY FROM PROJECT_DW.WORK_SOURCE_XW WHERE DOI_NORMALIZED = %s",
            [doi_normalized],
        )
        return rows[0][0] if rows else None

    # -- internals -----------------------------------------------------------

    def _resolve_work(
        self,
        work_key: str,
        group: list[StagingRow],
        run_id: str,
        now: datetime,
        outcome: CanonicalOutcome,
    ) -> bool:
        existing = self._get_dim_work(work_key)
        kept: list[StagingRow] = []
        for row in group:
            quarantine_entry = self._check_conflicts(work_key, row, existing)
            if quarantine_entry is None:
                kept.append(row)
            else:
                outcome.quarantine_entries.append(quarantine_entry)
                outcome.conflicts += 1
        if not kept:
            return False

        merged = self._merge_fields(existing, kept, now)
        merged["WORK_KEY"] = work_key
        outcome.canonical_rows.append(merged)
        outcome.resolved_rows.extend(kept)

        for row in kept:
            xw = self._crosswalk_row(row, work_key, now)
            if xw is None:
                continue
            if xw is False:  # crosswalk conflict quarantined
                outcome.conflicts += 1
                continue
            outcome.crosswalk_rows.append(xw)
        return True

    def _check_conflicts(
        self, work_key: str, row: StagingRow, existing: dict[str, Any] | None
    ) -> QuarantineEntry | None:
        """Return a quarantine entry when the record conflicts with stored state."""
        if existing is not None and work_key.startswith("doi:"):
            stored_title = existing.get("TITLE_NORMALIZED")
            if stored_title and row.title_normalized:
                if _loose_key(stored_title) != _loose_key(row.title_normalized):
                    return QuarantineEntry(
                        quarantine_id=_hash(f"{row.source_name}|{row.source_record_id}|{QUARANTINE_CONFLICTING_DOI}"),
                        run_id=row.run_id,
                        batch_id=row.batch_id,
                        source_name=row.source_name,
                        source_record_id=row.source_record_id,
                        reason_code=QUARANTINE_CONFLICTING_DOI,
                        detail=f"DOI {row.doi_normalized} already resolves to a different title",
                    )
        crosswalk = self._get_crosswalk(row.source_name, row.source_record_id)
        if crosswalk is not None and crosswalk.get("WORK_KEY") != work_key:
            return QuarantineEntry(
                quarantine_id=_hash(f"{row.source_name}|{row.source_record_id}|{QUARANTINE_DOI_CHANGE}"),
                run_id=row.run_id,
                batch_id=row.batch_id,
                source_name=row.source_name,
                source_record_id=row.source_record_id,
                reason_code=QUARANTINE_DOI_CHANGE,
                detail=(
                    f"Record previously resolved to {crosswalk.get('WORK_KEY')!r}; "
                    f"new observation maps to {work_key!r}"
                ),
            )
        return None

    def _merge_fields(
        self, existing: dict[str, Any] | None, rows: list[StagingRow], now: datetime
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {column: None for column in _DIM_WORK_COLUMNS}
        if existing is not None:
            merged.update({k: v for k, v in existing.items() if k in merged})
        merged["FIRST_SEEN_AT"] = merged.get("FIRST_SEEN_AT") or now

        priority = {name: index for index, name in enumerate(self.source_priority)}

        def updated_key(row: StagingRow) -> datetime:
            return row.source_updated_at or datetime.min.replace(tzinfo=now.tzinfo)

        # Stable three-pass sort (applied in reverse precedence order):
        #   1. source priority descending  -> higher priority applied LAST so
        #      its non-null values win,
        #   2. source update time ascending -> the latest observation wins
        #      within one source,
        #   3. payload hash ascending -> a deterministic tiebreak when the
        #      same record appears twice with identical timestamps in one
        #      batch (multiple content versions never produce ambiguous
        #      updates; full history stays in staging).
        by_hash = sorted(rows, key=lambda row: row.payload_sha256 or "")
        by_updated = sorted(by_hash, key=updated_key)
        by_priority = sorted(
            by_updated, key=lambda row: priority.get(row.source_name, len(priority)), reverse=True
        )
        for row in by_priority:
            candidates = {
                "DOI_NORMALIZED": row.doi_normalized or normalize_doi(row.doi_raw),
                "TITLE": row.title,
                "TITLE_NORMALIZED": row.title_normalized,
                "PUBLICATION_DATE": row.publication_date,
                "PUBLICATION_YEAR": row.publication_year,
                "WORK_TYPE": row.work_type,
                "VENUE_NAME": row.venue_name,
                "OA_IS_OA": row.oa_is_oa,
                "OA_STATUS": row.oa_status,
                "CITED_BY_COUNT": row.cited_by_count,
            }
            for field_name, value in candidates.items():
                if value is not None:
                    merged[field_name] = value
            merged["SOURCE_PRIORITY"] = row.source_name
        merged["LAST_UPDATED_AT"] = now
        return merged

    def _crosswalk_row(self, row: StagingRow, work_key: str, now: datetime) -> dict[str, Any] | None | bool:
        """Build an upsert row; ``False`` means conflicted (skip), ``None`` unusable."""
        if not row.source_record_id:
            return None
        existing = self._get_crosswalk(row.source_name, row.source_record_id)
        if existing is not None and existing.get("WORK_KEY") != work_key:
            return False  # already quarantined in _check_conflicts
        return {
            "SOURCE_NAME": row.source_name,
            "SOURCE_RECORD_ID": row.source_record_id,
            "WORK_KEY": work_key,
            "DOI_NORMALIZED": row.doi_normalized or normalize_doi(row.doi_raw),
            "FIRST_SEEN_AT": (existing or {}).get("FIRST_SEEN_AT") or now,
            "LAST_SEEN_AT": now,
        }

    # -- warehouse reads -----------------------------------------------------

    def _get_dim_work(self, work_key: str) -> dict[str, Any] | None:
        if self._dim_cache is not None and work_key in self._dim_cache:
            return self._dim_cache[work_key]
        columns = ", ".join(_DIM_WORK_COLUMNS)
        rows = self._warehouse.execute(
            f"SELECT {columns} FROM PROJECT_DW.DIM_WORK WHERE WORK_KEY = %s", [work_key]
        )
        if not rows:
            return None
        return dict(zip(_DIM_WORK_COLUMNS, rows[0], strict=True))

    def _get_crosswalk(self, source_name: str, source_record_id: str) -> dict[str, Any] | None:
        cache_key = (source_name, source_record_id)
        if self._xw_cache is not None and cache_key in self._xw_cache:
            return self._xw_cache[cache_key]
        columns = ", ".join(_CROSSWALK_COLUMNS)
        rows = self._warehouse.execute(
            f"SELECT {columns} FROM PROJECT_DW.WORK_SOURCE_XW "
            "WHERE SOURCE_NAME = %s AND SOURCE_RECORD_ID = %s",
            [source_name, source_record_id],
        )
        if not rows:
            return None
        return dict(zip(_CROSSWALK_COLUMNS, rows[0], strict=True))


_PREFETCH_CHUNK = 500


def _chunks(items: list[str], size: int = _PREFETCH_CHUNK) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _loose_key(title: str) -> str:
    """Punctuation-insensitive comparison key for titles."""
    return _NON_ALNUM.sub("", normalize_title(title) or "")


def _hash(basis: str) -> str:
    import hashlib

    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
