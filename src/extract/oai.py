"""OAI-PMH 2.0 harvesting helper for arXiv and Zenodo.

The raw metadata XML is preserved inside the emitted JSON object. Converting an
XML response into a JSON envelope is transport serialisation, not cleaning: the
metadata document itself is stored byte-for-byte (after XML decoding) and all
interpretation happens later in Snowflake SQL.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from extract.http import Http, PermanentHttpError, RetryableHttpError

OAI_NS = "http://www.openarchives.org/OAI/2.0/"


@dataclass(frozen=True)
class OaiRecord:
    identifier: str
    datestamp: str | None
    set_spec: list[str]
    deleted: bool
    metadata_xml: str | None


def list_records(
    http: Http,
    base_url: str,
    metadata_prefix: str,
    from_date: str | None,
    until_date: str | None,
    resumption_token: str | None,
    set_spec: str | None = None,
) -> tuple[list[OaiRecord], str | None, dict[str, Any]]:
    """Fetch one OAI-PMH ListRecords page.

    Returns ``(records, next_resumption_token, request_descriptor)``. An expired
    token is raised as ``RetryableHttpError`` so the runner can restart the
    bounded window; other OAI errors are permanent.
    """
    params: dict[str, str] = {"verb": "ListRecords"}
    if resumption_token:
        params["resumptionToken"] = resumption_token
    else:
        params["metadataPrefix"] = metadata_prefix
        if from_date:
            params["from"] = from_date
        if until_date:
            params["until"] = until_date
        if set_spec:
            params["set"] = set_spec

    response = http.get(base_url, params=params)
    descriptor = {"method": "GET", "url": base_url, "params": params}
    return parse_page(response.body), next_token(response.body), descriptor


def parse_page(body: bytes) -> list[OaiRecord]:
    root = _parse(body)
    _raise_for_oai_error(root)
    metadata_blocks = _metadata_blocks(body)
    records: list[OaiRecord] = []
    for element in root.findall(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}record"):
        header = element.find(f"{{{OAI_NS}}}header")
        if header is None:
            continue
        identifier = (header.findtext(f"{{{OAI_NS}}}identifier") or "").strip()
        datestamp = (header.findtext(f"{{{OAI_NS}}}datestamp") or "").strip() or None
        set_spec = [
            (node.text or "").strip()
            for node in header.findall(f"{{{OAI_NS}}}setSpec")
            if (node.text or "").strip()
        ]
        deleted = header.get("status") == "deleted"
        metadata = element.find(f"{{{OAI_NS}}}metadata")
        metadata_xml = None
        if metadata is not None and len(metadata):
            # Preserve the exact metadata fragment (including source prefixes and
            # entities) instead of re-serialising the parsed element tree.
            metadata_xml = metadata_blocks.pop(0) if metadata_blocks else ET.tostring(
                metadata[0], encoding="unicode"
            )
        records.append(
            OaiRecord(
                identifier=identifier,
                datestamp=datestamp,
                set_spec=set_spec,
                deleted=deleted,
                metadata_xml=metadata_xml,
            )
        )
    return records


def _metadata_blocks(body: bytes) -> list[str]:
    pattern = re.compile(
        rb"<(?:\w+:)?metadata\b[^>]*>(.*?)</(?:\w+:)?metadata>", re.DOTALL
    )
    return [match.group(1).decode("utf-8", errors="replace").strip() for match in pattern.finditer(body)]


def next_token(body: bytes) -> str | None:
    root = _parse(body)
    token = root.find(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}resumptionToken")
    if token is None:
        return None
    text = (token.text or "").strip()
    return text or None


def to_payload(record: OaiRecord, metadata_prefix: str) -> dict[str, Any]:
    """Wrap an OAI record as a raw JSON object (no field extraction)."""
    return {
        "identifier": record.identifier,
        "datestamp": record.datestamp,
        "set_spec": record.set_spec,
        "deleted": record.deleted,
        "metadata_prefix": metadata_prefix,
        "metadata_xml": record.metadata_xml,
    }


def _parse(body: bytes) -> ET.Element:
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise PermanentHttpError(f"Malformed OAI-PMH XML: {exc}") from exc


def _raise_for_oai_error(root: ET.Element) -> None:
    error = root.find(f"{{{OAI_NS}}}error")
    if error is None:
        return
    code = error.get("code") or "unknown"
    message = (error.text or "").strip()
    if code == "badResumptionToken":
        raise RetryableHttpError(
            f"OAI-PMH resumption token expired ({message}); restart the bounded window"
        )
    raise PermanentHttpError(f"OAI-PMH error {code}: {message}")
