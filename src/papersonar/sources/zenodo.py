"""Zenodo adapter: OAI-PMH datestamp harvesting with fast token expiry.

Verified against official docs on 2026-11-14 (developers.zenodo.org):
- REST API base https://zenodo.org/api/ (records search: q/page/size max 100,
  sort, all_versions) used for bounded backfill/detail fetches
- OAI-PMH is documented for metadata harvesting (ListRecords with datestamps
  and resumption tokens); OAI resumption tokens are short-lived, so pages are
  persisted immediately and an expired token restarts the window (idempotent)
- the ``oai_datacite`` format carries DataCite metadata XML (identifier/DOI,
  creators, publisher, dates, resourceType, relatedIdentifiers, version)

Stream scheme: ``oai:zenodo`` (OAI-PMH datestamp window).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord
from papersonar.sources.oai_pmh import OAI_NS, OaiPmhClient, parse_records
from papersonar.timeutil import parse_iso_utc

logger = logging.getLogger(__name__)

OAI_BASE_URL = "https://zenodo.org/oai2d"
DATACITE_NS = "http://datacite.org/schema/kernel-4"


class ZenodoAdapter(BaseAdapter):
    name = "zenodo"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._oai = OaiPmhClient(self.http, OAI_BASE_URL)

    def _metadata_prefix(self) -> str:
        return self.settings.extra("METADATA_PREFIX", "oai_datacite")

    def fetch_page(
        self, window: FetchWindow, cursor: str | None
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        body, next_token, descriptor = self._oai.list_records(
            metadata_prefix=self._metadata_prefix(),
            from_date=window.window_start,
            until_date=window.window_end,  # bounded OAI window per source contract
            resumption_token=cursor,
        )
        return body, next_token, descriptor

    def parse_page(self, payload: bytes) -> ParsedPage:
        oai_records = parse_records(payload)
        records = [r for r in (_to_record(rec) for rec in oai_records) if r is not None]
        root = ET.fromstring(payload)
        token = root.find(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}resumptionToken")
        next_token = ((token.text or "").strip() or None) if token is not None else None
        return ParsedPage(
            records=records,
            next_cursor=next_token,
            pages_complete=next_token is None,
            records_seen=len(oai_records),
        )


def _to_record(oai_record: Any) -> SourceRecord | None:
    """Build a SourceRecord from an oai_datacite (DataCite XML) OAI record."""
    if oai_record.deleted or oai_record.metadata is None:
        return None
    resource = oai_record.metadata[0] if len(oai_record.metadata) else None
    if resource is None:
        return None
    ns = _namespace_of(resource)
    if ns is None:
        return None

    doi = _text(resource, ns, "identifier")
    if doi and not doi.lower().startswith("10.") and "doi.org/" in doi.lower():
        doi = doi.split("doi.org/", 1)[-1]
    titles = [
        (node.text or "").strip()
        for node in resource.findall(f"{{{ns}}}titles/{{{ns}}}title")
    ]
    title = next((t for t in titles if t), None)
    creators = [
        {
            "author_id": _name_identifier(creator, ns),
            "author_name": _text(creator, ns, "creatorName"),
            "orcid": None,
            "institutions": [],
        }
        for creator in resource.findall(f"{{{ns}}}creators/{{{ns}}}creator")
    ]
    publication_year = _int_or_none(_text(resource, ns, "publicationYear"))
    dates = [
        {"date": node.text, "type": node.get("dateType")}
        for node in resource.findall(f"{{{ns}}}dates/{{{ns}}}date")
    ]
    publication_date = next(
        (
            entry["date"]
            for entry in dates
            if entry["type"] in ("Issued", None) and entry["date"]
        ),
        None,
    )
    resource_type = None
    type_node = resource.find(f"{{{ns}}}resourceType")
    if type_node is not None:
        resource_type = type_node.get("resourceTypeGeneral") or (type_node.text or "").strip() or None
    related = tuple(
        {
            "identifier": node.text,
            "relation": f"zenodo-relation:{node.get('relationType')}",
            "kind": node.get("relatedIdentifierType"),
        }
        for node in resource.findall(f"{{{ns}}}relatedIdentifiers/{{{ns}}}relatedIdentifier")
        if node.text
    )
    version = _text(resource, ns, "version")
    record_id = oai_record.identifier.rsplit(":", 1)[-1]
    return SourceRecord(
        source_name="zenodo",
        source_record_id=record_id,
        source_updated_at=parse_iso_utc(oai_record.datestamp),
        doi_raw=doi,
        title=title,
        publication_date=publication_date,
        publication_year=publication_year,
        work_type=resource_type or "dataset",
        venue_name="Zenodo",
        cited_by_count=None,
        related_identifiers=related,
        authorships=tuple(creators),
        extra={
            "oai_identifier": oai_record.identifier,
            "oai_datestamp": oai_record.datestamp,
            "metadata_prefix": "oai_datacite",
            "version": version,
            "dates": dates,
        },
        payload=_element_to_dict(resource),
    )


def _namespace_of(resource: ET.Element) -> str | None:
    if resource.tag.startswith("{"):
        return resource.tag.split("}", 1)[0][1:]
    return None


def _text(parent: ET.Element, ns: str, tag: str) -> str | None:
    value = (parent.findtext(f"{{{ns}}}{tag}") or "").strip()
    return value or None


def _name_identifier(creator: ET.Element, ns: str) -> str | None:
    node = creator.find(f"{{{ns}}}nameIdentifier")
    return (node.text or "").strip() or None if node is not None else None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


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
