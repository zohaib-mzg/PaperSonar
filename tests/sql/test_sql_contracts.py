"""Static contract tests for the SQL implementation.

These tests do not prove Snowflake execution. They prevent drift between the
YAML contracts and the deployed SQL, and they guard the architecture rules that
can be checked without a warehouse connection.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = PROJECT_ROOT / "sql"

REQUIRED_HEADER_FIELDS = (
    "Purpose:",
    "Inputs:",
    "Outputs:",
    "Idempotent:",
    "Owner:",
    "Parameters:",
    "Cost:",
)


def _sql_files() -> list[Path]:
    return sorted(SQL_ROOT.rglob("*.sql"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_line_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def test_every_sql_file_has_required_header() -> None:
    missing: list[str] = []
    for path in _sql_files():
        header = _read(path)[:5000]
        absent = [field for field in REQUIRED_HEADER_FIELDS if field not in header]
        if absent:
            missing.append(f"{path.relative_to(PROJECT_ROOT)}: {absent}")
    assert not missing, "SQL files missing required headers:\n" + "\n".join(missing)


def test_no_inferred_schema_in_executable_sql() -> None:
    offenders: list[str] = []
    for path in _sql_files():
        executable = _strip_line_comments(_read(path))
        if re.search(r"\bINFER_SCHEMA\b", executable, flags=re.IGNORECASE):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"INFER_SCHEMA found in executable SQL: {offenders}"


def test_no_destructive_table_rebuilds() -> None:
    offenders: list[str] = []
    for path in _sql_files():
        executable = _strip_line_comments(_read(path))
        if re.search(r"\bTRUNCATE\b", executable, flags=re.IGNORECASE):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: TRUNCATE")
        if re.search(
            r"\bDROP\s+(TABLE|SCHEMA|DATABASE)\b", executable, flags=re.IGNORECASE
        ):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: DROP")
    assert not offenders, "Destructive rebuild statements found:\n" + "\n".join(offenders)


def test_taxonomy_categories_match_config() -> None:
    config = yaml.safe_load(_read(PROJECT_ROOT / "config" / "taxonomy.yml"))
    seed = _read(SQL_ROOT / "04_categorization" / "01_seed_taxonomy.sql")
    for category in config["categories"]:
        key = category["key"]
        assert f"'{key}'" in seed, f"category missing from SQL seed: {key}"
        assert category["label"] in seed, f"category label missing from SQL seed: {key}"
    seed_category_block = seed.split("MERGE INTO PAPERSONAR.PROJECT_REF.REF_CATEGORY", 1)[1]
    seeded_keys = set(re.findall(r"^\s*\('([a-z0-9-]+)',", seed_category_block, re.MULTILINE))
    config_keys = {category["key"] for category in config["categories"]}
    assert seeded_keys == config_keys, (
        f"category key drift: only-seed={sorted(seeded_keys - config_keys)}, "
        f"only-config={sorted(config_keys - seeded_keys)}"
    )


def test_taxonomy_rules_match_config() -> None:
    config = yaml.safe_load(_read(PROJECT_ROOT / "config" / "taxonomy.yml"))
    seed = _read(SQL_ROOT / "04_categorization" / "01_seed_taxonomy.sql")
    for rule in config["rules"]:
        assert rule["pattern"] in seed, f"keyword pattern missing from SQL seed: {rule['pattern']}"
        assert f"'{rule['category']}'" in seed, (
            f"rule category missing from SQL seed: {rule['category']}"
        )


def test_dq_rules_match_config_and_procedure() -> None:
    config = yaml.safe_load(_read(PROJECT_ROOT / "config" / "quality_rules.yml"))
    config_ids = {rule["id"] for rule in config["rules"]}

    seed = _read(SQL_ROOT / "08_audit_dq" / "01_dq_rules.sql")
    procedure = _read(SQL_ROOT / "08_audit_dq" / "02_run_dq.sql")

    for rule in config["rules"]:
        rule_id = rule["id"]
        assert rule_id in seed, f"DQ rule missing from seed: {rule_id}"
        assert rule_id in procedure, f"DQ rule not evaluated by SP_RUN_DQ: {rule_id}"
        match = re.search(
            r"\('" + re.escape(rule_id) + r"',\s*'.*?',\s*'(CRITICAL|WARNING|INFO)'",
            seed,
            flags=re.DOTALL,
        )
        assert match, f"could not parse severity for {rule_id}"
        assert match.group(1) == rule["severity"], (
            f"severity drift for {rule_id}: SQL={match.group(1)} config={rule['severity']}"
        )

    procedure_ids = set(re.findall(r"DQ-\d{3}", procedure))
    assert procedure_ids == config_ids, (
        f"DQ id drift: only-procedure={sorted(procedure_ids - config_ids)}, "
        f"only-config={sorted(config_ids - procedure_ids)}"
    )


def test_task_graph_order_and_finalizer() -> None:
    task_sql = _read(SQL_ROOT / "09_tasks" / "02_task_graph.sql")
    assert "TASK_ELT_ROOT" in task_sql
    assert "OVERLAP_POLICY = NO_OVERLAP" in task_sql

    stage_order = [
        "TASK_ELT_COPY",
        "TASK_ELT_BRONZE",
        "TASK_ELT_SILVER",
        "TASK_ELT_CATEGORIZE",
        "TASK_ELT_DIMENSIONS",
        "TASK_ELT_FACTS",
        "TASK_ELT_DQ",
        "TASK_ELT_PUBLISH",
    ]
    positions = [task_sql.index(name) for name in stage_order]
    assert positions == sorted(positions), "task graph stage order is not top-down"

    publish_block = task_sql.split("TASK_ELT_PUBLISH", 1)[1]
    assert "AFTER PAPERSONAR.PROJECT_AUDIT.TASK_ELT_DQ" in publish_block
    assert "FINALIZE = PAPERSONAR.PROJECT_AUDIT.TASK_ELT_ROOT" in task_sql
    assert "SP_FINALIZE_BATCH" in task_sql


def test_copy_procedure_covers_all_five_sources() -> None:
    copy_sql = _read(SQL_ROOT / "01_staging" / "02_copy_batch.sql")
    for table in (
        "STG_OPENALEX_WORK",
        "STG_CROSSREF_WORK",
        "STG_ARXIV_RECORD",
        "STG_DATACITE_DOI",
        "STG_ZENODO_RECORD",
    ):
        assert table in copy_sql, f"COPY procedure missing {table}"
    assert "FORCE = TRUE" in copy_sql


def test_manual_physical_design_is_not_default_deployed() -> None:
    demo = _read(SQL_ROOT / "07_reporting" / "02_physical_demos.sql")
    assert "-- Deploy: manual" in demo
    runner = _read(PROJECT_ROOT / "src" / "runner" / "snowflake.py")
    assert '"-- Deploy: manual" in header' in runner


def test_reporting_views_are_publication_filtered() -> None:
    views = _read(SQL_ROOT / "07_reporting" / "01_views.sql")
    assert views.count("PUBLISHED_BATCH") >= 4
    assert "WHERE EXISTS" in views
    assert "SECURE VIEW" in views
    assert "GRANT SELECT" in views


def test_author_keys_are_json_null_safe() -> None:
    """JSON null passes VARIANT IS NOT NULL but casts to SQL NULL.

    Author business keys must therefore check the cast result, not the raw
    VARIANT, or a JSON-null ORCID/id produces a NULL NOT NULL staging key.
    """
    unsafe_checks = (
        "author.value:author.orcid IS NOT NULL",
        "author.value:author.id IS NOT NULL",
        "author.value:ORCID IS NOT NULL",
        "author.value:nameIdentifiers[0].nameIdentifier IS NOT NULL",
    )
    safe_checks = (
        "NULLIF(TRIM(author.value:author.orcid::STRING), '') IS NOT NULL",
        "NULLIF(TRIM(author.value:author.id::STRING), '') IS NOT NULL",
        "NULLIF(TRIM(author.value:ORCID::STRING), '') IS NOT NULL",
        "NULLIF(TRIM(author.value:nameIdentifiers[0].nameIdentifier::STRING), '') IS NOT NULL",
    )
    for relative in (
        "05_dimensions/04_load_dimensions.sql",
        "06_facts/02_load_facts.sql",
    ):
        sql = _read(SQL_ROOT / relative)
        for unsafe in unsafe_checks:
            assert unsafe not in sql, f"{relative}: unsafe VARIANT check {unsafe!r}"
        for safe in safe_checks:
            assert safe in sql, f"{relative}: missing JSON-null-safe check {safe!r}"


def test_capped_windows_are_visible_and_do_not_advance_watermark() -> None:
    patch = _read(SQL_ROOT / "01_staging" / "00_audit_cap_columns.sql")
    assert patch.count("ADD COLUMN IS_CAPPED BOOLEAN DEFAULT FALSE;") == 2
    assert "INFORMATION_SCHEMA.COLUMNS" in patch
    assert "EXECUTE IMMEDIATE $$" in patch

    publish = _read(SQL_ROOT / "07_reporting" / "03_publish_batch.sql")
    assert "IS_CAPPED" in publish
    assert "IF (COALESCE(:is_capped, FALSE)) THEN" in publish
    assert "publish_result := 'PUBLISHED_CAPPED'" in publish
    assert "RETURN :publish_result;" in publish

    views = _read(SQL_ROOT / "07_reporting" / "01_views.sql")
    assert "PUBLISHED.IS_CAPPED" in views


def test_elt_root_has_no_snowflake_cron_schedule() -> None:
    """GitHub Actions owns scheduling; the Snowflake root is on-demand only."""
    executable = _strip_line_comments(_read(SQL_ROOT / "09_tasks" / "02_task_graph.sql"))
    assert "SCHEDULE" not in executable
    assert "USING CRON" not in executable
    assert "OVERLAP_POLICY = NO_OVERLAP" in executable


def test_dq012_counts_primary_categories_without_crosswalk_fanout() -> None:
    """DQ-012 must count primary assignments per output, not joined rows.

    SLV_OUTPUT_CROSSWALK is unique per source observation, so one canonical
    output can own several crosswalk rows in a batch. Counting the joined rows
    instead of the distinct primary assignments reports a false CRITICAL
    failure and blocks publication of an otherwise clean batch.
    """
    procedure = _read(SQL_ROOT / "08_audit_dq" / "02_run_dq.sql")
    start = procedure.index("'DQ-012'")
    block = procedure[start:]
    assert "COUNT(category.OUTPUT_BK) <> 1" not in block, (
        "DQ-012 must not count joined crosswalk rows as primary category assignments"
    )
    assert "SELECT DISTINCT OUTPUT_BK" in block, (
        "DQ-012 must deduplicate the outputs touched by the batch"
    )
    assert "PRIMARY_COUNT" in block, (
        "DQ-012 must count primary category assignments per output"
    )
    assert "COALESCE(category.PRIMARY_COUNT, 0) <> 1" in block, (
        "DQ-012 must fail when an output has zero or more than one primary category"
    )
