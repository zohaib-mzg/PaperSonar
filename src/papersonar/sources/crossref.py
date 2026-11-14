"""Crossref adapter: index-date windows with deep cursor paging.

Verified against official docs on 2026-11-14
(crossref.org/documentation/.../tips-for-using-the-crossref-rest-api/):
- endpoint https://api.crossref.org/works
- ``cursor=*`` starts deep paging; response ``message.next-cursor``; last page
  reached when returned items < requested ``rows`` (no cursor returned then)
- ``rows`` default 20, max 1000
- ``from-index-date`` and ``until-index-date`` are inclusive; using BOTH is
  officially recommended so result sets stay stable between requests
- HTTP 429 means rate limited: back off (Retry-After honored)
- ``select`` narrows returned fields

Window scheme: stream ``indexdate:YYYY-MM-DD`` = one-day index-date partition.
Sync windows can span several days; window_start/window_end are ISO dates.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from papersonar.errors import PermanentError
from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord
from papersonar.timeutil import parse_iso_utc

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org/works"


class CrossrefAdapter(BaseAdapter):
    name = "crossref"

    def __init__(self, *args: Any, contact_email: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._contact_email = contact_email

    def fetch_page(
        self, window: FetchWindow, cursor: str | None
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        filters = [f"from-index-date:{window.window_start}", f"until-index-date:{window.window_end}"]
        params: dict[str, str] = {
            "filter": ",".join(filters),
            "rows": str(min(self.settings.page_size, 1000)),  # verified max 1000
            "cursor": cursor or "*",
        }
        if self._contact_email:
            request_params = {**params, "mailto": self._contact_email}
        else:
            request_params = params
        response = self.http.get(BASE_URL, params=request_params)
        descriptor = {"method": "GET", "url": BASE_URL, "params": params}
        return response.body, _next_cursor(response.body), descriptor

    def parse_page(self, payload: bytes) -> ParsedPage:
        document = json.loads(payload.decode("utf-8"))
        message = document.get("message") or {}
        items = message.get("items") or []
        requested_rows = self.settings.page_size
        next_cursor = message.get("next-cursor")
        records = [_to_record(item) for item in items]
        complete = next_cursor is None or len(items) < requested_rows
        return ParsedPage(
            records=records,
            next_cursor=next_cursor,
            pages_complete=complete,
            records_seen=len(items),
        )


def _next_cursor(body: bytes) -> str | None:
    document = json.loads(body.decode("utf-8"))
    message = document.get("message") or {}
    cursor = message.get("next-cursor")
    return str(cursor) if cursor else None


def _to_record(item: dict[str, Any]) -> SourceRecord:
    titles = item.get("title") or []
    container = item.get("container-title") or []
    issued = item.get("issued") or {}
    date_parts = (issued.get("date-parts") or [[None]])[0]
    publication_date = None
    publication_year = None
    if date_parts and date_parts[0]:
        publication_year = int(date_parts[0])
        parts = [f"{date_parts[0]:04d}"]
        if len(date_parts) > 1 and date_parts[1]:
            parts.append(f"{date_parts[1]:02d}")
            if len(date_parts) > 2 and date_parts[2]:
                parts.append(f"{date_parts[2]:02d}")
        publication_date = "-".join(parts)
    referenced_dois = tuple(
        ref["DOI"] for ref in item.get("reference") or [] if isinstance(ref, dict) and ref.get("DOI")
    )
    authorships = tuple(
        {
            "author_id": author.get("ORCID"),
            "author_name": " ".join(
                part for part in (author.get("given"), author.get("family")) if part
            ),
            "orcid": author.get("ORCID"),
            "institutions": [],
        }
        for author in item.get("author") or []
        if isinstance(author, dict)
    )
    doi_raw = item.get("DOI")
    source_record_id = doi_raw or item.get("id") or ""
    return SourceRecord(
        source_name="crossref",
        source_record_id=source_record_id,
        source_updated_at=parse_iso_utc(item.get("indexed", {}).get("date-time")),
        doi_raw=doi_raw,
        title=titles[0] if titles else None,
        publication_date=publication_date,
        publication_year=publication_year,
        work_type=item.get("type"),
        venue_name=container[0] if container else None,
        cited_by_count=item.get("is-referenced-by-count"),
        referenced_dois=referenced_dois,
        authorships=authorships,
        extra={
            "publisher": item.get("publisher"),
            "references_count": item.get("references-count"),
            "url": item.get("URL"),
        },
        payload=item,
    )


def validate_stream(window: FetchWindow) -> None:
    if not window.stream_name.startswith("indexdate:"):
        raise PermanentError(
            f"crossref: unknown stream partition {window.stream_name!r}; "
            "expected 'indexdate:YYYY-MM-DD'"
        )
