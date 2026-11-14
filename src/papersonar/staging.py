"""Staging: validation, quarantine and staging-row construction.

Validation is non-destructive: invalid rows are quarantined with a stable
reason code (never silently discarded) and valid rows proceed to canonical
resolution. Missing optional fields are recorded as missingness, not failures.
Dates and identifiers are normalized for comparison only; original values are
preserved.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from papersonar.identifiers import canonical_json_hash, normalize_doi, normalize_title
from papersonar.sources.base import SourceRecord
from papersonar.timeutil import utc_now

logger = logging.getLogger(__name__)

# Stable quarantine reason codes (queryable, documented).
QUARANTINE_MISSING_SOURCE_ID = "missing_source_id"
QUARANTINE_MALFORMED_IDENTIFIER = "malformed_identifier"
QUARANTINE_INVALID_DATE = "invalid_date"
QUARANTINE_NEGATIVE_COUNT = "impossible_negative_count"
QUARANTINE_CONFLICTING_DOI = "conflicting_doi_identity"
QUARANTINE_STRUCTURAL = "structurally_invalid_payload"

_DATE_SYNTAX = ("%Y-%m-%d", "%Y-%m", "%Y")


@dataclass(frozen=True)
class StagingRow:
    """One row for PROJECT_STAGING.STG_WORK_RECORD."""

    staging_id: str
    run_id: str
    batch_id: str
    source_name: str
    source_record_id: str
    source_updated_at: datetime | None
    doi_raw: str | None
    doi_normalized: str | None
    title: str | None
    title_normalized: str | None
    publication_date: str | None
    publication_year: int | None
    work_type: str | None
    venue_name: str | None
    oa_is_oa: bool | None
    oa_status: str | None
    cited_by_count: int | None
    referenced_works: list[Any]
    topics: list[Any]
    authorships: list[Any]
    related_identifiers: list[Any]
    payload_sha256: str
    parser_version: str
    schema_version: str
    validation_status: str
    validation_reason: str | None
    ingested_at: datetime

    def row(self, columns: tuple[str, ...]) -> list[Any]:
        values = {
            "STAGING_ID": self.staging_id,
            "RUN_ID": self.run_id,
            "BATCH_ID": self.batch_id,
            "SOURCE_NAME": self.source_name,
            "SOURCE_RECORD_ID": self.source_record_id,
            "SOURCE_UPDATED_AT": self.source_updated_at,
            "DOI_RAW": self.doi_raw,
            "DOI_NORMALIZED": self.doi_normalized,
            "TITLE": self.title,
            "TITLE_NORMALIZED": self.title_normalized,
            "PUBLICATION_DATE": self.publication_date,
            "PUBLICATION_YEAR": self.publication_year,
            "WORK_TYPE": self.work_type,
            "VENUE_NAME": self.venue_name,
            "OA_IS_OA": self.oa_is_oa,
            "OA_STATUS": self.oa_status,
            "CITED_BY_COUNT": self.cited_by_count,
            "REFERENCED_WORKS": self.referenced_works,
            "TOPICS": self.topics,
            "AUTHORSHIPS": self.authorships,
            "RELATED_IDENTIFIERS": self.related_identifiers,
            "PAYLOAD_SHA256": self.payload_sha256,
            "PARSER_VERSION": self.parser_version,
            "SCHEMA_VERSION": self.schema_version,
            "VALIDATION_STATUS": self.validation_status,
            "VALIDATION_REASON": self.validation_reason,
            "INGESTED_AT": self.ingested_at,
        }
        return [values[column] for column in columns]


@dataclass(frozen=True)
class QuarantineEntry:
    quarantine_id: str
    run_id: str
    batch_id: str | None
    source_name: str
    source_record_id: str | None
    reason_code: str
    detail: str | None


@dataclass(frozen=True)
class StagingOutcome:
    accepted: list[StagingRow]
    quarantined: list[QuarantineEntry]
    records_seen: int


class StagingValidator:
    """Validates parsed source records into staging rows or quarantine entries."""

    def __init__(self, parser_version: str = "1", schema_version: str = "1") -> None:
        self.parser_version = parser_version
        self.schema_version = schema_version

    def validate_batch(
        self,
        records: list[SourceRecord],
        *,
        run_id: str,
        batch_id: str,
    ) -> StagingOutcome:
        accepted: list[StagingRow] = []
        quarantined: list[QuarantineEntry] = []
        for record in records:
            reason = _first_failure(record)
            now = utc_now()
            if reason is not None:
                quarantined.append(
                    QuarantineEntry(
                        quarantine_id=_quarantine_id(record, reason),
                        run_id=run_id,
                        batch_id=batch_id,
                        source_name=record.source_name,
                        source_record_id=record.source_record_id or None,
                        reason_code=reason,
                        detail=None,
                    )
                )
                continue
            doi_normalized = normalize_doi(record.doi_raw)
            accepted.append(
                StagingRow(
                    staging_id=uuid.uuid4().hex,
                    run_id=run_id,
                    batch_id=batch_id,
                    source_name=record.source_name,
                    source_record_id=record.source_record_id,
                    source_updated_at=record.source_updated_at,
                    doi_raw=record.doi_raw,
                    doi_normalized=doi_normalized,
                    title=record.title,
                    title_normalized=normalize_title(record.title),
                    publication_date=_clean_date(record.publication_date),
                    publication_year=record.publication_year or _year_from_date(record.publication_date),
                    work_type=record.work_type,
                    venue_name=record.venue_name,
                    oa_is_oa=record.oa_is_oa,
                    oa_status=record.oa_status,
                    cited_by_count=record.cited_by_count,
                    referenced_works=(
                        [{"kind": "doi", "value": value} for value in record.referenced_dois]
                        + [{"kind": "provider_id", "value": value} for value in record.referenced_ids]
                    ),
                    topics=[dict(t) for t in record.topics],
                    authorships=[dict(a) for a in record.authorships],
                    related_identifiers=[dict(r) for r in record.related_identifiers],
                    payload_sha256=canonical_json_hash(record.payload),
                    parser_version=self.parser_version,
                    schema_version=self.schema_version,
                    validation_status="accepted",
                    validation_reason=None,
                    ingested_at=now,
                )
            )
        return StagingOutcome(
            accepted=accepted,
            quarantined=quarantined,
            records_seen=len(records),
        )


def _first_failure(record: SourceRecord) -> str | None:
    """Return the first fatal validation reason, or None when accepted."""
    if not record.source_record_id or not record.source_record_id.strip():
        return QUARANTINE_MISSING_SOURCE_ID
    if record.doi_raw is not None and normalize_doi(record.doi_raw) is None:
        return QUARANTINE_MALFORMED_IDENTIFIER
    if record.publication_date is not None and _clean_date(record.publication_date) is None:
        return QUARANTINE_INVALID_DATE
    if record.cited_by_count is not None and record.cited_by_count < 0:
        return QUARANTINE_NEGATIVE_COUNT
    return None


def _clean_date(value: str | None) -> str | None:
    """Accept YYYY, YYYY-MM or YYYY-MM-DD; reject unparseable date strings."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    from datetime import datetime as _dt

    for fmt in _DATE_SYNTAX:
        try:
            parsed = _dt.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.date().isoformat()[: len(text)]
    return None


def _year_from_date(value: str | None) -> int | None:
    cleaned = _clean_date(value)
    if cleaned is None:
        return None
    return int(cleaned[:4])


def _quarantine_id(record: SourceRecord, reason: str) -> str:
    """Deterministic id so re-quarantining updates the same row."""
    import hashlib

    basis = f"{record.source_name}|{record.source_record_id}|{reason}".encode()
    return hashlib.sha256(basis).hexdigest()[:32]
