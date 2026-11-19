"""DataCite extractor: raw DOI records via REST cursor paging.

Verified behaviour used here (official docs, checked 2026-11-14):
https://support.datacite.org/docs/api-queries

* endpoint ``https://api.datacite.org/dois``
* ``page[size]`` max 1000, ``page[cursor]`` starts at 1
* response ``links.next`` is followed until absent
* ``sort=-updated`` is used so incremental runs see recent changes first
* the updated-range query syntax is marked VERIFY in documentation before a
  production incremental run; the configured ``query`` is passed through as-is
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

from extract.base import FetchWindow, Page
from extract.http import Http


class DataCiteExtractor:
    name = "datacite"
    entity = "doi"
    base_url = "https://api.datacite.org/dois"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._page_size = min(int(config.get("page_size", 1000)), 1000)
        self._query_template = str(config.get("query", "") or "")

    def iter_pages(
        self, http: Http, window: FetchWindow, cursor: str | None = None
    ) -> Iterator[Page]:
        query = self._query_template.format(
            window_start=window.window_start, window_end=window.window_end
        ).strip()
        next_url: str | None = None
        page_cursor = cursor or "1"
        while True:
            if next_url:
                response = http.get(next_url)
                descriptor = {"method": "GET", "url": next_url, "params": {}}
            else:
                params: dict[str, str] = {
                    "page[size]": str(self._page_size),
                    "page[cursor]": page_cursor,
                    "sort": "-updated",
                }
                if query:
                    params["query"] = query
                response = http.get(self.base_url, params=params)
                descriptor = {"method": "GET", "url": self.base_url, "params": params}

            document = response.json()
            data = document.get("data") or []
            yield Page(
                records=[record for record in data if isinstance(record, dict)],
                next_cursor=next_url,
                request=descriptor,
                records_seen=len(data),
            )
            next_url = (document.get("links") or {}).get("next")
            if not next_url:
                return
            next_url = str(next_url)
            page_cursor = _cursor_from_url(next_url) or page_cursor


def _cursor_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("page[cursor]")
    return values[0] if values else None
