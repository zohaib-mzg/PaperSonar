"""OpenAlex extractor: full ``/works`` windows via cursor paging.

Verified behaviour used here (official docs, checked 2026-11-14):
https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/paging

* ``cursor=*`` starts paging; follow ``meta.next_cursor`` until it is null.
* ``per_page`` max 100.
* Basic page paging is capped at 10,000 results; cursor paging is not.
* ``from_publication_date`` / ``to_publication_date`` are free filters and are
  used for a full backfill, which is a one-time publication-date window.
* ``from_updated_date`` / ``to_updated_date`` are the change-feed filters used
  for incremental runs. OpenAlex restricts them to Member+/Partner (daily sync);
  a free key receives HTTP 403 "Plan upgrade required". The error is surfaced
  rather than silently falling back to a publication-date scan.
* An API key is required for cursor paging past the first page on the free tier.

There is deliberately **no page cap** here: a window is extracted to exhaustion
so every work matching the configured filter is returned. The runner owns
resumability: it persists ``next_cursor`` after each durable shard and restarts
this generator from that cursor after a failure. Any page cap would silently
truncate a resumable window, so the setting is not supported for OpenAlex.

Config keys:

* ``select``: optional list of top-level fields to return (smaller pages).
* ``filter``: optional base filter, e.g. ``has_doi:true``. Date filters for the
  window are always added.

The extractor emits the work objects exactly as returned. Field interpretation
happens in ``sql/03_silver``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from extract.base import FetchWindow, Page
from extract.http import Http


class OpenAlexExtractor:
    name = "openalex"
    entity = "work"
    base_url = "https://api.openalex.org/works"

    def __init__(self, config: Mapping[str, Any], api_key: str | None = None) -> None:
        self._page_size = min(int(config.get("page_size", 100)), 100)
        self._base_filter = str(config.get("filter", "") or "").strip()
        select = config.get("select")
        if isinstance(select, (list, tuple)):
            self._select = ",".join(str(s).strip() for s in select if str(s).strip())
        else:
            self._select = str(select or "").strip()
        if config.get("max_pages"):
            # A page cap truncates a window while the runner still clears the
            # cursor, which would lose the rest of the window. Fail loudly.
            raise ValueError(
                "openalex does not support max_pages: a window must be extracted "
                "to exhaustion (remove max_pages from config/sources.yml)"
            )
        self._api_key = api_key

    def iter_pages(
        self, http: Http, window: FetchWindow, cursor: str | None = None
    ) -> Iterator[Page]:
        if window.mode == "incremental":
            # Change feed: only works created or updated in the saved window.
            # Bronze upserts by work id, so the overlap re-fetches are harmless.
            filter_parts = [
                f"from_updated_date:{window.window_start}",
                f"to_updated_date:{window.window_end}",
            ]
        else:
            # One-time full backfill: every work published in the window.
            filter_parts = [
                f"from_publication_date:{window.window_start}",
                f"to_publication_date:{window.window_end}",
            ]
        if self._base_filter:
            filter_parts.append(self._base_filter)

        next_cursor = cursor or "*"
        while True:
            params: dict[str, str] = {
                "filter": ",".join(filter_parts),
                "per_page": str(self._page_size),
                "cursor": next_cursor,
            }
            if self._select:
                params["select"] = self._select
            request_params = dict(params)
            if self._api_key:
                request_params["api_key"] = self._api_key
            response = http.get(self.base_url, params=request_params)
            document = response.json()
            results = document.get("results") or []
            meta = document.get("meta") or {}
            page_cursor = meta.get("next_cursor")
            yield Page(
                records=[record for record in results if isinstance(record, dict)],
                next_cursor=str(page_cursor) if page_cursor else None,
                request={"method": "GET", "url": self.base_url, "params": params},
                records_seen=len(results),
            )
            if not results or not page_cursor:
                return
            next_cursor = str(page_cursor)
