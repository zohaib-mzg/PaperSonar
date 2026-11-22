"""Static contract tests for the Phase 3 OLAP and reporting-view layer.

These tests do not prove Snowflake execution. They guarantee that the three
OLAP aggregation techniques the course matrix asks for are present, that every
aggregate row can be told apart from a member row, and that the five named
reporting views exist as secure views that the reporter role can read.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = PROJECT_ROOT / "sql"
OLAP_PATH = SQL_ROOT / "10_analytics" / "09_rollup_cube.sql"
VIEWS_PATH = SQL_ROOT / "07_reporting" / "04_phase3_reporting_views.sql"

REQUIRED_VIEWS = (
    "VW_TOPIC_GROWTH",
    "VW_OUTPUT_COVERAGE",
    "VW_CITATION_COHORTS",
    "VW_TOPIC_INTERSECTIONS",
    "VW_RESEARCH_COMMUNITY",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def test_olap_file_uses_the_three_aggregation_techniques() -> None:
    """ROLLUP, CUBE and GROUPING SETS must all appear in the OLAP layer."""
    text = _read(OLAP_PATH)
    assert "GROUP BY ROLLUP(" in text, "the OLAP layer has no ROLLUP aggregation"
    assert "GROUP BY CUBE(" in text, "the OLAP layer has no CUBE aggregation"
    assert "GROUPING SETS (" in text, "the OLAP layer has no GROUPING SETS aggregation"


def test_olap_rows_carry_subtotal_flags() -> None:
    """An aggregate row must never be readable as a member row."""
    text = _read(OLAP_PATH)
    assert text.count("GROUPING_ID(") >= 3, "every OLAP result set must emit GROUPING_ID"
    assert "IS_SUBTOTAL" in text, "the OLAP layer must flag subtotal rows"
    assert "IS_GRAND_TOTAL" in text, "the OLAP layer must flag grand-total rows"
    assert "GROUPING(" in text, "the OLAP layer must state each grouped-out column"


def test_olap_layer_is_read_only() -> None:
    text = _read(OLAP_PATH)
    assert "-- Deploy: manual" in text[:4000], "the OLAP file must not be deployed automatically"
    executable = _strip_line_comments(text).upper()
    for forbidden in ("CREATE ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "DROP "):
        assert forbidden not in executable, f"the OLAP file contains a write statement: {forbidden}"


def test_the_five_reporting_views_are_defined_as_secure_views() -> None:
    text = _read(VIEWS_PATH)
    for view in REQUIRED_VIEWS:
        pattern = rf"CREATE OR REPLACE SECURE VIEW PAPERSONAR\.PROJECT_REPORTING\.{view}\b"
        assert re.search(pattern, text), f"{view} is not defined as a secure view"


def test_the_five_reporting_views_are_granted_to_the_reporter() -> None:
    text = _read(VIEWS_PATH)
    for view in REQUIRED_VIEWS:
        assert (
            f"GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.{view}\n  TO ROLE PAPERSONAR_REPORTER;"
            in text
        ), f"{view} is not granted to PAPERSONAR_REPORTER"


def test_reporting_views_enforce_the_publication_contract() -> None:
    """No reporting view may expose an unpublished batch."""
    text = _read(VIEWS_PATH)
    assert text.count("PROJECT_AUDIT.PUBLISHED_BATCH") >= 2, (
        "the reporting views must filter on the publication registry"
    )
    assert "VW_RESEARCH_OUTPUT" in text, "the reporting views must read the published output view"


def test_reporting_views_state_their_denominators() -> None:
    """A ratio without its denominator is not reportable."""
    text = _read(VIEWS_PATH)
    for marker in ("CORPUS_WORKS", "CLASSIFIED_WORKS", "PARENT_WORKS", "OUTPUTS"):
        assert marker in text, f"the reporting views do not expose {marker}"
