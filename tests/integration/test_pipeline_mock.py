"""Integration pipeline against the mock Snowflake adapter.

Covers the playbook-07 integration layer: raw batch -> staging upsert ->
quarantine -> canonical crosswalk -> dimensions/bridges/facts -> quality gate,
plus idempotent replay and citation back-fill resolution.
"""

from __future__ import annotations

from papersonar.canonical import CanonicalResolver
from papersonar.raw_store import RawStore
from papersonar.sources.crossref import CrossrefAdapter
from papersonar.sources.openalex import OpenAlexAdapter
from papersonar.staging import StagingValidator
from papersonar.warehouse.loaders import WarehouseLoader
from papersonar.warehouse.migration_runner import MigrationRunner
from papersonar.warehouse.quality import QualityGate
from papersonar.warehouse.state_store import StateStore
from tests.fakes.fake_warehouse import FakeWarehouse
from tests.helpers import FakeResponse, FakeSession, fixture_bytes
from tests.unit.test_source_adapters import make_adapter, source_settings


def _fixture_session(name: str, fixture: str) -> FakeSession:
    """Fixture-backed session with a terminal empty page so pagination ends."""
    terminal = (
        b'{"meta": {"next_cursor": null}, "results": []}'
        if name == "openalex"
        else b'{"message": {"items": []}}'
    )
    return FakeSession(
        FakeResponse(content=fixture_bytes(name, fixture)),
        terminal_response=FakeResponse(content=terminal),
    )


class PipelineHarness:
    """End-to-end pipeline over the mock warehouse."""

    def __init__(self, tmp_path) -> None:
        self.warehouse = FakeWarehouse()
        MigrationRunner(self.warehouse).apply_all()
        self.state = StateStore(self.warehouse)
        self.raw_store = RawStore(
            warehouse=self.warehouse,
            state_store=self.state,
            raw_dir=tmp_path / "raw",
            schema_version="1",
        )
        self.validator = StagingValidator()
        self.loader = WarehouseLoader(self.warehouse)
        self.run_id = "run-test-1"

    def ingest_adapter_page(self, adapter_cls, session, settings_name, tmp_path, **init_kwargs):
        adapter, _, _ = make_adapter(adapter_cls, source_settings(settings_name), session, tmp_path, **init_kwargs)
        from papersonar.sources.base import FetchWindow

        window = FetchWindow(
            stream_name=adapter_cls.name and "year:2020",
            window_start="2020-01-01",
            window_end="2020-12-31",
            sync_mode="backfill",
        )
        totals = {"records": 0, "accepted": 0, "quarantined": 0}
        for batch in adapter.stream_pages(self.run_id, window):
            parsed = adapter.parse_page(batch.local_payload_path.read_bytes())
            outcome = self.validator.validate_batch(parsed.records, run_id=self.run_id, batch_id=batch.batch_id)
            totals["records"] += outcome.records_seen
            totals["accepted"] += len(outcome.accepted)
            totals["quarantined"] += len(outcome.quarantined)
            self.loader.load_staging(outcome)
            self.loader.load_quarantine(outcome)
            resolved = CanonicalResolver(self.warehouse).resolve_batch(outcome.accepted, self.run_id)
            self.loader.load_canonical(resolved)
            self.loader.load_dimensions(resolved.resolved_rows)
            self.loader.load_facts(resolved, self.run_id)
            self.raw_store.mark_complete(batch.batch_id)
        return totals

    def refresh_citations(self) -> int:
        return self.loader.refresh_citation_resolution()

    def gate(self):
        return QualityGate(self.warehouse).run()

    def count(self, table: str) -> int:
        return self.warehouse.count(table)


