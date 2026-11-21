"""Extractor tests using mocked HTTP responses (no live API calls)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from extract.arxiv import ArxivExtractor
from extract.base import FetchWindow
from extract.crossref import CrossrefExtractor
from extract.datacite import DataCiteExtractor
from extract.http import HttpResponse, PermanentHttpError, RetryableHttpError
from extract.openalex import OpenAlexExtractor
from extract.zenodo import ZenodoExtractor


class FakeHttp:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, url: str, params: dict[str, str] | None = None, headers: Any = None) -> HttpResponse:
        self.calls.append((url, params))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        status, body = response
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        return HttpResponse(status=status, body=body, headers={}, url=url)


def test_openalex_follows_cursor_and_preserves_raw_objects() -> None:
    work = {"id": "https://openalex.org/W1", "display_name": "A paper", "nested": {"x": 1}}
    http = FakeHttp(
        [
            (200, {"meta": {"next_cursor": "abc"}, "results": [work]}),
            (200, {"meta": {"next_cursor": None}, "results": [{"id": "W2"}]}),
        ]
    )
    extractor = OpenAlexExtractor({"page_size": 100, "filter": "topics.id:T1"})
    window = FetchWindow("openalex", "work", "2024-01-01", "2024-12-31", "full")
    pages = list(extractor.iter_pages(http, window))

    assert [len(page.records) for page in pages] == [1, 1]
    assert pages[0].records[0] == work
    assert pages[0].next_cursor == "abc"
    assert pages[1].next_cursor is None
    assert http.calls[0][1] is not None
    assert http.calls[0][1]["filter"] == (
        "from_publication_date:2024-01-01,to_publication_date:2024-12-31,topics.id:T1"
    )
    assert http.calls[1][1]["cursor"] == "abc"


def test_openalex_has_no_page_cap_and_follows_every_cursor() -> None:
    responses: list[Any] = [
        (
            200,
            {"meta": {"next_cursor": f"cursor-{index}"}, "results": [{"id": f"W{index}"}]},
        )
        for index in range(5)
    ]
    responses.append((200, {"meta": {"next_cursor": None}, "results": [{"id": "W5"}]}))
    http = FakeHttp(responses)
    extractor = OpenAlexExtractor({"page_size": 100, "select": ["id", "doi"]})
    window = FetchWindow("openalex", "work", "2026-11-17", "2026-11-18", "full")

    pages = list(extractor.iter_pages(http, window))

    assert len(pages) == 6
    assert [page.next_cursor for page in pages] == [
        "cursor-0",
        "cursor-1",
        "cursor-2",
        "cursor-3",
        "cursor-4",
        None,
    ]
    assert http.calls[0][1]["cursor"] == "*"
    assert http.calls[0][1]["select"] == "id,doi"
    assert http.calls[-1][1]["cursor"] == "cursor-4"
    assert http.calls[0][1]["filter"] == (
        "from_publication_date:2026-11-17,to_publication_date:2026-11-18"
    )


def test_openalex_incremental_uses_updated_date_filter() -> None:
    http = FakeHttp([(200, {"meta": {"next_cursor": None}, "results": []})])
    extractor = OpenAlexExtractor({"page_size": 100, "filter": "has_doi:true"})
    window = FetchWindow("openalex", "work", "2026-11-18", "2026-11-19", "incremental")

    pages = list(extractor.iter_pages(http, window))

    assert len(pages) == 1
    assert pages[0].records == []
    params = http.calls[0][1]
    assert params is not None
    assert params["filter"] == (
        "from_updated_date:2026-11-18,to_updated_date:2026-11-19,has_doi:true"
    )
    assert "from_publication_date" not in params["filter"]


def test_openalex_rejects_a_page_cap() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        OpenAlexExtractor({"page_size": 100, "max_pages": 3})


def test_crossref_stops_on_short_page() -> None:
    http = FakeHttp(
        [
            (200, {"message": {"items": [{"DOI": "10.1/a"}, {"DOI": "10.1/b"}], "next-cursor": "c1"}}),
            (200, {"message": {"items": [{"DOI": "10.1/c"}], "next-cursor": "c2"}}),
        ]
    )
    extractor = CrossrefExtractor({"page_size": 2}, contact_email="test@example.org")
    window = FetchWindow("crossref", "work", "2024-01-01", "2024-01-01", "incremental")
    pages = list(extractor.iter_pages(http, window))

    assert len(pages) == 2
    assert pages[0].records[0] == {"DOI": "10.1/a"}
    assert http.calls[0][1]["filter"] == (
        "from-index-date:2024-01-01,until-index-date:2024-01-01"
    )
    assert http.calls[0][1]["mailto"] == "test@example.org"


def test_datacite_follows_next_link() -> None:
    http = FakeHttp(
        [
            (
                200,
                {
                    "data": [{"id": "10.1/a", "attributes": {"doi": "10.1/a"}}],
                    "links": {"next": "https://api.datacite.org/dois?page%5Bcursor%5D=abc"},
                },
            ),
            (200, {"data": [{"id": "10.1/b"}], "links": {}}),
        ]
    )
    extractor = DataCiteExtractor({"page_size": 1000, "query": "updated:[{window_start} TO {window_end}]"})
    window = FetchWindow("datacite", "doi", "2024-01-01", "2024-01-31", "incremental")
    pages = list(extractor.iter_pages(http, window))

    assert [len(page.records) for page in pages] == [1, 1]
    assert pages[0].records[0]["id"] == "10.1/a"
    assert http.calls[1][0].startswith("https://api.datacite.org/dois?page%5Bcursor%5D=")


ARXIV_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:arXiv.org:2401.00001</identifier>
        <datestamp>2024-01-02</datestamp>
        <setSpec>cs:cs:SE</setSpec>
      </header>
      <metadata>
        <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
          <id>2401.00001</id>
          <title>A &amp; B</title>
        </arXiv>
      </metadata>
    </record>
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:2401.00002</identifier>
        <datestamp>2024-01-03</datestamp>
      </header>
    </record>
    <resumptionToken>token-2</resumptionToken>
  </ListRecords>
</OAI-PMH>
"""


