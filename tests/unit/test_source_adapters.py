"""Adapter contract tests against sanitized fixtures (no network)."""

from datetime import UTC, datetime

import pytest

from papersonar.config import RetrySettings, SourceSettings
from papersonar.errors import PermanentError, RetryableError
from papersonar.http_client import HttpClient
from papersonar.raw_store import RawStore
from papersonar.sources.arxiv import ArxivAdapter
from papersonar.sources.crossref import CrossrefAdapter
from papersonar.sources.datacite import DataciteAdapter
from papersonar.sources.openalex import OpenAlexAdapter
from papersonar.sources.zenodo import ZenodoAdapter
from papersonar.warehouse.state_store import StateStore
from tests.fakes.fake_warehouse import FakeWarehouse
from tests.helpers import FakeResponse, FakeSession, fixture_bytes


def source_settings(name: str, **overrides) -> SourceSettings:
    defaults = dict(
        name=name,
        enabled=True,
        page_size=100,
        max_pages=50,
        timeout_seconds=30.0,
        rate_delay_seconds=0.0,
        sync_overlap_days=1,
        backfill_from_date=None,
        retries=RetrySettings(),
        extras={},
    )
    defaults.update(overrides)
    return SourceSettings(**defaults)


def make_adapter(cls, settings, session, tmp_path, **init_kwargs):
    sleeps: list[float] = []
    http = HttpClient(
        timeout_seconds=5,
        max_attempts=2,
        backoff_base_seconds=1,
        backoff_max_seconds=2,
        rate_delay_seconds=0.0,
        user_agent="PaperSonar-test/1.0",
        sleep=sleeps.append,
        session=session,
    )
    warehouse = FakeWarehouse()
    raw_store = RawStore(
        warehouse=warehouse,
        state_store=StateStore(warehouse),
        raw_dir=tmp_path / "raw",
        schema_version="1",
    )
    adapter = cls(settings, http, raw_store, **init_kwargs)
    return adapter, warehouse, http


class TestOpenAlexAdapter:
    def test_fetch_page_uses_verified_parameters(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("openalex", "page1.json")))
        settings = source_settings("openalex", extras={"FILTER": "topics.id:T10743"})
        adapter, _, _ = make_adapter(OpenAlexAdapter, settings, session, tmp_path)
        window = _window("year:2020", "2020-01-01", "2020-12-31")
        payload, next_cursor, descriptor = adapter.fetch_page(window, cursor=None)
        assert next_cursor == "IlsxNzA0MDQ0ODAwMDAwMDAwL"
        assert descriptor["url"] == "https://api.openalex.org/works"
        sent = session.calls[0]["params"]
        assert sent["cursor"] == "*"  # verified start cursor
        assert sent["per_page"] == "100"  # verified max 100
        assert sent["filter"] == "publication_year:2020,topics.id:T10743"
        assert "api_key" not in sent  # key absent unless configured

    def test_parse_page_common_shape(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("openalex", "page1.json")))
        adapter, _, _ = make_adapter(OpenAlexAdapter, source_settings("openalex"), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("openalex", "page1.json"))
        assert page.records_seen == 2
        assert page.next_cursor == "IlsxNzA0MDQ0ODAwMDAwMDAwL"
        assert page.pages_complete is False
        work = page.records[0]
        assert work.source_name == "openalex"
        assert work.source_record_id == "W2102429193"
        assert work.doi_raw == "https://doi.org/10.5555/test-one"
        assert work.title == "Test work one"
        assert work.publication_year == 2020
        assert work.work_type == "article"
        assert work.venue_name == "Journal of Tests"
        assert work.oa_is_oa is True
        assert work.oa_status == "gold"
        assert work.cited_by_count == 12
        assert work.referenced_ids == ("https://openalex.org/W1", "https://openalex.org/W2")
        assert work.topics[0]["id"] == "T10743"
        assert work.topics[0]["primary"] is True
        assert work.authorships[0]["author_id"] == "A1"
        assert work.authorships[0]["institutions"][0]["id"] == "I1"
        assert work.source_updated_at == datetime(2025, 1, 2, tzinfo=UTC)

    def test_last_page_complete_when_no_cursor(self, tmp_path):
        final_page = b'{"meta": {"next_cursor": null}, "results": []}'
        session = FakeSession(FakeResponse(content=final_page))
        adapter, _, _ = make_adapter(OpenAlexAdapter, source_settings("openalex"), session, tmp_path)
        page = adapter.parse_page(final_page)
        assert page.pages_complete is True

    def test_unknown_stream_rejected(self, tmp_path):
        session = FakeSession(FakeResponse(content=b"{}"))
        adapter, _, _ = make_adapter(OpenAlexAdapter, source_settings("openalex"), session, tmp_path)
        with pytest.raises(PermanentError, match="year:YYYY"):
            adapter.fetch_page(_window("bogus", None, None), None)

    def test_api_key_not_in_descriptor(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("openalex", "page1.json")))
        adapter, _, _ = make_adapter(
            OpenAlexAdapter, source_settings("openalex"), session, tmp_path, api_key="sk-test-key-123"
        )
        _, _, descriptor = adapter.fetch_page(_window("year:2020", None, None), None)
        assert "api_key" not in descriptor["params"]
        assert session.calls[0]["params"]["api_key"] == "sk-test-key-123"


