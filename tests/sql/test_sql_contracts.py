"""Static contract tests for the SQL implementation.

These tests do not prove Snowflake execution. They prevent drift between the
YAML contracts and the deployed SQL, and they guard the architecture rules that
can be checked without a warehouse connection.
"""

from __future__ import annotations

import re
import sys
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


def test_oversize_source_text_columns_are_wide_enough() -> None:
    """DataCite overflows narrow columns and aborts the whole batch.

    A multi-valued publication date or a long subject string used to raise
    "String ... is too long and would be truncated", which failed the batch at
    the silver or dimensions stage and blocked publication.
    """
    silver = _read(SQL_ROOT / "03_silver" / "01_slv_tables.sql")
    assert "PUBLICATION_DATE_RAW  VARCHAR(4000)" in silver

    transform = _read(SQL_ROOT / "03_silver" / "02_transform_batch.sql")
    assert "LEFT(b.PAYLOAD:publication_date::STRING, 4000)" in transform

    dimensions = _read(SQL_ROOT / "05_dimensions" / "04_load_dimensions.sql")
    assert "TOPIC_NAME   VARCHAR(4000)" in dimensions
    assert "), 4000) AS TOPIC_NAME" in dimensions

    topic_dimension = _read(SQL_ROOT / "05_dimensions" / "03_dim_topic_category.sql")
    assert "TOPIC_NAME  VARCHAR(4000)" in topic_dimension

    widen = _read(SQL_ROOT / "03_silver" / "04_widen_oversize_text.sql")
    assert "PUBLICATION_DATE_RAW SET DATA TYPE VARCHAR(4000)" in widen
    assert "TOPIC_NAME SET DATA TYPE VARCHAR(4000)" in widen


def test_no_trailing_comma_before_closing_parenthesis() -> None:
    """A trailing comma before ")" is a Snowflake syntax error.

    The generated taxonomy seed shipped with one and the deployment failed at
    compile time ("syntax error unexpected ')'"). The pattern is cheap to
    detect statically, so it is guarded for every SQL file.
    """
    offenders: list[str] = []
    for path in _sql_files():
        lines = _read(path).splitlines()
        for index, line in enumerate(lines):
            if not line.strip().startswith(")"):
                continue
            previous = index - 1
            while previous >= 0 and not lines[previous].strip():
                previous -= 1
            if previous >= 0 and lines[previous].rstrip().endswith(","):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{index + 1}")
    assert not offenders, "trailing comma before closing parenthesis:\n" + "\n".join(offenders)


def test_values_rows_are_comma_separated_without_a_trailing_comma() -> None:
    """A FROM VALUES list must separate its rows with commas.

    Both mistakes below break the deployment at compile time with
    "syntax error unexpected '('" / "unexpected ')'":

        FROM VALUES
            ('a', 'b')      <- missing separator
            ('c', 'd')

        FROM VALUES
            ('a', 'b'),
            ('c', 'd'),     <- trailing comma
    """
    offenders: list[str] = []
    for path in _sql_files():
        lines = _read(path).splitlines()
        in_values = False
        rows: list[tuple[int, str]] = []
        index = 0
        while index < len(lines):
            stripped = lines[index].strip()
            if stripped.startswith("--"):
                index += 1
                continue
            if not in_values:
                if re.search(r"\bFROM\s+VALUES\b", stripped, flags=re.IGNORECASE):
                    in_values = True
                    rows = []
                index += 1
                continue
            if stripped.startswith("("):
                start = index
                row_text = stripped
                depth = row_text.count("(") - row_text.count(")")
                while depth > 0 and index + 1 < len(lines):
                    index += 1
                    row_text += " " + lines[index].strip()
                    depth += lines[index].count("(") - lines[index].count(")")
                rows.append((start, row_text))
                index += 1
                continue
            if stripped.startswith(")"):
                for row_index, row in rows[:-1]:
                    if not row.endswith(","):
                        offenders.append(
                            f"{path.relative_to(PROJECT_ROOT)}:{row_index + 1} missing separator"
                        )
                if rows and rows[-1][1].endswith(","):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{rows[-1][0] + 1} trailing comma"
                    )
                in_values = False
                rows = []
            index += 1
    assert not offenders, "invalid VALUES row lists:\n" + "\n".join(offenders)


