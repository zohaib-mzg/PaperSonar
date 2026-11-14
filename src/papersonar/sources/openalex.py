"""OpenAlex adapter: cursor-paged works harvesting by deterministic partitions.

Verified against official docs on 2026-11-14 (help.openalex.org/api,
/api/paging, /api/filtering):
- base URL https://api.openalex.org; works endpoint /works
- cursor paging: ``cursor=*`` then follow ``meta.next_cursor`` until null
- ``per_page`` maximum 100 (200 is deprecated legacy)
- basic page paging hard-capped at 10,000 results (unused here)
- free API key required for cursor paging past the first page (401 otherwise)
- ``from_updated_date`` change feeds are PAID (Member+/Partner) and are NOT used;
  incremental refresh = bounded re-fetch reconciliation of partitions
- filter syntax: comma-separated AND, ``|`` for OR within one attribute

Partition scheme: stream_name ``year:YYYY`` combined with the configured base
filter (default: the candidate topics from the corpus contract).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from papersonar.errors import PermanentError
from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord
from papersonar.timeutil import parse_iso_utc

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"


class OpenAlexAdapter(BaseAdapter):
    name = "openalex"

    def __init__(self, *args: Any, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._api_key = api_key

    # -- request construction -------------------------------------------------

    def base_filter(self) -> str:
        """Configured base filter, e.g. ``topics.id:T10743|T12423|T12479``."""
        return self.settings.extra("FILTER", "topics.id:T10743|T12423|T12479")

    def _filter_for_stream(self, stream_name: str) -> str:
        year = _year_from_stream(stream_name)
        parts = [f"publication_year:{year}"]
        if self.base_filter():
            parts.append(self.base_filter())
        return ",".join(parts)

    def fetch_page(
        self, window: FetchWindow, cursor: str | None
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        params: dict[str, str] = {
            "filter": self._filter_for_stream(window.stream_name),
            "per_page": str(min(self.settings.page_size, 100)),  # verified max 100
            "cursor": cursor or "*",
        }
        if self._api_key:
            request_params = {**params, "api_key": self._api_key}
        else:
            request_params = params
        response = self.http.get(BASE_URL, params=request_params)
        descriptor = {"method": "GET", "url": BASE_URL, "params": params}
        next_cursor = _next_cursor(response.body)
        return response.body, next_cursor, descriptor

    def parse_page(self, payload: bytes) -> ParsedPage:
        document = json.loads(payload.decode("utf-8"))
        meta = document.get("meta") or {}
        results = document.get("results") or []
        next_cursor = meta.get("next_cursor")
        records = [_to_record(work) for work in results]
        complete = next_cursor is None or not results
        return ParsedPage(
            records=records,
            next_cursor=next_cursor,
            pages_complete=complete,
            records_seen=len(results),
        )


def _year_from_stream(stream_name: str) -> str:
    if stream_name.startswith("year:"):
        year = stream_name[len("year:") :]
        if year.isdigit():
            return year
    raise PermanentError(
        f"openalex: unknown stream partition {stream_name!r}; expected 'year:YYYY'"
    )


def _next_cursor(body: bytes) -> str | None:
    document = json.loads(body.decode("utf-8"))
    meta = document.get("meta") or {}
    cursor = meta.get("next_cursor")
    return str(cursor) if cursor else None


def _to_record(work: dict[str, Any]) -> SourceRecord:
    open_access = work.get("open_access") or {}
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    topics: list[dict[str, Any]] = []
    primary_topic = work.get("primary_topic") or {}
    primary_topic_id = primary_topic.get("id")
    for topic in work.get("topics") or []:
        topics.append(
            {
                "id": _short_id(topic.get("id")),
                "name": topic.get("display_name"),
                "score": topic.get("score"),
                "primary": topic.get("id") == primary_topic_id,
            }
        )
    authorships = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        authorships.append(
            {
                "position": authorship.get("author_position"),
                "author_id": _short_id(author.get("id")),
                "author_name": author.get("display_name"),
                "orcid": author.get("orcid"),
                "institutions": [
                    {"id": _short_id(inst.get("id")), "name": inst.get("display_name")}
                    for inst in authorship.get("institutions") or []
                ],
            }
        )
    doi = work.get("doi")
    return SourceRecord(
        source_name="openalex",
        source_record_id=_short_id(work.get("id")) or "",
        source_updated_at=parse_iso_utc(work.get("updated_date")),
        doi_raw=doi,
        title=work.get("display_name") or work.get("title"),
        publication_date=work.get("publication_date"),
        publication_year=work.get("publication_year"),
        work_type=work.get("type"),
        venue_name=source.get("display_name"),
        oa_is_oa=open_access.get("is_oa"),
        oa_status=open_access.get("oa_status"),
        cited_by_count=work.get("cited_by_count"),
        referenced_ids=tuple(work.get("referenced_works") or ()),
        topics=tuple(topics),
        authorships=tuple(authorships),
        extra={
            "language": work.get("language"),
            "is_retracted": work.get("is_retracted"),
        },
        payload=work,
    )


def _short_id(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]
