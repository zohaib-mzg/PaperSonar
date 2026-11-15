"""Read/write smoke test of the real multi-row insert against a TEMPORARY table.

Run only when permitted to use Snowflake credits. Requires Snowflake secrets in
shell environment. Never prints credentials or payload containing secrets.

    python scripts/snowflake_bulk_insert_smoke.py
"""

from __future__ import annotations

from uuid import uuid4

from papersonar.config import Settings
from papersonar.warehouse.adapter import SnowflakeAdapter


def main() -> None:
    settings = Settings.from_env()
    settings.require_snowflake()
    adapter = SnowflakeAdapter.from_settings(settings)
    table = f"PS_INSERT_SMOKE_{uuid4().hex[:12].upper()}"
    try:
        # A session-scoped table avoids persistent test objects and real data.
        adapter.execute(f"CREATE TEMPORARY TABLE {table} (ID STRING, PAYLOAD VARIANT)")
        n = adapter.insert_rows(
            table, ["ID", "PAYLOAD"],
            [("first", {"ok": True}), ("second", [1, 2]), ("third", {"ok": False})],
        )
        count = adapter.execute(f"SELECT COUNT(*) FROM {table}")[0][0]
        variants = adapter.execute(
            f"SELECT COUNT_IF(TYPEOF(PAYLOAD) IN ('OBJECT', 'ARRAY')) FROM {table}"
        )[0][0]
        if n != 3 or count != 3 or variants != 3:
            raise AssertionError("bulk insert smoke test failed")
        print("PASS: 3 rows inserted via multi-row INSERT; JSON VARIANT values verified")
    finally:
        adapter.close()  # session-scoped temporary table is removed automatically


if __name__ == "__main__":
    main()
