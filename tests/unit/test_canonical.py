"""Canonical identity resolution tests (mock warehouse)."""

from papersonar.canonical import CanonicalResolver
from papersonar.sources.base import SourceRecord
from papersonar.staging import QUARANTINE_CONFLICTING_DOI, StagingValidator
from tests.fakes.fake_warehouse import FakeWarehouse


def make_row(source: str, record_id: str, doi: str | None, title: str, **overrides):
    record = SourceRecord(
        source_name=source,
        source_record_id=record_id,
        doi_raw=doi,
        title=title,
        cited_by_count=overrides.pop("cited_by_count", None),
        **overrides,
    )
    validator = StagingValidator()
    outcome = validator.validate_batch([record], run_id="run-1", batch_id="b1")
    assert not outcome.quarantined
    return outcome.accepted[0]


def resolve(warehouse: FakeWarehouse, rows):
    resolver = CanonicalResolver(warehouse)
    return resolver, resolver.resolve_batch(rows, run_id="run-1")


def resolve_and_persist(warehouse: FakeWarehouse, rows):
    """Resolve then write through the loader (canonical + crosswalk)."""
    resolver = CanonicalResolver(warehouse)
    outcome = resolver.resolve_batch(rows, run_id="run-1")
    from papersonar.warehouse.loaders import WarehouseLoader

    WarehouseLoader(warehouse).load_canonical(outcome)
    return resolver, outcome


class TestWorkKeyAssignment:
    def test_doi_key(self):
        warehouse = FakeWarehouse()
        resolver = CanonicalResolver(warehouse)
        row = make_row("crossref", "10.5555/one", "10.5555/One", "T")
        assert resolver.work_key_for(row) == "doi:10.5555/one"

    def test_source_fallback_key(self):
        warehouse = FakeWarehouse()
        resolver = CanonicalResolver(warehouse)
        row = make_row("arxiv", "2401.00001", None, "T")
        assert resolver.work_key_for(row) == "src:arxiv:2401.00001"


class TestResolution:
    def test_same_doi_two_sources_merge(self):
        warehouse = FakeWarehouse()
        rows = [
            make_row("crossref", "10.5555/one", "10.5555/one", "A study of things", cited_by_count=7),
            make_row("openalex", "W1", "10.5555/one", "A Study of Things"),
        ]
        resolver, outcome = resolve(warehouse, rows)
        assert outcome.works_resolved == 1
        assert outcome.conflicts == 0
        assert len(outcome.canonical_rows) == 1
        canonical = outcome.canonical_rows[0]
        assert canonical["WORK_KEY"] == "doi:10.5555/one"
        assert canonical["SOURCE_PRIORITY"] == "openalex"  # higher priority wins
        assert canonical["CITED_BY_COUNT"] == 7  # filled from lower priority
        assert canonical["TITLE"] == "A Study of Things"
        assert len(outcome.crosswalk_rows) == 2

    def test_fill_only_missing_no_null_overwrite(self):
        warehouse = FakeWarehouse()
        rich = make_row("crossref", "10.5555/x", "10.5555/x", "Rich title", cited_by_count=3)
        sparse = make_row("openalex", "W9", "10.5555/x", None)  # no title
        resolver, outcome = resolve(warehouse, [rich, sparse])
        canonical = outcome.canonical_rows[0]
        assert canonical["TITLE"] == "Rich title"  # filled by lower priority, not wiped
        assert canonical["SOURCE_PRIORITY"] == "openalex"

    def test_higher_priority_updates_existing_non_null(self):
        warehouse = FakeWarehouse()
        # Existing canonical from crossref
        _, first = resolve(warehouse, [make_row("crossref", "10.5555/x", "10.5555/x", "Old title", cited_by_count=1)])
        assert first.works_resolved == 1
        # OpenAlex (higher priority) supplies a different, valid title
        _, second = resolve(
            warehouse, [make_row("openalex", "W1", "10.5555/x", "Newer richer title", cited_by_count=9)]
        )
        assert second.conflicts == 0
        canonical = second.canonical_rows[0]
        assert canonical["TITLE"] == "Newer richer title"
        assert canonical["CITED_BY_COUNT"] == 9

    def test_conflicting_title_quarantined(self):
        warehouse = FakeWarehouse()
        _, first = resolve_and_persist(warehouse, [make_row("crossref", "10.5555/x", "10.5555/x", "A study of things")])
        assert first.works_resolved == 1
        # Same DOI, materially different title -> quarantine, not merge
        _, second = resolve_and_persist(
            warehouse, [make_row("datacite", "dc-1", "10.5555/x", "Completely different work")]
        )
        assert second.works_resolved == 0
        assert second.conflicts == 1
        assert second.quarantine_entries[0].reason_code == QUARANTINE_CONFLICTING_DOI
        assert not second.resolved_rows
        # Stored canonical unchanged
        stored = CanonicalResolver(warehouse)._get_dim_work("doi:10.5555/x")
        assert stored["TITLE"] == "A study of things"

    def test_crosswalk_change_quarantined(self):
        warehouse = FakeWarehouse()
        _, first = resolve_and_persist(
            warehouse, [make_row("crossref", "10.5555/x", "10.5555/x", "Original title")]
        )
        assert first.works_resolved == 1
        # Same source record now carries a different DOI -> quarantined for
        # review; the stored crosswalk mapping is preserved, not re-pointed.
        _, second = resolve_and_persist(
            warehouse, [make_row("crossref", "10.5555/x", "10.5555/renamed", "Original title")]
        )
        assert second.works_resolved == 0
        assert second.conflicts == 1
        reasons = {entry.reason_code for entry in second.quarantine_entries}
        assert "doi_change_review" in reasons
        stored = CanonicalResolver(warehouse)._get_crosswalk("crossref", "10.5555/x")
        assert stored["WORK_KEY"] == "doi:10.5555/x"

    def test_doi_lookup_after_resolve(self):
        warehouse = FakeWarehouse()
        resolve_and_persist(warehouse, [make_row("crossref", "10.5555/x", "10.5555/x", "Title")])
        resolver = CanonicalResolver(warehouse)
        assert resolver.lookup_work_key_by_doi("10.5555/x") == "doi:10.5555/x"
        assert resolver.lookup_work_key_by_doi("10.5555/none") is None

    def test_same_record_two_versions_one_batch_is_deterministic(self):
        """Hardening §4.3: multiple staged content versions of one record in a
        single batch must never produce ambiguous updates."""
        def build_rows():
            return [
                make_row("crossref", "10.5555/x", "10.5555/x", "Title", cited_by_count=1),
                make_row("crossref", "10.5555/x", "10.5555/x", "Title", cited_by_count=2),
            ]

        first = CanonicalResolver(FakeWarehouse()).resolve_batch(build_rows(), run_id="r1")
        second = CanonicalResolver(FakeWarehouse()).resolve_batch(build_rows(), run_id="r2")
        assert first.works_resolved == 1
        assert len(first.canonical_rows) == 1
        # Deterministic tiebreak: identical inputs -> identical canonical value
        assert first.canonical_rows[0]["CITED_BY_COUNT"] == second.canonical_rows[0]["CITED_BY_COUNT"]