def _taxonomy_config() -> dict:
    return yaml.safe_load(_read(PROJECT_ROOT / "config" / "taxonomy.yml"))


def test_taxonomy_seed_is_reproducible_from_the_config() -> None:
    """The deployed seed is generated from config/taxonomy.yml.

    A hand-edited seed would silently drift from the contract, so regenerating
    it must reproduce the committed file byte for byte.
    """
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import generate_taxonomy_seed
    finally:
        sys.path.pop(0)

    expected = generate_taxonomy_seed.render(_taxonomy_config())
    actual = _read(SQL_ROOT / "04_categorization" / "01_seed_taxonomy.sql")
    assert actual == expected, (
        "sql/04_categorization/01_seed_taxonomy.sql is stale; "
        "run python scripts/generate_taxonomy_seed.py"
    )


def test_taxonomy_source_mappings_match_config() -> None:
    """Every native source taxonomy mapping in the contract is seeded."""
    config = _taxonomy_config()
    seed = _read(SQL_ROOT / "04_categorization" / "01_seed_taxonomy.sql")
    category_keys = {category["key"] for category in config["categories"]}

    for mapping in config.get("source_mappings", []):
        assert mapping["source"] in seed, (
            f"mapping source missing from SQL seed: {mapping['source']}"
        )
        assert mapping["value"] in seed, (
            f"mapping value missing from SQL seed: {mapping['value']}"
        )
        assert mapping["category"] in category_keys, (
            f"mapping points at an unknown category: {mapping['category']}"
        )

    assert "MERGE INTO PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP" in seed, (
        "the taxonomy seed must populate REF_TAXONOMY_MAP"
    )


def test_every_taxonomy_category_is_reachable() -> None:
    """Each category except the unclassified default needs a way to be assigned."""
    config = _taxonomy_config()
    category_keys = {category["key"] for category in config["categories"]}
    reachable = {rule["category"] for rule in config["rules"]}
    reachable |= {
        mapping["category"] for mapping in config.get("source_mappings", [])
    }
    unreachable = category_keys - reachable - {"unclassified"}
    assert not unreachable, f"categories without any rule or mapping: {sorted(unreachable)}"


def test_categorization_ranks_native_taxonomy_above_keywords() -> None:
    """Native source taxonomy values are curated and must outrank keyword hits."""
    procedure = _read(SQL_ROOT / "04_categorization" / "02_categorize_batch.sql")
    assert "PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP" in procedure, (
        "the categorization procedure must read the native taxonomy map"
    )
    assert "'SOURCE_TAXONOMY'" in procedure, (
        "the categorization procedure must record the source taxonomy method"
    )
    assert "'SOURCE_TAXONOMY', 1" in procedure, (
        "native taxonomy matches must outrank keyword matches"
    )
    assert "'KEYWORD', 2" in procedure, (
        "keyword matches must rank below native taxonomy matches"
    )
    assert "LENGTH(k.PATTERN) <= 4 AND CONTAINS(' ' || tt.NORMALIZED_TOKEN || ' '" in procedure, (
        "short keyword patterns must match on token boundaries"
    )
    assert "CONTAINS(s.TITLE_NORMALIZED, k.PATTERN)" not in procedure, (
        "title patterns must not match inside a longer word"
    )
    assert "CONTAINS(tt.TOKEN, k.PATTERN)" not in procedure, (
        "keyword patterns must not match inside a longer word"
    )
    assert "t.value:display_name::STRING" in procedure, (
        "the native taxonomy topic name must be read as a structured value"
    )
    assert "t.value:subfield:display_name::STRING" in procedure, (
        "the native taxonomy subfield must be read as a structured value"
    )
    assert "MAX(m.BASE_WEIGHT * 2 + tt.LEVEL)" in procedure, (
        "the most specific native taxonomy value must win"
    )


