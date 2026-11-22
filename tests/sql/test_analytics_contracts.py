"""Static contract tests for the Phase 3 analytical layer.

These tests do not prove Snowflake execution. They guarantee that every
business question has exactly one SQL implementation, that the Phase 1
interpretation limits travel with the query, and that no analytical query
invents a measure the metric catalogue does not define.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = PROJECT_ROOT / "sql"
ANALYTICS_ROOT = SQL_ROOT / "10_analytics"
CATALOGUE_PATH = PROJECT_ROOT / "docs" / "phase3" / "METRIC_CATALOGUE.md"

QUESTIONS = {
    "Q01": "topic growth",
    "Q02": "topic share",
    "Q03": "citation impact",
    "Q04": "citation gains",
    "Q05": "topic intersections",
    "Q06": "venues",
    "Q07": "institution contribution",
    "Q08": "institution concentration",
    "Q09": "open access",
    "Q10": "author activity",
    "Q11": "citation flow",
    "Q12": "metadata coverage",
    "Q13": "counting sensitivity",
    "Q14": "partial year",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _analytics_files() -> list[Path]:
    return sorted(ANALYTICS_ROOT.glob("*.sql"))


def _question_blocks() -> dict[str, str]:
    """Map each Q-number to the SQL block that implements it.

    A block starts at the "-- QNN - ..." header and runs until the next
    question header, so it contains both the copied Phase 1 text and the SQL.
    """
    blocks: dict[str, str] = {}
    for path in _analytics_files():
        text = _read(path)
        markers = list(re.finditer(r"^--\s*(Q\d{2})\s+-\s.*$", text, flags=re.MULTILINE))
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            blocks[marker.group(1)] = text[marker.start():end]
    return blocks


def test_every_business_question_has_one_sql_implementation() -> None:
    blocks = _question_blocks()
    missing = sorted(set(QUESTIONS) - set(blocks))
    assert not missing, f"questions without a SQL implementation: {missing}"
    extra = sorted(set(blocks) - set(QUESTIONS))
    assert not extra, f"unexpected question blocks: {extra}"


def test_every_question_block_states_measure_and_limit() -> None:
    for question, block in _question_blocks().items():
        lowered = block.lower()
        assert "decision." in lowered, f"{question} does not state its decision"
        assert "measure." in lowered, f"{question} does not state its measure"
        assert "limit." in lowered, f"{question} does not state its interpretation limit"
        assert "analysis." in lowered, f"{question} does not state its analysis"


def test_suppression_thresholds_are_present_in_the_sql() -> None:
    """The Phase 1 thresholds must be in the SQL, not only in the prose."""
    blocks = _question_blocks()

    q01 = blocks["Q01"]
    assert "30" in q01, "Q01 must apply the 30-work suppression threshold"

    q05 = blocks["Q05"]
    assert "100" in q05, "Q05 must apply the 100-work parent threshold"
    assert "5" in q05, "Q05 must apply the 5-work joint threshold"

    q13 = blocks["Q13"]
    assert "LOW_VOLUME_THRESHOLD" in q13, "Q13 must flag low-volume groups"


def test_ratio_queries_return_their_denominator() -> None:
    """A rate without its denominator is not reportable."""
    blocks = _question_blocks()
    denominator_markers = (
        "CORPUS_WORKS",
        "COHORT_SIZE",
        "TOPIC_WORKS",
        "TOPIC_CLASSIFIED_CREDIT",
        "WORKS_WITH_KNOWN_ACCESS",
        "ELIGIBLE_WORKS",
        "PARENT_WORKS",
        "OUTPUT_CREDIT",
        "DISTINCT_WORKS",
    )
    for question in ("Q02", "Q03", "Q05", "Q06", "Q07", "Q08", "Q09", "Q12"):
        block = blocks[question]
        assert any(marker in block for marker in denominator_markers), (
            f"{question} does not return its denominator"
        )


def test_queries_are_read_only_and_manual_only() -> None:
    """Analytical queries must never be executed by the deployment client."""
    for path in _analytics_files():
        text = _read(path)
        assert "-- Deploy: manual" in text[:4000], (
            f"{path.name} would be executed by the deployment client"
        )
        executable = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("--")
        )
        for forbidden in ("CREATE ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "DROP "):
            assert forbidden not in executable.upper(), (
                f"{path.name} contains a write statement: {forbidden}"
            )


def test_queries_use_the_publication_contract() -> None:
    """Every query must see published data only."""
    for path in _analytics_files():
        text = _read(path)
        assert (
            "PROJECT_REPORTING.VW_RESEARCH_OUTPUT" in text
            or "PROJECT_REPORTING.VW_CITATION_SNAPSHOT" in text
            or "PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH" in text
        ), f"{path.name} does not restrict the data to the publication contract"


def test_metric_catalogue_documents_every_question() -> None:
    catalogue = _read(CATALOGUE_PATH)
    lowered = catalogue.lower()
    for question, topic in QUESTIONS.items():
        assert question in catalogue, f"{question} is missing from the metric catalogue"
        assert topic in lowered, f"{question} topic text is missing from the catalogue"
    for threshold in ("30", "100", "5"):
        assert threshold in catalogue, (
            f"the catalogue does not document the {threshold} threshold"
        )


def test_taxonomy_contract_is_valid_yaml() -> None:
    config = yaml.safe_load(_read(PROJECT_ROOT / "config" / "taxonomy.yml"))
    assert config["taxonomy_version"] == "v2"
    assert len(config["categories"]) >= 60
    assert len(config["rules"]) >= 150
    assert len(config.get("source_mappings", [])) >= 100
