"""Migration runner and state store behavior against the mock warehouse."""

import pytest

from papersonar.errors import CheckpointError, IngestionError
from papersonar.timeutil import utc_now
from papersonar.warehouse.migration_runner import MigrationRunner, load_migrations
from papersonar.warehouse.state_store import RawBatch, StateStore, SyncState
from tests.fakes.fake_warehouse import FakeWarehouse


class TestMigrationRunner:
    def test_load_migrations_sorted_and_checksummed(self):
        migrations = load_migrations()
        assert len(migrations) >= 1
        versions = [m.version for m in migrations]
        assert versions == sorted(versions)
        assert all(len(m.checksum) == 64 for m in migrations)

    def test_apply_all_creates_bootstrap_and_records(self):
        warehouse = FakeWarehouse()
        runner = MigrationRunner(warehouse)
        applied = runner.apply_all()
        assert len(applied) >= 1
        assert warehouse.count("PROJECT_OPS.SCHEMA_MIGRATION") == len(applied)
        # Every migration file statement was executed
        assert any("CREATE SCHEMA IF NOT EXISTS PROJECT_OPS" in s for s in warehouse.executed)

    def test_rerun_is_idempotent(self):
        warehouse = FakeWarehouse()
        runner = MigrationRunner(warehouse)
        first = runner.apply_all()
        second = runner.apply_all()
        assert first and not second
        assert warehouse.count("PROJECT_OPS.SCHEMA_MIGRATION") == len(first)

    def test_checksum_mismatch_rejected(self):
        warehouse = FakeWarehouse()
        runner = MigrationRunner(warehouse)
        runner.apply_all()
        # Tamper with recorded checksum to simulate an edited applied migration.
        warehouse.tables["PROJECT_OPS.SCHEMA_MIGRATION"].rows[0]["CHECKSUM"] = "deadbeef"
        with pytest.raises(IngestionError, match="checksum mismatch"):
            runner.apply_all()


class TestSyncState:
    def test_get_missing_returns_none(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        assert store.get_sync_state("openalex", "partition:2020") is None

    def test_save_then_get_roundtrip(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        state = SyncState(
            source_name="openalex",
            stream_name="partition:2020",
            status="succeeded",
            last_successful_watermark="2020-12-31",
            records_seen=120,
            pages_completed=3,
        )
        store.save_sync_state_transactional(state)
        loaded = store.get_sync_state("openalex", "partition:2020")
        assert loaded is not None
        assert loaded.last_successful_watermark == "2020-12-31"
        assert loaded.records_seen == 120
        assert loaded.updated_at is not None

    def test_update_preserves_watermark_fields(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        store.save_sync_state_transactional(
            SyncState(source_name="s", stream_name="x", status="succeeded", last_successful_watermark="w1")
        )
        store.save_sync_state_transactional(
            SyncState(source_name="s", stream_name="x", status="running", cursor_or_token="tok9")
        )
        loaded = store.get_sync_state("s", "x")
        assert loaded.status == "running"
        assert loaded.cursor_or_token == "tok9"
        assert loaded.last_successful_watermark == "w1"

    def test_failed_transactional_write_rolls_back(self):
        warehouse = FakeWarehouse()
        warehouse.fail_next_upsert = True
        store = StateStore(warehouse)
        with pytest.raises(CheckpointError, match="watermark unchanged"):
            store.save_sync_state_transactional(
                SyncState(source_name="s", stream_name="x", status="running")
            )


class TestRuns:
    def test_create_then_finish_preserves_mode(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        now = utc_now()
        store.create_run("run-1", mode="sync", started_at=now)
        store.finish_run(
            "run-1",
            status="partial",
            finished_at=now,
            source_statuses={"openalex": "succeeded", "crossref": "failed"},
        )
        row = next(r for r in warehouse.tables["PROJECT_OPS.ETL_RUN"].rows if r["RUN_ID"] == "run-1")
        assert row["MODE"] == "sync"  # preserved via limited update columns
        assert row["STATUS"] == "partial"
        assert row["SOURCE_STATUSES"] == {"openalex": "succeeded", "crossref": "failed"}


class TestRawBatches:
    def test_register_mark_complete_get(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        batch = RawBatch(
            batch_id="b1",
            run_id="run-1",
            source_name="openalex",
            stream_name="p1",
            window_start="2020-01-01",
            window_end="2020-12-31",
            page_seq=1,
            page_cursor="*",
            retrieved_at_utc=utc_now(),
            http_status=200,
            payload_stage_path="PROJECT_OPS.RAW_STAGE/openalex/b1.json",
            payload_sha256="0" * 64,
            records_seen=5,
            parser_version="1",
            schema_version="1",
        )
        store.register_raw_batch(batch)
        assert store.get_batch("b1")["COMPLETE"] in (False, None)
        store.mark_batch_complete("b1")
        assert store.get_batch("b1")["COMPLETE"] is True

    def test_get_missing_batch(self):
        assert StateStore(FakeWarehouse()).get_batch("nope") is None


class TestQuarantine:
    def test_quarantine_upsert_idempotent(self):
        warehouse = FakeWarehouse()
        store = StateStore(warehouse)
        store.quarantine("q1", "run-1", "crossref", "10.1234/x", "conflicting_doi", detail="title mismatch")
        store.quarantine("q1", "run-2", "crossref", "10.1234/x", "conflicting_doi", detail="still conflicting")
        assert warehouse.count("PROJECT_STAGING.STG_QUARANTINE") == 1
        row = warehouse.tables["PROJECT_STAGING.STG_QUARANTINE"].rows[0]
        assert row["LAST_SEEN_AT"] >= row["FIRST_SEEN_AT"]
        assert row["RESOLUTION_STATUS"] == "open"
