"""Orchestrator tests: run status policy, checkpoints, recovery, dry-run."""

from __future__ import annotations

import pytest

from papersonar.config import Settings
from papersonar.errors import ConfigurationError
from papersonar.orchestrator import Orchestrator, _final_status
from papersonar.sources.crossref import CrossrefAdapter
from papersonar.warehouse.state_store import StateStore
from tests.fakes.fake_warehouse import FakeWarehouse
from tests.helpers import FakeResponse, FakeSession
from tests.integration.test_pipeline_mock import _fixture_session
from tests.unit.test_source_adapters import make_adapter, source_settings

SNOWFLAKE_ENV = {
    "PAPERSONAR_TARGET": "snowflake",
    "SNOWFLAKE_ACCOUNT": "xy12345.eu-central-1",
    "SNOWFLAKE_USER": "svc_papersonar",
    "SNOWFLAKE_ROLE": "PAPERSONAR_INGEST",
    "SNOWFLAKE_WAREHOUSE": "PAPERSONAR_WH",
    "SNOWFLAKE_DATABASE": "PAPERSONAR",
    "SNOWFLAKE_SCHEMA": "INGEST",
    "SNOWFLAKE_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----",
}


def settings_for(enabled: dict[str, bool]) -> Settings:
    env = {**SNOWFLAKE_ENV}
    for name, is_enabled in enabled.items():
        env[f"{name.upper()}_ENABLED"] = "true" if is_enabled else "false"
    return Settings.from_env(env)


def _enabled_only(name: str) -> dict[str, bool]:
    return {source: source == name for source in ("openalex", "crossref", "arxiv", "datacite", "zenodo")}


def patch_build_adapters(monkeypatch, tmp_path, failing: bool = False):
    """Point every adapter at a fake HTTP session (fixture-backed or failing)."""

    def build(self, name):
        if failing:
            session = FakeSession(
                [FakeResponse(status_code=429)], terminal_response=FakeResponse(status_code=429)
            )
        else:
            fixture = {"openalex": "page1.json", "crossref": "page1.json"}.get(name, "page1.json")
            session = _fixture_session(name, fixture)
        from papersonar.sources import ADAPTERS

        adapter, _, _ = make_adapter(ADAPTERS[name], source_settings(name), session, tmp_path)
        return adapter

    monkeypatch.setattr(Orchestrator, "_build_adapter", build)


class TestRunStatusPolicy:
    def test_final_status_matrix(self):
        assert _final_status({"openalex": "succeeded", "crossref": "succeeded"}, True) == "succeeded"
        assert _final_status({"openalex": "succeeded", "crossref": "failed"}, True) == "partial"
        assert _final_status({"openalex": "succeeded", "crossref": "succeeded"}, False) == "partial"
        assert _final_status({"openalex": "failed", "crossref": "failed"}, True) == "failed"
        assert _final_status({}, True) == "failed"


