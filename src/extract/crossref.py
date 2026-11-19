"""Crossref extractor: index-date windows with deep cursor paging.

Verified behaviour used here (official docs, checked 2026-11-14):
https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/

* endpoint ``https://api.crossref.org/works``
* ``cursor=*`` starts deep paging; the next cursor is ``message.next-cursor``
* ``rows`` max 1000; a final page has no ``next-cursor``
* ``from-index-date`` and ``until-index-date`` are inclusive and should be used
  together so result sets remain stable between requests
* an informative ``mailto`` is sent when a contact address is configured

Optional config keys (``config/sources.yml``):

* ``select``: list (or comma string) of fields to request. Full Crossref works
  are about 26 KB each (reference lists dominate); a trimmed field list is
  about 1 KB each. Anything not listed is absent from the raw files.
* ``max_pages``: stop after N pages. TEST ONLY: the runner refuses it unless
  ``--dry-run`` is used, because a truncated window must never be marked loaded.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from typing import Any

from extract.base import FetchWindow, Page
from extract.http import Http

log = logging.getLogger(__name__)


class CrossrefExtractor:
    name = "crossref"
    entity = "work"
    base_url = "https://api.crossref.org/works"

    def __init__(self, config: Mapping[str, Any], contact_email: str | None = None) -> None:
        self._page_size = min(int(config.get("page_size", 1000)), 1000)
        self._contact_email = contact_email
        select = config.get("select")
        if isinstance(select, (list, tuple)):
            select = ",".join(str(s).strip() for s in select if str(s).strip())
        self._select = str(select) if select else None
        max_pages = config.get("max_pages")
        self._max_pages = int(max_pages) if max_pages else None

    def iter_pages(
        self, http: Http, window: FetchWindow, cursor: str | None = None
    ) -> Iterator[Page]:
        next_cursor = cursor or "*"
        page_no = 0
        while True:
            params: dict[str, str] = {
                "filter": (
                    f"from-index-date:{window.window_start},"
                    f"until-index-date:{window.window_end}"
                ),
                "rows": str(self._page_size),
                "cursor": next_cursor,
            }
            if self._select:
                params["select"] = self._select
            request_params = dict(params)
            if self._contact_email:
                request_params["mailto"] = self._contact_email
            started = time.monotonic()
            response = http.get(self.base_url, params=request_params)
            document = response.json()
            page_no += 1
            message = document.get("message") or {}
            items = message.get("items") or []
            page_cursor = message.get("next-cursor")
            log.info(
                "crossref page %d: %d records, %d bytes, %.1fs",
                page_no,
                len(items),
                len(response.body),
                time.monotonic() - started,
            )
            yield Page(
                records=[item for item in items if isinstance(item, dict)],
                next_cursor=str(page_cursor) if page_cursor else None,
                request={"method": "GET", "url": self.base_url, "params": params},
                records_seen=len(items),
            )
            if len(items) < self._page_size or not page_cursor:
                return
            if self._max_pages and page_no >= self._max_pages:
                log.warning("crossref max_pages=%d reached; stopping early", self._max_pages)
                return
            next_cursor = str(page_cursor)