class TestCrossrefAdapter:
    def test_fetch_page_uses_verified_parameters(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("crossref", "page1.json")))
        settings = source_settings("crossref", page_size=2)
        adapter, _, _ = make_adapter(
            CrossrefAdapter, settings, session, tmp_path, contact_email="team@example.org"
        )
        window = _window("indexdate:2026-01-25", "2026-01-25", "2026-01-25")
        payload, next_cursor, descriptor = adapter.fetch_page(window, None)
        assert next_cursor == "cursor-to-page-2"
        sent = session.calls[0]["params"]
        assert sent["filter"] == "from-index-date:2026-01-25,until-index-date:2026-01-25"
        assert sent["rows"] == "2"
        assert sent["cursor"] == "*"
        assert session.calls[0]["params"]["mailto"] == "team@example.org"

    def test_parse_page(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("crossref", "page1.json")))
        adapter, _, _ = make_adapter(CrossrefAdapter, source_settings("crossref", page_size=2), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("crossref", "page1.json"))
        assert page.records_seen == 2
        assert page.next_cursor == "cursor-to-page-2"
        item = page.records[0]
        assert item.source_name == "crossref"
        assert item.source_record_id == "10.5555/one"
        assert item.doi_raw == "10.5555/one"
        assert item.title == "Crossref item one"
        assert item.publication_date == "2020-03-14"
        assert item.publication_year == 2020
        assert item.venue_name == "Journal of Tests"
        assert item.cited_by_count == 7
        assert item.referenced_dois == ("10.5555/ref1", "10.5555/ref2")
        assert item.authorships[0]["author_name"] == "Grace Hopper"
        assert item.source_updated_at == datetime(2026, 1, 25, 12, 0, tzinfo=UTC)

    def test_year_only_date(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("crossref", "page1.json")))
        adapter, _, _ = make_adapter(CrossrefAdapter, source_settings("crossref", page_size=2), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("crossref", "page1.json"))
        assert page.records[1].publication_date == "2021"

    def test_last_page_when_items_less_than_rows(self, tmp_path):
        body = b'{"message": {"items": [{"DOI": "10.1/x"}], "items-per-page": 100}}'
        session = FakeSession(FakeResponse(content=body))
        adapter, _, _ = make_adapter(CrossrefAdapter, source_settings("crossref", page_size=100), session, tmp_path)
        page = adapter.parse_page(body)
        assert page.pages_complete is True


class TestArxivAdapter:
    def test_parse_page_versions_and_deletions(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("arxiv", "listrecords1.xml")))
        adapter, _, _ = make_adapter(ArxivAdapter, source_settings("arxiv"), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("arxiv", "listrecords1.xml"))
        assert page.records_seen == 2  # one live + one tombstone
        assert len(page.records) == 1  # tombstones are not staged
        assert page.next_cursor == "tok-page2"
        record = page.records[0]
        assert record.source_name == "arxiv"
        assert record.source_record_id == "2401.00001"
        assert record.doi_raw == "10.5555/arxiv-doi"
        assert record.work_type == "preprint"
        assert record.venue_name == "arXiv"
        assert record.publication_date == "2024-01-01"
        assert record.extra["categories"] == ["cs.SE", "cs.PL"]
        assert record.extra["updated"] == "2024-06-01"
        assert [a["author_name"] for a in record.authorships] == ["Ada Lovelace", "Grace Hopper"]
        assert record.related_identifiers[0]["relation"] == "is-article-in-journal"

    def test_fetch_page_from_only_and_set(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("arxiv", "listrecords1.xml")))
        adapter, _, _ = make_adapter(ArxivAdapter, source_settings("arxiv"), session, tmp_path)
        window = _window("set:cs:cs:SE", "2026-01-01", None)
        adapter.fetch_page(window, cursor=None)
        sent = session.calls[0]["params"]
        assert sent["verb"] == "ListRecords"
        assert sent["metadataPrefix"] == "arXiv"
        assert sent["from"] == "2026-01-01"
        assert "until" not in sent  # official guidance: no until for incremental
        assert sent["set"] == "cs:cs:SE"

    def test_expired_token_raises_retryable_restart(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("arxiv", "bad_resumption_token.xml")))
        adapter, _, _ = make_adapter(ArxivAdapter, source_settings("arxiv"), session, tmp_path)
        window = _window("oai:arxiv", "2026-01-01", None)
        with pytest.raises(RetryableError, match="resumption token"):
            adapter.fetch_page(window, cursor="expired-token")


