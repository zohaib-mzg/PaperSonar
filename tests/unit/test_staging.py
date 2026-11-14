"""Staging validation and quarantine tests."""


from papersonar.sources.base import SourceRecord
from papersonar.staging import (
    QUARANTINE_INVALID_DATE,
    QUARANTINE_MALFORMED_IDENTIFIER,
    QUARANTINE_MISSING_SOURCE_ID,
    QUARANTINE_NEGATIVE_COUNT,
    StagingValidator,
)


def record(**overrides) -> SourceRecord:
    defaults = dict(
        source_name="crossref",
        source_record_id="10.5555/one",
        doi_raw="10.5555/one",
        title="A Study of Things",
        publication_date="2020-03-14",
        publication_year=2020,
        work_type="journal-article",
        cited_by_count=5,
    )
    defaults.update(overrides)
    return SourceRecord(**defaults)


def validate_one(**overrides):
    validator = StagingValidator(parser_version="1", schema_version="1")
    return validator.validate_batch([record(**overrides)], run_id="run-1", batch_id="b1")


class TestAccepted:
    def test_valid_record_becomes_staging_row(self):
        outcome = validate_one()
        assert outcome.records_seen == 1
        assert len(outcome.accepted) == 1
        assert not outcome.quarantined
        row = outcome.accepted[0]
        assert row.doi_normalized == "10.5555/one"
        assert row.title_normalized == "a study of things"
        assert row.validation_status == "accepted"
        assert row.payload_sha256  # deterministic content hash of parsed payload
        assert row.source_record_id == "10.5555/one"

    def test_year_only_date_accepted(self):
        outcome = validate_one(publication_date="2021", publication_year=None)
        row = outcome.accepted[0]
        assert row.publication_date == "2021"
        assert row.publication_year == 2021  # derived from date when absent

    def test_missing_title_is_not_fatal(self):
        outcome = validate_one(title=None)
        assert len(outcome.accepted) == 1
        assert outcome.accepted[0].title_normalized is None

    def test_missing_doi_is_not_fatal(self):
        outcome = validate_one(doi_raw=None)
        assert len(outcome.accepted) == 1
        assert outcome.accepted[0].doi_normalized is None

    def test_year_month_date_accepted(self):
        outcome = validate_one(publication_date="2020-03")
        assert outcome.accepted[0].publication_date == "2020-03"


class TestQuarantine:
    def test_missing_source_id(self):
        outcome = validate_one(source_record_id="  ")
        assert not outcome.accepted
        assert outcome.quarantined[0].reason_code == QUARANTINE_MISSING_SOURCE_ID

    def test_malformed_identifier(self):
        outcome = validate_one(doi_raw="not-a-doi")
        assert outcome.quarantined[0].reason_code == QUARANTINE_MALFORMED_IDENTIFIER

    def test_invalid_date(self):
        outcome = validate_one(publication_date="March 2020")
        assert outcome.quarantined[0].reason_code == QUARANTINE_INVALID_DATE

    def test_negative_count(self):
        outcome = validate_one(cited_by_count=-2)
        assert outcome.quarantined[0].reason_code == QUARANTINE_NEGATIVE_COUNT

    def test_quarantine_id_deterministic(self):
        first = validate_one(doi_raw="not-a-doi")
        second = validate_one(doi_raw="not-a-doi")
        assert first.quarantined[0].quarantine_id == second.quarantined[0].quarantine_id

    def test_mixed_batch(self):
        validator = StagingValidator()
        outcome = validator.validate_batch(
            [
                record(),
                record(source_record_id="10.5555/bad", doi_raw="garbage"),
            ],
            run_id="run-1",
            batch_id="b1",
        )
        assert len(outcome.accepted) == 1
        assert len(outcome.quarantined) == 1
        assert outcome.records_seen == 2
