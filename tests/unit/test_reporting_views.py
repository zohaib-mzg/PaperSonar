"""Static consistency guard for reporting views (migration 003).

The mock warehouse logs CREATE VIEW statements without evaluating them, so a
view referencing a column that does not exist only fails on real Snowflake —
which happened live (`invalid identifier 'OA_STATUS'` in
VW_PUBLICATION_BY_SOURCE). This test parses the table/column declarations from
migrations 001–002 and validates every view in migration 003 against them:

- every FROM/JOIN target must be a declared table;
- every column reference must exist on a table the view queries (or be a
  view-local alias).
"""

from __future__ import annotations

import re

from papersonar.warehouse.migration_runner import load_migrations

_TYPES = r"STRING|NUMBER|BOOLEAN|FLOAT|VARIANT|ARRAY|DATE|TIMESTAMP_TZ"
_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS ([A-Za-z0-9_.]+)\s*\(", re.I)
_COLUMN_RE = re.compile(rf"^\s*([A-Z][A-Z0-9_]+)\s+({_TYPES})\b", re.M)
_VIEW_RE = re.compile(
    r"CREATE VIEW IF NOT EXISTS ([A-Za-z0-9_.]+)\s+AS\s+(.*?);", re.S | re.I
)
_FROM_JOIN_RE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Z][A-Z0-9_.]*)", re.I)
_IDENT_RE = re.compile(r"\b([A-Z_][A-Z0-9_]*)\b")

_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "AS",
    "ON", "AND", "OR", "NOT", "IS", "NULL", "LEFT", "RIGHT", "INNER", "OUTER",
    "JOIN", "CASE", "WHEN", "THEN", "ELSE", "END", "IN", "OVER", "PARTITION",
    "DESC", "ASC", "WITHIN", "DISTINCT", "TRUE", "FALSE", "USING",
    "CURRENT_TIMESTAMP", "CURRENT_DATE",
}

_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "COALESCE", "IFF",
    "DATEDIFF", "ROW_NUMBER", "LISTAGG", "TO_NUMBER", "TO_CHAR", "NVL",
}


def _declared_tables() -> dict[str, set[str]]:
    """Map qualified table name -> declared column set from migrations 001+002."""
    tables: dict[str, set[str]] = {}
    for migration in load_migrations():
        if migration.version not in ("001", "002"):
            continue
        for match in _TABLE_RE.finditer(migration.sql):
            start = match.end()
            depth = 1
            i = start
            while i < len(migration.sql) and depth:
                if migration.sql[i] == "(":
                    depth += 1
                elif migration.sql[i] == ")":
                    depth -= 1
                i += 1
            body = migration.sql[start : i - 1]
            columns = {name for name, _ in _COLUMN_RE.findall(body)}
            tables[match.group(1).upper()] = columns
    return tables


def _view_bodies() -> list[tuple[str, str]]:
    for migration in load_migrations():
        if migration.version == "003":
            return [(name.upper(), body.upper()) for name, body in _VIEW_RE.findall(migration.sql)]
    return []


class TestReportingViewConsistency:
    def test_views_exist_in_migration_003(self):
        views = _view_bodies()
        assert len(views) >= 8

    def test_view_tables_are_declared(self):
        tables = _declared_tables()
        assert tables, "no declared tables parsed from migrations 001/002"
        for view_name, body in _view_bodies():
            for table in _FROM_JOIN_RE.findall(body):
                table_name = table.rstrip(",").upper()
                assert table_name in tables, (
                    f"{view_name} references undeclared table {table_name}"
                )

    def test_view_columns_exist_on_referenced_tables(self):
        tables = _declared_tables()
        failures: list[str] = []
        for view_name, body in _view_bodies():
            referenced: dict[str, set[str]] = {}
            aliases: set[str] = set()
            spans: list[tuple[int, int]] = []
            for match in _FROM_JOIN_RE.finditer(body):
                table_name = match.group(1).rstrip(",").upper()
                referenced[table_name] = tables.get(table_name, set())
                spans.append((match.start(1), match.end(1)))
                # Correlation alias: the token right after the table name
                tail = body[match.end() : match.end() + 16]
                alias_match = re.match(r"\s+([A-Z][A-Z0-9_]*)\b", tail)
                if alias_match and alias_match.group(1) not in {
                    "LEFT", "JOIN", "ON", "WHERE", "GROUP", "ORDER", "AS", "INNER", "RIGHT"
                }:
                    aliases.add(alias_match.group(1))
            # Mask qualified table names so their segments are not mistaken
            # for column references (PROJECT_DW.FACT_PUBLICATION ...).
            masked = list(body)
            for start, end in spans:
                for i in range(start, end):
                    masked[i] = " "
            masked_body = "".join(masked)
            available: set[str] = set()
            for columns in referenced.values():
                available |= columns
            # View-local select aliases
            for alias in re.findall(r"\bAS\s+([A-Z_][A-Z0-9_]*)\b", masked_body):
                aliases.add(alias)
            for match in _IDENT_RE.finditer(masked_body):
                token = match.group(1)
                if token in _KEYWORDS or token in _FUNCTIONS or token in aliases:
                    continue
                if match.end() < len(masked_body) and masked_body[match.end()] == "(":
                    continue  # function invocation
                if match.start() > 0 and masked_body[match.start() - 1] == ".":
                    if token not in available:
                        failures.append(f"{view_name}: column {token} not in referenced tables")
                # table-alias prefixes (X. in X.COL) are skipped via the alias set
        assert not failures, "\n".join(failures)

    def test_regressed_case_oa_status_not_on_fact_publication(self):
        """The original live failure: OA_STATUS belongs to DIM_WORK, not FACT_PUBLICATION."""
        tables = _declared_tables()
        assert "OA_STATUS" not in tables.get("PROJECT_DW.FACT_PUBLICATION", set())
        assert "OA_STATUS" in tables.get("PROJECT_DW.DIM_WORK", set())