def test_taxonomy_patterns_are_whole_words_or_phrases() -> None:
    """Patterns must be normalized words or phrases.

    The categorization procedure matches on word boundaries, so a pattern with
    punctuation or an empty word would never fire or would match unpredictably.
    """
    config = _taxonomy_config()
    for rule in config["rules"]:
        pattern = rule["pattern"].strip().lower()
        assert pattern, "a taxonomy rule must carry a pattern"
        for word in pattern.split():
            assert re.fullmatch(r"[a-z0-9]+", word), (
                f"pattern {pattern!r} is not a normalized word or phrase"
            )


def test_taxonomy_seed_deactivates_superseded_rows() -> None:
    """A new taxonomy version must retire the rules it replaced.

    The seed MERGEs by surrogate key, so rows that exist only in the previous
    contract would stay active and keep firing. The seed therefore deactivates
    every row whose version is not the current one.
    """
    config = _taxonomy_config()
    seed = _read(SQL_ROOT / "04_categorization" / "01_seed_taxonomy.sql")
    version = config["taxonomy_version"]
    assert (
        "UPDATE PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD\n"
        "SET IS_ACTIVE = FALSE\n"
        f"WHERE RULE_VERSION IS DISTINCT FROM '{version}';"
    ) in seed
    assert (
        "UPDATE PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP\n"
        "SET IS_ACTIVE = FALSE\n"
        f"WHERE MAPPING_VERSION IS DISTINCT FROM '{version}';"
    ) in seed
    assert (
        "UPDATE PAPERSONAR.PROJECT_REF.REF_CATEGORY\n"
        "SET IS_ACTIVE = FALSE\n"
        f"WHERE TAXONOMY_VERSION IS DISTINCT FROM '{version}';"
    ) in seed


def test_boundary_matching_separates_lookalike_words() -> None:
    """The matching semantics must keep lookalike words apart.

    The v2 taxonomy matched substrings, so "cultural" fired on "agricultural
    and biological sciences" and "art" fired on "plant science". The v3
    contract matches on word boundaries, and this test pins that behaviour.
    """
    config = _taxonomy_config()
    patterns = {
        (rule["field"], rule["pattern"].lower()): rule["category"]
        for rule in config["rules"]
    }

    def matches(field: str, text: str, pattern: str) -> bool:
        padded = f" {text} "
        needle = f" {pattern}"
        if len(pattern) <= 4:
            return f"{pattern} " in padded
        return needle in padded

    assert ("keywords", "cultural") in patterns
    assert not matches("keywords", "agricultural and biological sciences", "cultural")
    assert ("keywords", "arts") in patterns
    assert not matches("keywords", "plant science", "arts")
    assert matches("keywords", "plant ecology studies", "plant ecology")
    assert matches("keywords", "deep machine learning models", "machine learning")
    assert matches("keywords", "storage systems", "storage")
    assert not matches("keywords", "storage systems", "rag")
    assert matches("title", "a study of machine learning systems", "machine learning")
    assert not matches("title", "a study of storage systems", "rag")


def test_taxonomy_contract_covers_the_research_domains() -> None:
    """The taxonomy must not be a software-engineering-only spine any more.

    Phase 2 measured 4-6% categorization coverage because every rule targeted
    software engineering or AI, while the corpus is general scholarship. The
    v2 contract must therefore contain the broad domains and must keep the
    software-engineering spine for the course's own focus area.
    """
    config = _taxonomy_config()
    category_keys = {category["key"] for category in config["categories"]}
    required = {
        "computer-science",
        "health-sciences",
        "life-sciences",
        "natural-sciences",
        "earth-and-environment",
        "engineering-and-technology",
        "social-sciences",
        "humanities",
        "arts-and-culture",
        "software-engineering",
        "ai-ml",
        "unclassified",
    }
    assert required <= category_keys, (
        f"missing broad domains: {sorted(required - category_keys)}"
    )

    keyword_patterns = {
        rule["pattern"] for rule in config["rules"] if rule["field"] == "keywords"
    }
    assert len(keyword_patterns) >= 100, (
        "the native taxonomy rules are too thin to lift DQ-009 coverage"
    )

    sources = {
        mapping["source"] for mapping in config.get("source_mappings", [])
    }
    assert "ARXIV" in sources, "arXiv category codes must be mapped explicitly"
    assert "DATACITE" in sources, "DataCite subjects must be mapped explicitly"
