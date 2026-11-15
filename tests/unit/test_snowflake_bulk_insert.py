"""SQL construction tests exercise SnowflakeAdapter, not FakeWarehouse."""

from __future__ import annotations

from papersonar.warehouse.adapter import SnowflakeAdapter


class Cursor:
    def __init__(self, fail_compile=False, fail_network=False):
        self.statements = []
        self.fail_compile = fail_compile
        self.fail_network = fail_network
        self.closed = False

    def execute(self, sql, params=None):
        self.statements.append((sql, list(params or [])))
        if "UNION ALL" in sql and self.fail_compile:
            error = RuntimeError("SQL compilation error")
            error.errno = 1003
            error.sqlstate = "42000"
            self.fail_compile = False
            raise error
        if "UNION ALL" in sql and self.fail_network:
            raise ConnectionError("unknown INSERT commit status")

    def close(self):
        self.closed = True


class Conn:
    def __init__(self, **kwargs):
        self.cursor_obj = Cursor(**kwargs)

    def cursor(self):
        return self.cursor_obj


def test_multirow_insert_parameter_order_and_variant():
    conn = Conn()
    count = SnowflakeAdapter(conn).insert_rows(
        "PROJECT_OPS.RAW_BATCH", ["ID", "META"], [("a", {"x": 1}), ("b", [2, 3])]
    )
    assert count == 2
    assert len(conn.cursor_obj.statements) == 1
    sql, params = conn.cursor_obj.statements[0]
    assert sql.count("UNION ALL") == 1
    assert sql.count("PARSE_JSON(%s)") == 2
    assert params == ["a", '{"x": 1}', "b", "[2, 3]"]
    assert conn.cursor_obj.closed


def test_compile_failure_falls_back_without_executemany():
    conn = Conn(fail_compile=True)
    count = SnowflakeAdapter(conn).insert_rows("PROJECT_X.T", ["ID"], [("a",), ("b",)])
    assert count == 2
    assert len(conn.cursor_obj.statements) == 3
    assert "UNION ALL" in conn.cursor_obj.statements[0][0]
    assert all("UNION ALL" not in sql for sql, _ in conn.cursor_obj.statements[1:])


def test_network_error_does_not_replay_possibly_committed_rows():
    conn = Conn(fail_network=True)
    try:
        SnowflakeAdapter(conn).insert_rows("PROJECT_X.T", ["ID"], [("a",), ("b",)])
    except ConnectionError:
        pass
    else:
        raise AssertionError("expected connection failure")
    assert len(conn.cursor_obj.statements) == 1
    assert conn.cursor_obj.closed


def test_empty_and_single_row():
    conn = Conn()
    adapter = SnowflakeAdapter(conn)
    assert adapter.insert_rows("PROJECT_X.T", ["ID"], []) == 0
    assert adapter.insert_rows("PROJECT_X.T", ["ID"], [("a",)]) == 1
    assert len(conn.cursor_obj.statements) == 1
    assert "UNION ALL" not in conn.cursor_obj.statements[0][0]
