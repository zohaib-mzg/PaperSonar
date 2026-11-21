"""Zenodo extractor: OAI-PMH harvesting with raw DataCite XML preserved.

Verified behaviour used here (official docs, checked 2026-11-14):
https://developers.zenodo.org/#oai-pmh

* OAI-PMH endpoint ``https://zenodo.org/oai2d``
* ``oai_datacite`` returns DataCite kernel metadata as XML
* datestamp windows are supported; resumption tokens are short-lived and an
  expired token restarts the bounded window (idempotent bronze replay)
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from extract import oai
from extract.base import FetchWindow, Page
from extract.http import Http


class ZenodoExtractor:
    name = "zenodo"
    entity = "record"
    base_url = "https://zenodo.org/oai2d"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._metadata_prefix = str(config.get("metadata_prefix", "oai_datacite"))
        self._set_spec = config.get("set_spec")

    def iter_pages(
        self, http: Http, window: FetchWindow, cursor: str | None = None
    ) -> Iterator[Page]:
        next_token = cursor
        while True:
            records, next_token, descriptor = oai.list_records(
                http,
                self.base_url,
                metadata_prefix=self._metadata_prefix,
                from_date=window.resume_from or window.window_start,
                until_date=window.window_end,
                resumption_token=next_token,
                set_spec=str(self._set_spec) if self._set_spec else None,
            )
            yield Page(
                records=[
                    oai.to_payload(record, self._metadata_prefix) for record in records
                ],
                next_cursor=next_token,
                request=descriptor,
                records_seen=len(records),
            )
            if not next_token:
                return