class TestOrchestrator:
    def test_no_enabled_sources_fails_closed(self, tmp_path):
        disabled = {"openalex": False, "crossref": False, "arxiv": False, "datacite": False, "zenodo": False}
        orchestrator = Orchestrator(settings_for(disabled))
        with pytest.raises(ConfigurationError, match="No sources enabled"):
            orchestrator.run("sync")

    def test_requires_snowflake_before_any_source_call(self, tmp_path, monkeypatch):
        env = {**SNOWFLAKE_ENV, "SNOWFLAKE_ACCOUNT": ""}
        for name in ("openalex", "crossref", "arxiv", "datacite", "zenodo"):
            env[f"{name.upper()}_ENABLED"] = "false"
        settings = Settings.from_env(env)
        called = []
        monkeypatch.setattr(Orchestrator, "_build_adapter", lambda self, name: called.append(name))
        orchestrator = Orchestrator(settings, warehouse=FakeWarehouse())
        with pytest.raises(ConfigurationError, match="SNOWFLAKE_ACCOUNT"):
            orchestrator.run("sync")
        assert not called  # no source adapters were built before failing closed

    def test_successful_sync_run(self, tmp_path, monkeypatch):
        patch_build_adapters(monkeypatch, tmp_path)
        settings = settings_for(_enabled_only("openalex"))
        warehouse = FakeWarehouse()
        orchestrator = Orchestrator(settings, warehouse=warehouse)
        result = orchestrator.run("sync")
        assert result.status == "succeeded"
        assert result.source_statuses == {"openalex": "succeeded"}
        assert result.staging_rows == 2
        assert result.gate_summary == "PASS"
        # Run recorded with quality gate result
        run_rows = warehouse.tables["PROJECT_OPS.ETL_RUN"].rows
        assert run_rows[0]["STATUS"] == "succeeded"
        assert run_rows[0]["QUALITY_GATE_RESULT"] == "PASS"
        assert run_rows[0]["MODE"] == "sync"
        # Watermark advanced for the openalex partition
        state = StateStore(warehouse).get_sync_state("openalex", f"year:{__import__('datetime').date.today().year}")
        assert state is not None
        assert state.status == "succeeded"
        assert state.last_successful_watermark == f"{__import__('datetime').date.today().year}-12-31"
        # Migrations applied and warehouse populated (001, 002, 003)
        assert warehouse.count("PROJECT_DW.DIM_WORK") == 2
        assert warehouse.count("PROJECT_OPS.SCHEMA_MIGRATION") == 4

    def test_source_failure_marks_run_partial_and_keeps_watermark(self, tmp_path, monkeypatch):
        patch_build_adapters(monkeypatch, tmp_path, failing=True)
        settings = settings_for(
            {"openalex": True, "crossref": True, "arxiv": False, "datacite": False, "zenodo": False}
        )
        # Make crossref succeed so the run is partial (one ok, one failed).
        original_build = Orchestrator._build_adapter

        def build(self, name):
            if name == "crossref":
                adapter, _, _ = make_adapter(
                    CrossrefAdapter, source_settings("crossref"), _fixture_session("crossref", "page1.json"), tmp_path
                )
                return adapter
            return original_build(self, name)

        monkeypatch.setattr(Orchestrator, "_build_adapter", build)

        warehouse = FakeWarehouse()
        orchestrator = Orchestrator(settings, warehouse=warehouse)
        result = orchestrator.run("sync")
        assert result.status == "partial"
        assert result.source_statuses["openalex"] == "failed"
        assert result.source_statuses["crossref"] == "succeeded"
        run_rows = warehouse.tables["PROJECT_OPS.ETL_RUN"].rows
        assert run_rows[0]["STATUS"] == "partial"
        assert run_rows[0]["ERROR_SUMMARY"] is None  # source failures don't abort the run
        # Watermark NOT advanced for the failed source
        state = StateStore(warehouse).get_sync_state("openalex", f"year:{__import__('datetime').date.today().year}")
        assert state is not None
        assert state.status == "failed"
        assert state.last_successful_watermark is None
        assert state.error_code == "RetryableError"

    def test_all_sources_failed_run_failed(self, tmp_path, monkeypatch):
        patch_build_adapters(monkeypatch, tmp_path, failing=True)
        settings = settings_for(
            {"openalex": True, "crossref": False, "arxiv": False, "datacite": False, "zenodo": False}
        )
        warehouse = FakeWarehouse()
        orchestrator = Orchestrator(settings, warehouse=warehouse)
        result = orchestrator.run("sync")
        assert result.status == "failed"
        run_rows = warehouse.tables["PROJECT_OPS.ETL_RUN"].rows
        assert run_rows[0]["STATUS"] == "failed"

    def test_resume_uses_saved_cursor(self, tmp_path, monkeypatch):
        from papersonar.sources.base import BaseAdapter
        from papersonar.warehouse.state_store import SyncState

        patch_build_adapters(monkeypatch, tmp_path)
        settings = settings_for(
            {"openalex": True, "crossref": False, "arxiv": False, "datacite": False, "zenodo": False}
        )
        warehouse = FakeWarehouse()
        year = __import__("datetime").date.today().year
        StateStore(warehouse).save_sync_state(
            SyncState(
                source_name="openalex",
                stream_name=f"year:{year}",
                cursor_or_token="saved-cursor-token",
                status="running",
            )
        )
        captured = {}
        original_stream_pages = BaseAdapter.stream_pages

        def recording_stream(self_adapter, run_id, window):
            captured["resume_cursor"] = window.resume_cursor
            return original_stream_pages(self_adapter, run_id, window)

        monkeypatch.setattr(BaseAdapter, "stream_pages", recording_stream)
        Orchestrator(settings, warehouse=warehouse).run("sync")
        assert captured["resume_cursor"] == "saved-cursor-token"


class TestPipelineSafety:
    def test_dry_run_never_connects_to_warehouse(self, monkeypatch, tmp_path):
        """Dry-run must not advance or even read production checkpoints via a
        live connection: planning happens locally with no Snowflake session."""
        from papersonar.warehouse.adapter import SnowflakeAdapter

        def boom(cls, settings):
            raise AssertionError("dry-run must never connect to Snowflake")

        monkeypatch.setattr(SnowflakeAdapter, "from_settings", classmethod(boom))
        settings = settings_for(_enabled_only("openalex"))
        orchestrator = Orchestrator(settings)  # no warehouse injected
        windows = orchestrator._windows_for("openalex", "sync")
        assert windows, "dry-run planning must work without any warehouse session"
        # Planning only: nothing was fetched, nothing was written.

    def test_source_watermarks_remain_independent(self, tmp_path, monkeypatch):
        patch_build_adapters(monkeypatch, tmp_path, failing=True)
        settings = settings_for(
            {"openalex": True, "crossref": True, "arxiv": False, "datacite": False, "zenodo": False}
        )
        original_build = Orchestrator._build_adapter

        def build(self, name):
            if name == "crossref":
                adapter, _, _ = make_adapter(
                    CrossrefAdapter, source_settings("crossref"), _fixture_session("crossref", "page1.json"), tmp_path
                )
                return adapter
            return original_build(self, name)

        monkeypatch.setattr(Orchestrator, "_build_adapter", build)
        warehouse = FakeWarehouse()
        result = Orchestrator(settings, warehouse=warehouse).run("sync")
        assert result.status == "partial"
        state = StateStore(warehouse)
        year = __import__("datetime").date.today().year
        # openalex failed -> its watermark untouched
        openalex_state = state.get_sync_state("openalex", f"year:{year}")
        assert openalex_state.status == "failed"
        assert openalex_state.last_successful_watermark is None
        # crossref succeeded -> its watermark advanced independently
        today = __import__("datetime").date.today()
        crossref_source = settings.sources["crossref"]
        start = (today - __import__("datetime").timedelta(days=1)) - __import__("datetime").timedelta(
            days=crossref_source.sync_overlap_days
        )
        crossref_state = state.get_sync_state("crossref", f"indexdate:{start.isoformat()}")
        assert crossref_state is not None
        assert crossref_state.status == "succeeded"
        assert crossref_state.last_successful_watermark is not None


def _state_with_cursor(source: str, stream: str, cursor: str):
    from papersonar.warehouse.state_store import SyncState

    return SyncState(source_name=source, stream_name=stream, cursor_or_token=cursor, status="running")