def test_arxiv_oai_preserves_xml_and_deleted_flag() -> None:
    http = FakeHttp([(200, ARXIV_PAGE), (200, ARXIV_PAGE.replace(b"token-2", b""))])
    extractor = ArxivExtractor({"metadata_prefix": "arXiv"})
    window = FetchWindow("arxiv", "record", "2024-01-01", "2024-12-31", "full")
    pages = list(extractor.iter_pages(http, window))

    first = pages[0].records[0]
    assert first["identifier"] == "oai:arXiv.org:2401.00001"
    assert "<arXiv" in first["metadata_xml"]
    assert "A &amp; B" in first["metadata_xml"]
    assert pages[0].records[1]["deleted"] is True
    assert pages[0].next_cursor == "token-2"
    assert http.calls[0][1]["metadataPrefix"] == "arXiv"
    assert http.calls[0][1]["from"] == "2024-01-01"
    assert "until" not in http.calls[0][1]


def test_zenodo_uses_bounded_oai_window() -> None:
    http = FakeHttp(
        [
            (200, ARXIV_PAGE.replace(b"arXiv", b"oai_datacite")),
            (200, ARXIV_PAGE.replace(b"arXiv", b"oai_datacite").replace(b"token-2", b"")),
        ]
    )
    extractor = ZenodoExtractor({"metadata_prefix": "oai_datacite"})
    window = FetchWindow("zenodo", "record", "2024-01-01", "2024-02-01", "incremental")
    pages = list(extractor.iter_pages(http, window))

    assert len(pages) == 2
    assert http.calls[0][1]["until"] == "2024-02-01"
    assert http.calls[0][1]["metadataPrefix"] == "oai_datacite"
    assert pages[1].next_cursor is None


def test_zenodo_http_422_on_resumption_token_restarts_window() -> None:
    http = FakeHttp(
        [
            (200, ARXIV_PAGE.replace(b"arXiv", b"oai_datacite")),
            (422, b"Invalid resumptionToken"),
            (200, ARXIV_PAGE.replace(b"arXiv", b"oai_datacite").replace(b"token-2", b"")),
        ]
    )
    extractor = ZenodoExtractor({"metadata_prefix": "oai_datacite"})
    window = FetchWindow("zenodo", "record", "2024-01-01", "2024-02-01", "incremental")

    with pytest.raises(RetryableHttpError):
        list(extractor.iter_pages(http, window))

    assert http.calls[0][1] is not None and "resumptionToken" not in http.calls[0][1]
    assert http.calls[1][1] is not None and http.calls[1][1]["resumptionToken"] == "token-2"


def test_oai_permanent_error_is_raised() -> None:
    body = b"""<?xml version="1.0"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <error code="badArgument">bad</error>
    </OAI-PMH>"""
    http = FakeHttp([(200, body)])
    extractor = ArxivExtractor({})
    window = FetchWindow("arxiv", "record", "2024-01-01", "2024-12-31", "full")
    with pytest.raises(PermanentHttpError):
        list(extractor.iter_pages(http, window))
