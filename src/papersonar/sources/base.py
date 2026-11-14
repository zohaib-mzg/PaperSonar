"""Source adapter framework.

Every adapter implements the same pipeline-facing interface (fetch bounded
pages, persist raw, parse into the common SourceRecord shape, report next-page
state) while keeping its own pagination and API rules. Source-specific code
stays in its own module.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from papersonar.config import SourceSettings
from papersonar.errors import PermanentError
from papersonar.http_client import HttpClient
from papersonar.raw_store import RawBatchResult, RawStore


@dataclass(frozen=True)
class SourceRecord:
    """Common internal record shape produced by every adapter parser."""

    source_name: str
    source_record_id: str
    source_updated_at: datetime | None = None
    doi_raw: str | None = None
    title: str | None = None
    publication_date: str | None = None
    publication_year: int | None = None
    work_type: str | None = None
    venue_name: str | None = None
    oa_is_oa: bool | None = None
    oa_status: str | None = None
    cited_by_count: int | None = None
    referenced_dois: tuple[str, ...] = ()
    referenced_ids: tuple[str, ...] = ()  # provider-native IDs of cited works
    topics: tuple[dict[str, Any], ...] = ()
    authorships: tuple[dict[str, Any], ...] = ()
    related_identifiers: tuple[dict[str, Any], ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)  # parsed per-record payload


@dataclass(frozen=True)
class ParsedPage:
    """Parsed raw page: records plus pagination continuation state."""

    records: list[SourceRecord]
    next_cursor: str | None
    pages_complete: bool
    records_seen: int


@dataclass(frozen=True)
class FetchWindow:
    """A bounded extraction window or partition."""

    stream_name: str
    window_start: str | None
    window_end: str | None
    sync_mode: str  # backfill | sync | reconciliation
    resume_cursor: str | None = None


class PageFetcher(Protocol):
    """Adapter page contract."""

    def fetch_page(self, window: FetchWindow, cursor: str | None) -> tuple[bytes, str | None, dict[str, Any]]:
        """Return (raw_bytes, next_cursor, request_descriptor). Raises on HTTP failure."""
        ...

    def parse_page(self, payload: bytes) -> ParsedPage:
        """Parse raw bytes into the common record shape."""
        ...


class BaseAdapter:
    """Shared fetch/persist loop. Subclasses provide fetch_page and parse_page."""

    name: str = "base"

    def __init__(
        self,
        settings: SourceSettings,
        http_client: HttpClient,
        raw_store: RawStore,
    ) -> None:
        self.settings = settings
        self.http = http_client
        self.raw_store = raw_store

    def stream_pages(
        self,
        run_id: str,
        window: FetchWindow,
    ) -> Iterator[RawBatchResult]:
        """Fetch + persist every page in the window until complete or bounded.

        Each page is durable (local mirror + warehouse stage + registry row)
        before the next request. The completed watermark is advanced by the
        orchestrator only after the whole window validates.
        """
        cursor = window.resume_cursor
        page_seq = 0
        while page_seq < self.settings.max_pages:
            page_seq += 1
            payload, next_cursor, descriptor = self.fetch_page(window, cursor)
            result = self.raw_store.persist_batch(
                run_id=run_id,
                source_name=self.name,
                stream_name=window.stream_name,
                window_start=window.window_start,
                window_end=window.window_end,
                page_seq=page_seq,
                page_cursor=cursor,
                retrieved_at_utc=_utc_now(),
                http_status=None,
                payload_bytes=payload,
                records_seen=self.count_records(payload),
                request_descriptor=descriptor,
            )
            yield result
            if next_cursor is None or self.is_complete(payload):
                return
            cursor = next_cursor
        raise PermanentError(
            f"{self.name}: max_pages={self.settings.max_pages} reached without completing "
            f"window {window.stream_name}; rerun to resume safely (idempotent upserts)"
        )

    # -- helpers -------------------------------------------------------------

    def fetch_page(self, window: FetchWindow, cursor: str | None) -> tuple[bytes, str | None, dict[str, Any]]:
        raise NotImplementedError

    def parse_page(self, payload: bytes) -> ParsedPage:
        raise NotImplementedError

    def count_records(self, payload: bytes) -> int:
        return self.parse_page(payload).records_seen

    def is_complete(self, payload: bytes) -> bool:
        return self.parse_page(payload).pages_complete


def _utc_now() -> datetime:
    from papersonar.timeutil import utc_now

    return utc_now()
