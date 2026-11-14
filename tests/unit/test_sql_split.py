"""SQL statement splitting tests.

Regression for a live Snowflake failure: the previous naive ``split(";")``
produced comment-only statements (Snowflake error ``000900 (42601): Empty SQL
statement``) and split statements inside string literals containing ``;``.
"""

from __future__ import annotations

from papersonar.warehouse.migration_runner import load_migrations
from papersonar.warehouse.sqlsplit import split_sql_statements


def test_semicolon_inside_string_literal_stays_one_statement():
    sql = "CREATE TABLE t (c STRING) COMMENT = 'Never silently discarded; reason codes';"
    statements = split_sql_statements(sql)
    assert statements == ["CREATE TABLE t (c STRING) COMMENT = 'Never silently discarded; reason codes'"]


def test_semicolon_inside_line_comment_is_not_a_splitter():
    sql = "SELECT 1 -- note; with semicolon\nFROM dual;"
    statements = split_sql_statements(sql)
    assert len(statements) == 1
    assert statements[0].startswith("SELECT 1")
    assert "FROM dual" in statements[0]


def test_semicolon_inside_block_comment_is_not_a_splitter():
    sql = "/* header; still comment */ SELECT 1;"
    statements = split_sql_statements(sql)
    assert len(statements) == 1
    assert "SELECT 1" in statements[0]


def test_comment_only_trailing_chunk_dropped():
    sql = "SELECT 1;\n\n-- trailing note about the script\n"
    assert split_sql_statements(sql) == ["SELECT 1"]


def test_comment_only_chunk_between_statements_dropped():
    sql = "SELECT 1;\n\n-- section header\n-- more notes\n\nSELECT 2;"
    statements = split_sql_statements(sql)
    assert len(statements) == 2
    assert statements[0] == "SELECT 1"
    # Leading comments may be kept in the statement text (valid SQL for
    # Snowflake); the point is the statement has content and is not empty.
    assert statements[1].endswith("SELECT 2")


def test_empty_script_yields_nothing():
    assert split_sql_statements("") == []
    assert split_sql_statements(";;;\n   \n-- only comments\n") == []


def test_final_statement_without_semicolon_kept():
    sql = "CREATE SCHEMA IF NOT EXISTS ops;\nCREATE TABLE ops.t (c NUMBER)\n"
    assert split_sql_statements(sql) == [
        "CREATE SCHEMA IF NOT EXISTS ops",
        "CREATE TABLE ops.t (c NUMBER)",
    ]


def test_escaped_quote_in_string():
    sql = "INSERT INTO t VALUES ('it''s; tricky');"
    assert split_sql_statements(sql) == ["INSERT INTO t VALUES ('it''s; tricky')"]


def test_semicolon_inside_quoted_identifier():
    sql = 'CREATE TABLE "my;table" (c NUMBER);'
    assert split_sql_statements(sql) == ['CREATE TABLE "my;table" (c NUMBER)']


def test_dollar_quoted_constant_with_semicolon():
    sql = "CREATE FUNCTION f() RETURNS STRING AS $$body; with; semicolons$$;"
    statements = split_sql_statements(sql)
    assert len(statements) == 1
    assert statements[0].count(";") == 2  # the two inside the $$ body


class TestRealMigrationFiles:
    """The actual shipped migration files must split into valid statements."""

    def test_every_statement_has_content(self):
        for migration in load_migrations():
            statements = split_sql_statements(migration.sql)
            assert statements, f"migration {migration.version} produced no statements"
            for statement in statements:
                assert statement.strip(), (
                    f"migration {migration.version} produced an empty statement"
                )

    def test_comment_string_with_semicolon_survives(self):
        statements = split_sql_statements(load_migrations()[0].sql)
        quarantined = [
            s for s in statements
            if "STG_QUARANTINE" in s and "COMMENT" in s
        ]
        assert quarantined, "quarantine table statement not found"
        assert "Never silently discarded; reason codes are queryable" in quarantined[0]

    def test_dim_work_comment_string_with_semicolon_survives(self):
        statements = split_sql_statements(load_migrations()[1].sql)
        dim_work = [s for s in statements if "CREATE TABLE IF NOT EXISTS PROJECT_DW.DIM_WORK" in s]
        assert dim_work, "DIM_WORK statement not found"
        assert "One row per resolved identity; MERGE-upserted." in dim_work[0]

    def test_split_is_idempotent(self):
        for migration in load_migrations():
            once = split_sql_statements(migration.sql)
            rejoined = ";\n".join(once) + ";"
            twice = split_sql_statements(rejoined)
            assert once == twice

    def test_migration_script_executes_in_mock(self):
        """The full migration path through execute_script (the live failure mode)."""
        from papersonar.warehouse.migration_runner import MigrationRunner
        from tests.fakes.fake_warehouse import FakeWarehouse

        warehouse = FakeWarehouse()
        runner = MigrationRunner(warehouse)
        applied = runner.apply_all()
        assert applied == ["001", "002", "003"]
        # Re-run: exactly once, no errors, no duplicates
        assert runner.apply_all() == []
        assert warehouse.count("PROJECT_OPS.SCHEMA_MIGRATION") == 3
