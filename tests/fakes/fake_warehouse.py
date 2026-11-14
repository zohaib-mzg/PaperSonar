"""In-memory mock of the Snowflake warehouse protocol.

Implements the same semantics the production adapter promises - in particular
MERGE-style idempotent upserts, transaction boundaries and a raw file stage -
so integration tests can exercise pipeline behavior deterministically without
network access. This is a testing technique only, never a production target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from papersonar.errors import CheckpointError


@dataclass
class Table:
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)


class FakeWarehouse:
    """Mock warehouse with dict-backed tables and MERGE semantics."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.tables: dict[str, Table] = {}
        self.stage: dict[str, bytes] = {}
        self.executed: list[str] = []
        self.in_transaction = False
        self.fail_next_upsert = False
        self.fail_after: int | None = fail_after
        self._op_count = 0

    # -- protocol ------------------------------------------------------------

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[tuple]:
        self.executed.append(sql.strip()[:200])
        self._count_op()
        sql_l = " ".join(sql.split()).lower()
        if sql_l.startswith("select"):
            return self._select(sql, params)
        if sql_l.startswith("update"):
            return self._update(sql, params)
        return []

    def _select(self, sql: str, params: list[Any] | tuple[Any, ...] | None) -> list[tuple]:
        # Supports:
        #   SELECT cols FROM table [WHERE ...] [ORDER BY ...]
        #   SELECT COUNT(*) FROM table [WHERE ...]
        flat = " ".join(sql.split())
        count_match = re.match(
            r"SELECT COUNT\(\*\) FROM ([A-Za-z0-9_.]+)(?: WHERE (.+))?$", flat, re.I
        )
        if count_match:
            table_name, where_sql = count_match.groups()
            table = self.tables.get(table_name.upper())
            if table is None:
                return [(0,)]
            params = list(params or [])
            filters = _parse_where(where_sql, params)
            count = sum(
                1
                for row in table.rows
                if all(_cmp(row.get(col.upper()), op, value) for col, op, value in filters)
            )
            return [(count,)]
        match = re.match(
            r"SELECT (.+?) FROM ([A-Za-z0-9_.]+)(?: WHERE (.+?))?(?: ORDER BY (.+))?$",
            flat,
            re.I,
        )
        if not match:
            raise NotImplementedError(f"FakeWarehouse cannot parse SELECT: {sql}")
        cols_sql, table_name, where_sql, _order = match.groups()
        table = self.tables.get(table_name.upper())
        if table is None:
            return []
        params = list(params or [])
        filters = _parse_where(where_sql, params)
        out = []
        for row in table.rows:
            if all(_cmp(row.get(col.upper()), op, value) for col, op, value in filters):
                projected = [c.strip() for c in cols_sql.split(",")]
                out.append(tuple(row.get(c.upper()) for c in projected))
        return out

    def _update(self, sql: str, params: list[Any] | tuple[Any, ...] | None) -> list[tuple]:
        match = re.match(
            r"UPDATE ([A-Za-z0-9_.]+) SET (.+?) WHERE (.+)$",
            " ".join(sql.split()),
            re.I,
        )
        if not match:
            raise NotImplementedError(f"FakeWarehouse cannot parse UPDATE: {sql}")
        table_name, set_sql, where_sql = match.groups()
        table = self.tables.get(table_name.upper())
        if table is None:
            return []
        params = list(params or [])
        # Parse assignments: COL = %s (bound) or COL = LITERAL (true/false/number/string).
        set_pairs: list[tuple[str, Any]] = []
        param_index = 0
        for part in set_sql.split(","):
            assign = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(%s|[^,\s]+)\s*$", part.strip())
            if not assign:
                raise NotImplementedError(f"FakeWarehouse cannot parse SET fragment: {part}")
            col = assign.group(1).upper()
            if assign.group(2) == "%s":
                if param_index >= len(params):
                    raise NotImplementedError("FakeWarehouse SET has more %s than params")
                set_pairs.append((col, params[param_index]))
                param_index += 1
            else:
                set_pairs.append((col, _parse_literal(assign.group(2))))
        filters = _parse_where(where_sql, params[param_index:])
        for row in table.rows:
            if all(_cmp(row.get(col.upper()), op, value) for col, op, value in filters):
                for col, value in set_pairs:
                    row[col] = value
        return []

    def upsert_rows(
        self,
        table: str,
        key_columns: list[str],
        columns: list[str],
        rows: list[list[Any]],
        update_columns: list[str] | None = None,
    ) -> int:
        self.executed.append(f"MERGE INTO {table}")
        self._count_op()
        if self.fail_next_upsert:
            self.fail_next_upsert = False
            raise CheckpointError("simulated database failure during upsert")
        key_columns = [k.upper() for k in key_columns]
        update_columns = [c.upper() for c in (update_columns or [c for c in columns if c.upper() not in key_columns])]
        table_obj = self.tables.setdefault(table.upper(), Table(columns=[c.upper() for c in columns]))
        for row in rows:
            record = {c.upper(): value for c, value in zip(columns, row, strict=True)}
            keys = tuple(record[k] for k in key_columns)
            existing = next(
                (r for r in table_obj.rows if tuple(r.get(k) for k in key_columns) == keys),
                None,
            )
            if existing is None:
                table_obj.rows.append(record)
            else:
                for col in update_columns:
                    existing[col] = record.get(col)
        return len(rows)

    def insert_rows(self, table: str, columns: list[str], rows: list[list[Any]]) -> int:
        self.executed.append(f"INSERT INTO {table}")
        self._count_op()
        table_obj = self.tables.setdefault(table.upper(), Table(columns=[c.upper() for c in columns]))
        for row in rows:
            table_obj.rows.append({c.upper(): value for c, value in zip(columns, row, strict=True)})
        return len(rows)

    def execute_script(self, sql_text: str) -> None:
        from papersonar.warehouse.sqlsplit import split_sql_statements

        for statement in split_sql_statements(sql_text):
            self.executed.append(statement.split("\n")[0][:120])
            self._materialize(statement)

    def _materialize(self, statement: str) -> None:
        """Materialize CREATE TABLE statements so SELECTs against new tables work."""
        match = re.search(r"CREATE TABLE IF NOT EXISTS ([A-Za-z0-9_.]+)\s*\(", statement, re.I)
        if not match:
            return
        table_name = match.group(1).upper()
        if table_name in self.tables:
            return
        columns: list[str] = []
        for line in statement.splitlines():
            column_match = re.match(
                r"^\s{2}([A-Z][A-Z0-9_]+)\s+(STRING|NUMBER|BOOLEAN|FLOAT|VARIANT|ARRAY|DATE|TIMESTAMP_TZ)\b",
                line,
            )
            if column_match:
                columns.append(column_match.group(1))
        self.tables[table_name] = Table(columns=columns)

    def put_file(self, local_path: Path, stage_path: str) -> None:
        self.stage[stage_path] = local_path.read_bytes()

    def get_file(self, stage_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.stage[stage_path])

    def begin(self) -> None:
        self.in_transaction = True

    def commit(self) -> None:
        self.in_transaction = False

    def rollback(self) -> None:
        self.in_transaction = False

    def close(self) -> None:
        return None

    # -- helpers -------------------------------------------------------------

    def count(self, table: str) -> int:
        return len(self.tables.get(table.upper(), Table(columns=[])).rows)

    def _count_op(self) -> None:
        self._op_count += 1
        if self.fail_after is not None and self._op_count > self.fail_after:
            raise CheckpointError("simulated database failure")


