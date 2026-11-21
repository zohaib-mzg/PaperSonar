"""Render sql/04_categorization/01_seed_taxonomy.sql from config/taxonomy.yml.

The taxonomy contract lives in YAML; the warehouse seed is generated from it so
that categories, keyword rules and native source mappings can never drift.
Run from the repository root:

    python scripts/generate_taxonomy_seed.py

The generated file is committed; tests/sql/test_sql_contracts.py verifies that
regenerating it produces the same bytes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "taxonomy.yml"
SEED_PATH = PROJECT_ROOT / "sql" / "04_categorization" / "01_seed_taxonomy.sql"

HEADER = """-- =============================================================================
-- Purpose: Seed the versioned taxonomy, weighted keyword rules and native
--          source taxonomy mappings that drive deterministic categorization.
--          GENERATED FILE - do not edit by hand.
--          Source of truth: config/taxonomy.yml
--          Regenerate with: python scripts/generate_taxonomy_seed.py
-- Inputs: PROJECT_REF tables.
-- Outputs: REF_CATEGORY, REF_CATEGORY_KEYWORD and REF_TAXONOMY_MAP rows.
-- Idempotent: Yes - MERGE on the natural key of each target table.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================
-- Cortex is deliberately not used. Scoring is title x3 and native taxonomy or
-- keyword topic x2. A native source taxonomy match outranks a keyword match;
-- an operator override outranks both.

MERGE INTO PAPERSONAR.PROJECT_REF.REF_CATEGORY t
USING (
  SELECT column1 AS CATEGORY_KEY, column2 AS LABEL, column3 AS PARENT_KEY
  FROM VALUES
"""

CATEGORY_MERGE_TAIL = """
) s
ON t.CATEGORY_KEY = s.CATEGORY_KEY
WHEN MATCHED THEN UPDATE SET
  t.LABEL = s.LABEL, t.PARENT_KEY = s.PARENT_KEY,
  t.IS_ACTIVE = TRUE, t.TAXONOMY_VERSION = '{version}'
WHEN NOT MATCHED THEN INSERT
  (CATEGORY_KEY, LABEL, PARENT_KEY, IS_ACTIVE, TAXONOMY_VERSION)
  VALUES (s.CATEGORY_KEY, s.LABEL, s.PARENT_KEY, TRUE, '{version}');

MERGE INTO PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD t
USING (
  SELECT column1 AS RULE_ID, column2 AS CATEGORY_KEY, column3 AS PATTERN,
         column4 AS FIELD_NAME, column5 AS BASE_WEIGHT
  FROM VALUES
"""

KEYWORD_MERGE_TAIL = """
) s
ON t.RULE_ID = s.RULE_ID
WHEN MATCHED THEN UPDATE SET
  t.CATEGORY_KEY = s.CATEGORY_KEY, t.PATTERN = s.PATTERN,
  t.FIELD_NAME = s.FIELD_NAME, t.BASE_WEIGHT = s.BASE_WEIGHT,
  t.IS_ACTIVE = TRUE, t.RULE_VERSION = '{version}'
WHEN NOT MATCHED THEN INSERT
  (RULE_ID, CATEGORY_KEY, PATTERN, FIELD_NAME, BASE_WEIGHT, IS_ACTIVE, RULE_VERSION)
  VALUES (s.RULE_ID, s.CATEGORY_KEY, s.PATTERN, s.FIELD_NAME, s.BASE_WEIGHT,
          TRUE, '{version}');

MERGE INTO PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP t
USING (
  SELECT column1 AS SOURCE_NAME, column2 AS SOURCE_VALUE, column3 AS CATEGORY_KEY
  FROM VALUES
"""

MAPPING_MERGE_TAIL = """
) s
ON t.SOURCE_NAME = s.SOURCE_NAME AND t.SOURCE_VALUE = s.SOURCE_VALUE
WHEN MATCHED THEN UPDATE SET
  t.CATEGORY_KEY = s.CATEGORY_KEY, t.MAPPING_VERSION = '{version}',
  t.IS_ACTIVE = TRUE
WHEN NOT MATCHED THEN INSERT
  (SOURCE_NAME, SOURCE_VALUE, CATEGORY_KEY, MAPPING_VERSION, IS_ACTIVE)
  VALUES (s.SOURCE_NAME, s.SOURCE_VALUE, s.CATEGORY_KEY, '{version}', TRUE);
"""


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def render(config: dict) -> str:
    version = str(config["taxonomy_version"])

    parts = [HEADER]
    for category in config["categories"]:
        parent = category.get("parent")
        parent_sql = "NULL" if parent is None else _sql_literal(parent)
        parts.append(
            "    ({key}, {label}, {parent}),\n".format(
                key=_sql_literal(category["key"]),
                label=_sql_literal(category["label"]),
                parent=parent_sql,
            )
        )
    parts.append(CATEGORY_MERGE_TAIL.format(version=version))

    for index, rule in enumerate(config["rules"], start=1):
        weight = float(rule.get("weight", 1.0))
        parts.append(
            "    ('KW-{index:03d}', {category}, {pattern}, {field}, {weight}),\n".format(
                index=index,
                category=_sql_literal(rule["category"]),
                pattern=_sql_literal(rule["pattern"]),
                field=_sql_literal(rule["field"]),
                weight=f"{weight:.2f}",
            )
        )
    parts.append(KEYWORD_MERGE_TAIL.format(version=version))

    for mapping in config.get("source_mappings", []):
        parts.append(
            "    ({source}, {value}, {category}),\n".format(
                source=_sql_literal(mapping["source"]),
                value=_sql_literal(mapping["value"]),
                category=_sql_literal(mapping["category"]),
            )
        )
    parts.append(MAPPING_MERGE_TAIL.format(version=version))
    return "".join(parts)


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    SEED_PATH.write_text(render(config), encoding="utf-8")
    print(f"wrote {SEED_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