class TestFullPipelineMock:
    def test_openalex_and_crossref_end_to_end(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        openalex_session = _fixture_session("openalex", "page1.json")
        crossref_session = _fixture_session("crossref", "page1.json")

        totals = pipeline.ingest_adapter_page(OpenAlexAdapter, openalex_session, "openalex", tmp_path)
        assert totals["accepted"] == 2
        assert totals["quarantined"] == 0

        totals = pipeline.ingest_adapter_page(CrossrefAdapter, crossref_session, "crossref", tmp_path)
        assert totals["accepted"] == 2

        # Canonical layer
        assert pipeline.count("PROJECT_DW.DIM_WORK") == 4  # 4 distinct identities
        assert pipeline.count("PROJECT_DW.WORK_SOURCE_XW") == 4
        assert pipeline.count("PROJECT_DW.FACT_PUBLICATION") == 4
        assert pipeline.count("PROJECT_DW.FACT_WORK_SNAPSHOT") == 4
        # Citations: openalex provider refs (2) + crossref DOI refs (2)
        assert pipeline.count("PROJECT_DW.FACT_CITATION") == 4
        # Dimensions and bridges populated
        assert pipeline.count("PROJECT_DW.DIM_AUTHOR") >= 2
        assert pipeline.count("PROJECT_DW.DIM_TOPIC") >= 2
        assert pipeline.count("PROJECT_DW.DIM_VENUE") >= 2
        assert pipeline.count("PROJECT_DW.BRIDGE_WORK_AUTHOR") >= 2

        result = pipeline.gate()
        assert result.passed is True
        assert result.summary == "PASS"

    def test_replay_is_idempotent(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        openalex_session = _fixture_session("openalex", "page1.json")
        crossref_session = _fixture_session("crossref", "page1.json")
        pipeline.ingest_adapter_page(OpenAlexAdapter, openalex_session, "openalex", tmp_path)
        pipeline.ingest_adapter_page(CrossrefAdapter, crossref_session, "crossref", tmp_path)

        counts_before = {
            table: pipeline.count(table)
            for table in (
                "PROJECT_STAGING.STG_WORK_RECORD",
                "PROJECT_OPS.RAW_BATCH",
                "PROJECT_DW.DIM_WORK",
                "PROJECT_DW.WORK_SOURCE_XW",
                "PROJECT_DW.FACT_PUBLICATION",
                "PROJECT_DW.FACT_WORK_SNAPSHOT",
                "PROJECT_DW.FACT_CITATION",
            )
        }
        # Replay the exact same fetches (safe resume after interruption)
        pipeline.ingest_adapter_page(OpenAlexAdapter, _fixture_session("openalex", "page1.json"), "openalex", tmp_path)
        pipeline.ingest_adapter_page(CrossrefAdapter, _fixture_session("crossref", "page1.json"), "crossref", tmp_path)

        counts_after = {
            table: pipeline.count(table)
            for table in (
                "PROJECT_STAGING.STG_WORK_RECORD",
                "PROJECT_DW.DIM_WORK",
                "PROJECT_DW.WORK_SOURCE_XW",
                "PROJECT_DW.FACT_PUBLICATION",
                "PROJECT_DW.FACT_WORK_SNAPSHOT",
                "PROJECT_DW.FACT_CITATION",
            )
        }
        for table, count_value in counts_after.items():
            assert count_value == counts_before[table], f"{table} changed on replay"

    def test_changed_content_creates_new_staging_version(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        session = _fixture_session("openalex", "page1.json")
        pipeline.ingest_adapter_page(OpenAlexAdapter, session, "openalex", tmp_path)
        assert pipeline.count("PROJECT_STAGING.STG_WORK_RECORD") == 2

        # Same work, updated metric -> new content version row, canonical updated
        updated_fixture = fixture_bytes("openalex", "page1.json").decode("utf-8").replace(
            '"cited_by_count": 12', '"cited_by_count": 13'
        )
        session = FakeSession(
            FakeResponse(content=updated_fixture.encode("utf-8")),
            terminal_response=FakeResponse(content=b'{"meta": {"next_cursor": null}, "results": []}'),
        )
        pipeline.ingest_adapter_page(OpenAlexAdapter, session, "openalex", tmp_path)
        assert pipeline.count("PROJECT_STAGING.STG_WORK_RECORD") == 3  # history preserved
        assert pipeline.count("PROJECT_DW.DIM_WORK") == 2  # no new identity
        fact = next(
            row
            for row in pipeline.warehouse.tables["PROJECT_DW.FACT_PUBLICATION"].rows
            if row["WORK_KEY"] == "doi:10.5555/test-one"
        )
        assert fact["CITED_BY_COUNT"] == 13

    def test_citation_backfill_resolves_later_arrivals(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        crossref_session = _fixture_session("crossref", "page1.json")
        pipeline.ingest_adapter_page(CrossrefAdapter, crossref_session, "crossref", tmp_path)
        # crossref item one references 10.5555/ref1 and 10.5555/ref2: unresolved so far
        rows = pipeline.warehouse.tables["PROJECT_DW.FACT_CITATION"].rows
        assert all(row["CITED_WORK_KEY"] in ("", None) for row in rows)

        # A later run ingests the referenced work
        referenced_record = fixture_bytes("crossref", "page1.json").decode("utf-8")
        referenced_session = FakeSession(
            FakeResponse(
                content=referenced_record.replace("10.5555/ref1", "10.5555/ref1-ingested").encode("utf-8")
            )
        )
        pipeline.ingest_adapter_page(CrossrefAdapter, referenced_session, "crossref", tmp_path)
        # Now ingest a work whose DOI equals one of the cited DOIs
        from papersonar.sources.base import SourceRecord

        record = SourceRecord(
            source_name="crossref",
            source_record_id="10.5555/ref1",
            doi_raw="10.5555/ref1",
            title="Referenced work one",
        )
        outcome = pipeline.validator.validate_batch([record], run_id=pipeline.run_id, batch_id="manual")
        pipeline.loader.load_staging(outcome)
        resolved = CanonicalResolver(pipeline.warehouse).resolve_batch(outcome.accepted, pipeline.run_id)
        pipeline.loader.load_canonical(resolved)
        pipeline.loader.load_facts(resolved, pipeline.run_id)

        refreshed = pipeline.refresh_citations()
        assert refreshed >= 1
        rows = pipeline.warehouse.tables["PROJECT_DW.FACT_CITATION"].rows
        resolved_rows = [row for row in rows if row["CITED_DOI"] == "10.5555/ref1"]
        assert resolved_rows
        assert all(row["CITED_WORK_KEY"] == "doi:10.5555/ref1" for row in resolved_rows)

    def test_quarantined_records_do_not_pollute_warehouse(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        from papersonar.sources.base import SourceRecord

        bad = SourceRecord(source_name="crossref", source_record_id="", doi_raw="garbage-doi", title="bad")
        outcome = pipeline.validator.validate_batch([bad], run_id=pipeline.run_id, batch_id="b1")
        pipeline.loader.load_staging(outcome)
        pipeline.loader.load_quarantine(outcome)
        assert pipeline.count("PROJECT_STAGING.STG_WORK_RECORD") == 0
        assert pipeline.count("PROJECT_STAGING.STG_QUARANTINE") == 1
        resolved = CanonicalResolver(pipeline.warehouse).resolve_batch(outcome.accepted, pipeline.run_id)
        pipeline.loader.load_canonical(resolved)
        assert pipeline.count("PROJECT_DW.DIM_WORK") == 0
        result = pipeline.gate()
        # 100% quarantine ratio fails the gate
        assert result.passed is False
        assert result.summary == "FAIL"

    def test_migration_002_creates_warehouse_objects(self, tmp_path):
        pipeline = PipelineHarness(tmp_path)
        # All DW tables exist in the mock after migrations
        expected = {
            "PROJECT_DW.DIM_WORK",
            "PROJECT_DW.WORK_SOURCE_XW",
            "PROJECT_DW.DIM_DATE",
            "PROJECT_DW.DIM_TOPIC",
            "PROJECT_DW.DIM_VENUE",
            "PROJECT_DW.DIM_WORK_TYPE",
            "PROJECT_DW.DIM_ACCESS_STATUS",
            "PROJECT_DW.DIM_AUTHOR",
            "PROJECT_DW.DIM_INSTITUTION",
            "PROJECT_DW.FACT_PUBLICATION",
            "PROJECT_DW.FACT_WORK_SNAPSHOT",
            "PROJECT_DW.FACT_CITATION",
            "PROJECT_DW.BRIDGE_WORK_TOPIC",
            "PROJECT_DW.BRIDGE_WORK_AUTHOR",
            "PROJECT_DW.BRIDGE_WORK_INSTITUTION",
        }
        assert expected.issubset(set(pipeline.warehouse.tables.keys()))
