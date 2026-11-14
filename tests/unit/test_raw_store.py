"""Raw persistence tests: durability, checksums, redaction, replay."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from papersonar.raw_store import RawStore, scrub_request_descriptor
from papersonar.warehouse.state_store import StateStore
from tests.fakes.fake_warehouse import FakeWarehouse


def make_store(tmp_path):
    warehouse = FakeWarehouse()
    store = RawStore(
        warehouse=warehouse,
        state_store=StateStore(warehouse),
        raw_dir=tmp_path / "raw",
        schema_version="1",
    )
    return warehouse, store


def persist(warehouse, store, **overrides):
    kwargs = dict(
        run_id="run-1",
        source_name="openalex",
        stream_name="partition:2020",
        window_start="2020-01-01",
        window_end="2020-12-31",
        page_seq=1,
        page_cursor="*",
        retrieved_at_utc=datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC),
        http_status=200,
        payload_bytes=b'{"results": [1, 2, 3]}',
        records_seen=3,
        request_descriptor={"url": "https://api.openalex.org/works", "filter": "topics.id:T10743"},
    )
    kwargs.update(overrides)
    return store.persist_batch(**kwargs)


class TestPersistBatch:
    def test_payload_durably_stored_with_checksum(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        result = persist(warehouse, store)
        expected = hashlib.sha256(b'{"results": [1, 2, 3]}').hexdigest()
        assert result.payload_sha256 == expected
        # Local mirror exists with exact bytes
        assert result.local_payload_path.read_bytes() == b'{"results": [1, 2, 3]}'
        # Durable warehouse stage copy exists with same bytes
        assert warehouse.stage[result.payload_stage_path] == b'{"results": [1, 2, 3]}'
        # Registry row with checksum
        batch = store._state.get_batch(result.batch_id)
        assert batch["PAYLOAD_SHA256"] == expected
        assert batch["COMPLETE"] is False

    def test_manifest_contains_required_fields(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        result = persist(warehouse, store)
        manifest = json.loads(result.local_manifest_path.read_text(encoding="utf-8"))
        for key in (
            "run_id",
            "source_name",
            "batch_id",
            "retrieved_at_utc",
            "request_descriptor_redacted",
            "http_status",
            "page_or_token_sequence",
            "payload_stage_path",
            "payload_sha256",
            "records_seen",
            "parser_version",
            "schema_version",
            "window_start",
            "window_end",
            "complete",
        ):
            assert key in manifest
        assert manifest["retrieved_at_utc"] == "2026-11-14T12:00:00Z"
        assert manifest["complete"] is False

    def test_refetch_creates_new_batch_not_overwrite(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        first = persist(warehouse, store)
        second = persist(warehouse, store)
        assert first.batch_id != second.batch_id
        assert warehouse.count("PROJECT_OPS.RAW_BATCH") == 2

    def test_empty_payload_rejected(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            persist(warehouse, store, payload_bytes=b"")

    def test_request_descriptor_secrets_redacted(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        result = persist(
            warehouse,
            store,
            request_descriptor={
                "url": "https://api.example.org/works",
                "api_key": "sk-abc123",
                "api-key": "sk-abc123",
                "nested": {"Authorization": "Bearer xyz", "filter": "x"},
                "api_key_values": {"a": 1},
            },
        )
        manifest = json.loads(result.local_manifest_path.read_text(encoding="utf-8"))
        descriptor = manifest["request_descriptor_redacted"]
        assert descriptor["api_key"] == "***REDACTED***"
        assert descriptor["api-key"] == "***REDACTED***"
        assert descriptor["nested"]["Authorization"] == "***REDACTED***"
        assert descriptor["nested"]["filter"] == "x"
        assert descriptor["url"] == "https://api.example.org/works"
        # Fail-safe: any key containing a secret-like fragment is redacted entirely.
        assert descriptor["api_key_values"] == "***REDACTED***"

    def test_mark_complete(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        result = persist(warehouse, store)
        assert store._state.get_batch(result.batch_id)["COMPLETE"] is False
        store.mark_complete(result.batch_id)
        assert store._state.get_batch(result.batch_id)["COMPLETE"] is True


class TestReplay:
    def test_load_payload_roundtrip(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        result = persist(warehouse, store)
        target_dir = tmp_path / "replay"
        downloaded = store.load_payload(result.batch_id, target_dir)
        assert downloaded.read_bytes() == b'{"results": [1, 2, 3]}'

    def test_load_unknown_batch_raises(self, tmp_path):
        warehouse, store = make_store(tmp_path)
        with pytest.raises(ValueError, match="Unknown raw batch"):
            store.load_payload("nope", tmp_path / "replay")


class TestScrub:
    def test_deep_scrub(self):
        out = scrub_request_descriptor(
            {"a": 1, "private_key": "PEM", "list": [{"password": "p"}, {"ok": 2}]}
        )
        assert out == {"a": 1, "private_key": "***REDACTED***", "list": [{"password": "***REDACTED***"}, {"ok": 2}]}

    def test_no_secrets_untouched(self):
        desc = {"url": "https://x", "cursor": "*"}
        assert scrub_request_descriptor(desc) == desc