def _parse_where(where_sql: str | None, params: list[Any]) -> list[tuple[str, str, Any]]:
    """Return (column, operator, value) triples. Supports = and != with bound
    params or SQL literals (quoted strings, TRUE/FALSE/NULL/numbers)."""
    if not where_sql:
        return []
    filters: list[tuple[str, str, Any]] = []
    parts = re.split(r"\bAND\b", where_sql, flags=re.I)
    param_index = 0
    for part in parts:
        in_match = re.match(r"\s*([A-Za-z0-9_]+)\s+IN\s*\(([^)]*)\)\s*$", part.strip(), re.I)
        if in_match:
            in_values: list[Any] = []
            for item in in_match.group(2).split(","):
                item = item.strip()
                if item == "%s":
                    if param_index >= len(params):
                        raise NotImplementedError("FakeWarehouse WHERE requires literal params")
                    in_values.append(params[param_index])
                    param_index += 1
                else:
                    in_values.append(_parse_literal(item))
            filters.append((in_match.group(1).upper(), "in", in_values))
            continue
        match = re.match(
            r"\s*([A-Za-z0-9_]+)\s*(=|!=|<>)\s*(%s|'[^']*'|\"[^\"]*\"|[A-Za-z0-9_.\-]+)\s*$",
            part.strip(),
        )
        if not match:
            raise NotImplementedError(f"FakeWarehouse cannot parse WHERE fragment: {part}")
        col = match.group(1).upper()
        op = "=" if match.group(2) == "=" else "!="
        raw = match.group(3)
        if raw == "%s":
            if param_index >= len(params):
                raise NotImplementedError("FakeWarehouse WHERE requires literal params")
            value = params[param_index]
            param_index += 1
        else:
            value = _parse_literal(raw)
        filters.append((col, op, value))
    return filters


def _cmp(left: Any, op: str, right: Any) -> bool:
    if op == "=":
        return _eq(left, right)
    if op == "!=":
        return not _eq(left, right)
    if op == "in":
        return any(_eq(left, candidate) for candidate in right)
    raise NotImplementedError(f"FakeWarehouse operator {op}")


def _parse_literal(text: str) -> Any:
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.match(r"^-?\d+$", text):
        return int(text)
    return text.strip("'\"")


def _eq(left: Any, right: Any) -> bool:
    return left == right
