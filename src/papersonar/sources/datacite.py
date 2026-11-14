"""DataCite adapter: REST cursor paging with updated-date sorting.

Verified against official docs on 2026-11-14 (support.datacite.org/docs/
api-queries, updated 2026-08-07):
- endpoint https://api.datacite.org/dois (public, unauthenticated)
- pagination via ``page[cursor]`` (plus page[number]/page[size])
- sorting via ``sort=-updated`` (most recently updated first)
- filters: client-id, resource-type-id, prefix, etc.; advanced field queries
  via the ``query`` parameter (e.g. updated ranges) - exact updated-range
  syntax must be validated against the live API before production sync
- incremental strategy v1: bounded reconciliation with ``sort=-updated`` +
  cursor paging, stopping at the configured window bounds; relationships and
  resource types are preserved

Stream scheme: ``updated:YYYY-MM-DD`` (records updated on that UTC date).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from papersonar.errors import PermanentError
from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord

logger = logging.getLogger(__name__)

BASE_URL = "https://api.datacite.org/dois"

# DataCite relation vocabulary (DataCite metadata schema relatedIdentifierType
# / relationType). Only mapping keys we use are normalized.
_RELATION_PREFIX = "datacite-relation:"


class DataciteAdapter(BaseAdapter):
    name = "datacite"

    def fetch_page(
        self, window: FetchWindow, cursor: str | None
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        query = self._query_for_stream(window)
        params: dict[str, str] = {
            "page[size]": str(min(self.settings.page_size, 1000)),
            "sort": "-updated",
        }
        if query:
            params["query"] = query
        if cursor:
            params["page[cursor]"] = cursor
        else:
            params["page[cursor]"] = "1"
        response = self.http.get(BASE_URL, params=params)
        descriptor = {"method": "GET", "url": BASE_URL, "params": params}
        next_cursor = _next_cursor(response.body)
        return response.body, next_cursor, descriptor

    def parse_page(self, payload: bytes) -> ParsedPage:
        document = json.loads(payload.decode("utf-8"))
        data = document.get("data") or []
        records = [_to_record(doi_record) for doi_record in data]
        next_cursor = _next_cursor(payload)
        return ParsedPage(
            records=records,
            next_cursor=next_cursor,
            pages_complete=next_cursor is None,
            records_seen=len(data),
        )

    def _query_for_stream(self, window: FetchWindow) -> str:
        if not window.stream_name.startswith("updated:"):
            raise PermanentError(
                f"datacite: unknown stream partition {window.stream_name!r}; "
                "expected 'updated:YYYY-MM-DD'"
            )
        base_query = self.settings.extra("QUERY", "")
        # Validated REST filters + updated sort; the date constraint is applied
        # client-side in staging (updated<=window bounds) until the live
        # updated-range query syntax is verified.
        return base_query


def _next_cursor(payload: bytes) -> str | None:
    document = json.loads(payload.decode("utf-8"))
    links = document.get("links") or {}
    next_link = links.get("next")
    if not next_link:
        return None
    return _cursor_from_url(next_link)


def _cursor_from_url(url: str) -> str | None:
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    cursor_values = query.get("page[cursor]")
    if cursor_values:
        return cursor_values[0]
    return None


def _to_record(doi_record: dict[str, Any]) -> SourceRecord:
    attributes = doi_record.get("attributes") or {}
    related = tuple(
        {
            "identifier": rel.get("relatedIdentifier"),
            "relation": f"{_RELATION_PREFIX}{rel.get('relationType')}",
            "kind": rel.get("relatedIdentifierType"),
        }
        for rel in attributes.get("relatedIdentifiers") or []
        if isinstance(rel, dict) and rel.get("relatedIdentifier")
    )
    creators = tuple(
        {
            "author_id": creator.get("nameIdentifiers", [{}])[0].get("nameIdentifier")
            if creator.get("nameIdentifiers")
            else None,
            "author_name": creator.get("name"),
            "orcid": None,
            "institutions": [
                {"id": aff.get("affiliationIdentifier"), "name": aff.get("name")}
                for aff in creator.get("affiliation") or []
                if isinstance(aff, dict)
            ],
        }
        for creator in attributes.get("creators") or []
        if isinstance(creator, dict)
    )
    doi_raw = attributes.get("doi")
    dates = attributes.get("dates") or []
    publication_date = None
    for date_entry in dates:
        if isinstance(date_entry, dict) and date_entry.get("dateType") == "Issued":
            publication_date = date_entry.get("date")
            break
    publication_year = attributes.get("publicationYear")
    year_fallback = f"{publication_year}" if publication_year else None
    return SourceRecord(
        source_name="datacite",
        source_record_id=doi_raw or str(doi_record.get("id")),
        source_updated_at=_parse_updated(attributes.get("updated")),
        doi_raw=doi_raw,
        title=_first_title(attributes.get("titles")),
        publication_date=publication_date or year_fallback,
        publication_year=attributes.get("publicationYear"),
        work_type=attributes.get("resourceTypeGeneral") or attributes.get("resourceType"),
        venue_name=(attributes.get("publisher") or {}).get("name")
        if isinstance(attributes.get("publisher"), dict)
        else attributes.get("publisher"),
        oa_is_oa=None,
        oa_status=None,
        cited_by_count=None,
        referenced_dois=tuple(
            rel["identifier"]
            for rel in related
            if _RELATION_PREFIX in ("",) or rel["identifier"].lower().startswith("doi:")
        ),
        related_identifiers=related,
        authorships=creators,
        extra={
            "url": attributes.get("url"),
            "state": attributes.get("state"),
            "schemaVersion": attributes.get("schemaVersion"),
        },
        payload=doi_record,
    )


def _first_title(titles: list[dict[str, Any]] | None) -> str | None:
    if not titles:
        return None
    for entry in titles:
        if isinstance(entry, dict) and entry.get("title"):
            return entry["title"]
    return None


def _parse_updated(value: str | None):
    from papersonar.timeutil import parse_iso_utc

    return parse_iso_utc(value)
