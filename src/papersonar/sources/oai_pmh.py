"""Shared OAI-PMH 2.0 client used by arXiv, DataCite and Zenodo adapters.

Handles ListRecords with datestamp windows, resumption-token pagination,
namespace-aware XML parsing and tombstone (deleted) detection. Expired
resumption tokens are raised as a recoverable condition: the adapter restarts
the bounded window from the beginning and relies on idempotent upserts, per the
approved recovery policy.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from papersonar.errors import PermanentError, RetryableError
from papersonar.http_client import HttpClient

logger = logging.getLogger(__name__)

OAI_NS = "http://www.openarchives.org/OAI/2.0/"

VERB_LIST_RECORDS = "ListRecords"


class OaiPmhClient:
    """Minimal OAI-PMH ListRecords harvester for one repository endpoint."""

    def __init__(self, http: HttpClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url

    def list_records(
        self,
        metadata_prefix: str,
        from_date: str | None = None,
        until_date: str | None = None,
        resumption_token: str | None = None,
        set_spec: str | None = None,
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        """Fetch one ListRecords page.

        Returns (raw_xml_bytes, next_resumption_token_or_None, request_descriptor).
        Raises RetryableError on badResumptionToken so callers can restart the
        window; raises PermanentError on other OAI errors.
        """
        params: dict[str, str] = {"verb": VERB_LIST_RECORDS}
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
        response = self.http.get(self.base_url, params=params)
        descriptor = {"method": "GET", "url": self.base_url, "params": params}
        self._check_errors(response.body)
        return response.body, _resumption_token(response.body), descriptor

    def _check_errors(self, body: bytes) -> None:
        root = ET.fromstring(body)
        error_element = root.find(f"{{{OAI_NS}}}error")
        if error_element is None:
            return
        code = error_element.get("code") or "unknown"
        message = (error_element.text or "").strip()
        if code == "badResumptionToken":
            raise RetryableError(
                f"OAI-PMH resumption token expired/invalid ({message}); "
                "restart the bounded window from its beginning"
            )
        raise PermanentError(f"OAI-PMH error {code}: {message}")


@dataclass(frozen=True)
class OaiRecord:
    identifier: str
    datestamp: str | None
    deleted: bool
    metadata: ET.Element | None  # <metadata> element (first child = format root)
    raw_element: ET.Element


def parse_records(body: bytes) -> list[OaiRecord]:
    """Extract ListRecords entries with tombstone detection."""
    root = ET.fromstring(body)
    records: list[OaiRecord] = []
    for element in root.findall(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}record"):
        header = element.find(f"{{{OAI_NS}}}header")
        if header is None:
            continue
        identifier = (header.findtext(f"{{{OAI_NS}}}identifier") or "").strip()
        datestamp = (header.findtext(f"{{{OAI_NS}}}datestamp") or "").strip() or None
        deleted = header.get("status") == "deleted"
        metadata = element.find(f"{{{OAI_NS}}}metadata")
        records.append(
            OaiRecord(
                identifier=identifier,
                datestamp=datestamp,
                deleted=deleted,
                metadata=metadata,
                raw_element=element,
            )
        )
    return records


def _resumption_token(body: bytes) -> str | None:
    root = ET.fromstring(body)
    token = root.find(f"{{{OAI_NS}}}ListRecords/{{{OAI_NS}}}resumptionToken")
    if token is None:
        return None
    text = (token.text or "").strip()
    return text or None