class TestDataciteAdapter:
    def test_fetch_page_parameters(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("datacite", "page1.json")))
        adapter, _, _ = make_adapter(DataciteAdapter, source_settings("datacite"), session, tmp_path)
        window = _window("updated:2026-01-20", "2026-01-20", "2026-01-20")
        _, next_cursor, descriptor = adapter.fetch_page(window, None)
        assert next_cursor == "next-cursor-token"
        sent = session.calls[0]["params"]
        assert sent["page[size]"] == "100"
        assert sent["sort"] == "-updated"  # verified sort option
        assert sent["page[cursor]"] == "1"

    def test_parse_page(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("datacite", "page1.json")))
        adapter, _, _ = make_adapter(DataciteAdapter, source_settings("datacite"), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("datacite", "page1.json"))
        assert page.records_seen == 2
        record = page.records[0]
        assert record.source_name == "datacite"
        assert record.source_record_id == "10.5555/dc-one"
        assert record.doi_raw == "10.5555/dc-one"
        assert record.title == "DataCite test dataset one"
        assert record.publication_year == 2022
        assert record.publication_date == "2022-04-01"
        assert record.work_type == "Dataset"
        assert record.venue_name == "Test Repository"
        assert record.authorships[0]["author_name"] == "Grace Hopper"
        assert record.authorships[0]["author_id"] == "https://orcid.org/0000-0002-1111-1111"
        assert record.authorships[0]["institutions"][0]["id"] == "https://ror.org/02mhbdp94"
        assert record.related_identifiers[0]["relation"] == "datacite-relation:IsSupplementTo"
        assert record.source_updated_at == datetime(2026, 1, 20, 10, 0, tzinfo=UTC)


class TestZenodoAdapter:
    def test_parse_page(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("zenodo", "listrecords1.xml")))
        adapter, _, _ = make_adapter(ZenodoAdapter, source_settings("zenodo"), session, tmp_path)
        page = adapter.parse_page(fixture_bytes("zenodo", "listrecords1.xml"))
        assert page.records_seen == 2  # one live + one tombstone
        assert len(page.records) == 1
        assert page.next_cursor == "zen-tok-2"
        record = page.records[0]
        assert record.source_name == "zenodo"
        assert record.source_record_id == "12345"
        assert record.doi_raw == "10.5281/zenodo.12345"
        assert record.title == "Zenodo test dataset one"
        assert record.publication_year == 2023
        assert record.publication_date == "2023-06-01"
        assert record.work_type == "Dataset"
        assert record.extra["version"] == "v1.0"
        assert record.authorships[0]["author_name"] == "Doe, Jane"
        assert record.related_identifiers[0]["relation"] == "zenodo-relation:IsSupplementTo"

    def test_fetch_page_window(self, tmp_path):
        session = FakeSession(FakeResponse(content=fixture_bytes("zenodo", "listrecords1.xml")))
        adapter, _, _ = make_adapter(ZenodoAdapter, source_settings("zenodo"), session, tmp_path)
        window = _window("oai:zenodo", "2026-02-01", "2026-02-01")
        adapter.fetch_page(window, None)
        sent = session.calls[0]["params"]
        assert sent["metadataPrefix"] == "oai_datacite"
        assert sent["from"] == "2026-02-01"
        assert sent["until"] == "2026-02-01"
        assert sent["verb"] == "ListRecords"


def _window(stream: str, start: str | None, end: str | None):
    from papersonar.sources.base import FetchWindow

    return FetchWindow(stream_name=stream, window_start=start, window_end=end, sync_mode="sync")
