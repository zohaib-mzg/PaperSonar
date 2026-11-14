"""arXiv adapter: OAI-PMH datestamp harvesting with version awareness.

Verified against official docs on 2026-11-14 (info.arxiv.org/help/oa):
- OAI-PMH 2.0 base URL https://oaipmh.arxiv.org/oai (since 2025-03 rewrite)
- metadata formats: oai_dc, arXiv, arXivRaw (version history in arXivRaw)
- incremental harvesting: ``from`` = last harvest datestamp; ``until`` should
  NOT be set for ongoing sync (official guidance)
- resumption tokens expire DAILY: on badResumptionToken the window restarts
  from the beginning (idempotent upserts make re-fetch safe)
- sets follow group:archive:category, e.g. cs:cs:SE
- only the latest version is exposed per item in the arXiv format; arXivRaw
  carries full version history (configurable prefix)

Stream scheme: ``oai:arxiv`` (whole repository, incremental datestamp window)
or ``set:<setSpec>`` for selective harvesting.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord
from papersonar.sources.oai_pmh import OAI_NS, OaiPmhClient, parse_records
from papersonar.timeutil import parse_iso_utc

logger = logging.getLogger(__name__)

ARXIV_NS = "http://arxiv.org/OAI/arXiv/"
DC_NS = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
BASE_URL = "https://oaipmh.arxiv.org/oai"


class ArxivAdapter(BaseAdapter):
    name = "arxiv"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._oai = OaiPmhClient(self.http, BASE_URL)

    def _metadata_prefix(self) -> str:
        return self.settings.extra("METADATA_PREFIX", "arXiv")

    def _set_spec(self, window: FetchWindow) -> str | None:
        if window.stream_name.startswith("set:"):
            return window.stream_name[len("set:") :]
        if window.stream_name == "oai:arxiv":
            return None
        return None

    def fetch_page(
        self, window: FetchWindow, cursor: str | None
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        body, next_token, descriptor = self._oai.list_records(
            metadata_prefix=self._metadata_prefix(),
            from_date=window.window_start,
            until_date=None,  # official guidance: do not set `until` for incremental sync
            resumption_token=cursor,
            set_spec=self._set_spec(window),
        )
        return body, next_token, descriptor

    def parse_page(self, payload: bytes) -> ParsedPage:
        oai_records = parse_records(payload)
        records: list[SourceRecord] = []
        deleted = 0
        for oai_record in oai_records:
            if oai_record.deleted or oai_record.metadata is None:
                deleted += 1
                continue
            record = _to_record(oai_record, self._metadata_prefix())
            if record is not None:
                records.append(record)
        next_token = _resumption_token(payload)
        return ParsedPage(
            records=records,
            next_cursor=next_token,
            pages_complete=next_token is None,
            records_seen=len(oai_records),
        )


def _resumption_token(payload: bytes) -> str | None:
    root = ET.fromstring(payload)
    token = root.find(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}resumptionToken")
    if token is None:
        return None
    return (token.text or "").strip() or None


def _to_record(oai_record: Any, metadata_prefix: str) -> SourceRecord | None:
    if metadata_prefix == "arXiv":
        return _record_from_arxiv(oai_record)
    if metadata_prefix == "oai_dc":
        return _record_from_oai_dc(oai_record)
    return _record_from_arxiv(oai_record)  # arXivRaw shares the arXiv element set


def _record_from_arxiv(oai_record: Any) -> SourceRecord | None:
    metadata_root = oai_record.metadata[0] if len(oai_record.metadata) else None
    if metadata_root is None:
        return None
    arxiv_id = (metadata_root.findtext(f"{{{ARXIV_NS}}}id") or "").strip()
    if not arxiv_id:
        return None
    categories = (metadata_root.findtext(f"{{{ARXIV_NS}}}categories") or "").split()
    doi = (metadata_root.findtext(f"{{{ARXIV_NS}}}doi") or "").strip() or None
    journal_ref = (metadata_root.findtext(f"{{{ARXIV_NS}}}journal-ref") or "").strip() or None
    created = (metadata_root.findtext(f"{{{ARXIV_NS}}}created") or "").strip() or None
    updated = (metadata_root.findtext(f"{{{ARXIV_NS}}}updated") or "").strip() or None
    authors = [
        (author.text or "").strip()
        for author in metadata_root.findall(f"{{{ARXIV_NS}}}authors/{{{ARXIV_NS}}}author")
        if author.text
    ]
    if not authors:
        authors = [
            (element.text or "").strip()
            for element in metadata_root.findall(f"{{{ARXIV_NS}}}author")
            if element.text
        ]
    abstract = (metadata_root.findtext(f"{{{ARXIV_NS}}}abstract") or "").strip() or None
    return SourceRecord(
        source_name="arxiv",
        source_record_id=arxiv_id,
        source_updated_at=parse_iso_utc(oai_record.datestamp),
        doi_raw=doi,
        title=(metadata_root.findtext(f"{{{ARXIV_NS}}}title") or "").strip() or None,
        publication_date=created,
        work_type="preprint",
        venue_name="arXiv",
        cited_by_count=None,
        related_identifiers=(
            (
                {
                    "identifier": journal_ref,
                    "relation": "is-article-in-journal",
                    "kind": "journal_ref",
                },
            )
            if journal_ref
            else ()
        ),
        authorships=tuple(
            {"author_id": None, "author_name": name, "orcid": None, "institutions": []}
            for name in authors
        ),
        extra={
            "categories": categories,
            "abstract": abstract,
            "oai_identifier": oai_record.identifier,
            "oai_datestamp": oai_record.datestamp,
            "updated": updated,
        },
        payload=_element_to_dict(metadata_root),
    )


def _record_from_oai_dc(oai_record: Any) -> SourceRecord | None:
    dc_root = None
    for child in oai_record.metadata:
        dc_root = child
        break
    if dc_root is None:
        return None
    identifier_text = ""
    for element in dc_root.findall(f"{{{DC_NS}}}identifier"):
        value = (element.text or "").strip()
        if value.startswith("http://arxiv.org/abs/"):
            identifier_text = value.rsplit("/", 1)[-1]
            break
    if not identifier_text:
        identifier_text = oai_record.identifier
    arxiv_id = identifier_text
    dates = [(element.text or "").strip() for element in dc_root.findall(f"{{{DC_NS}}}date")]
    return SourceRecord(
        source_name="arxiv",
        source_record_id=arxiv_id,
        source_updated_at=parse_iso_utc(oai_record.datestamp),
        doi_raw=None,
        title=(dc_root.findtext(f"{{{DC_NS}}}title") or "").strip() or None,
        publication_date=dates[0] if dates else None,
        work_type="preprint",
        venue_name="arXiv",
        authorships=tuple(
            {"author_id": None, "author_name": (element.text or "").strip(), "orcid": None, "institutions": []}
            for element in dc_root.findall(f"{{{DC_NS}}}creator")
        ),
        extra={"oai_identifier": oai_record.identifier, "oai_datestamp": oai_record.datestamp},
        payload=_element_to_dict(dc_root),
    )


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    def convert(node: ET.Element) -> Any:
        children = list(node)
        text = (node.text or "").strip()
        if not children:
            return text
        result: dict[str, Any] = {}
        for child in children:
            tag = child.tag.split("}")[-1]
            value = convert(child)
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(value)
            else:
                result[tag] = value
        return result

    converted = convert(element)
    return converted if isinstance(converted, dict) else {"value": converted}
