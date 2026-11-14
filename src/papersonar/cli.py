"""PaperSonar command-line interface.

Commands:
- ``validate-config``: structural validation (no network); ``--mode ingest``
  additionally requires all mandatory Snowflake settings.
- ``migrate``: apply versioned migrations to Snowflake.
- ``sync`` / ``backfill``: run the ingestion pipeline (fail closed on config).
- ``quality``: run the data-quality gate against the warehouse.
- ``smoke-test``: connectivity + migrations + row counts (live acceptance).

Secrets are never printed. Exit codes: 0 success, 1 partial/quality-fail,
2 configuration or hard error.
"""

from __future__ import annotations

import argparse
import sys

from papersonar.config import Settings
from papersonar.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="papersonar",
        description=(
            "PaperSonar Phase 2 ingestion pipeline. "
            "Production target is fixed to Snowflake; there is no fallback database."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate-config",
        help="Validate runtime configuration without network access or source calls.",
    )
    validate.add_argument(
        "--mode",
        choices=("validate", "ingest"),
        default="validate",
        help=(
            "'validate' checks structure only; 'ingest' additionally requires all "
            "mandatory Snowflake settings (fails closed before any source call)."
        ),
    )

    sub.add_parser(
        "migrate",
        help="Apply versioned, non-destructive migrations to the Snowflake warehouse.",
    )
    sync = sub.add_parser("sync", help="Run one incremental sync (requires Snowflake settings).")
    sync.add_argument("--dry-run", action="store_true", help="Plan windows and exit without fetching or writing.")
    backfill = sub.add_parser(
        "backfill", help="Run bounded historical backfill windows (requires Snowflake settings)."
    )
    backfill.add_argument("--dry-run", action="store_true", help="Plan windows and exit without fetching or writing.")
    sub.add_parser("quality", help="Run the data-quality gate against the Snowflake warehouse.")
    sub.add_parser(
        "smoke-test",
        help="Live Snowflake acceptance: connect, apply migrations, report row counts.",
    )
    return parser


def _load_settings_and_logging() -> Settings:
    settings = Settings.from_env()
    setup_logging(settings.log_level, settings.secret_values)
    return settings


def _run_validate_config(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.mode == "ingest":
        settings.require_snowflake()
        print("configuration OK for ingestion (Snowflake settings present)")
    else:
        settings.validate()
        print("configuration OK (structural validation; Snowflake presence not required)")
    return 0


def _warehouse_for(settings: Settings):
    from papersonar.warehouse.adapter import SnowflakeAdapter

    settings.require_snowflake()
    return SnowflakeAdapter.from_settings(settings)


def _run_migrate() -> int:
    settings = _load_settings_and_logging()
    warehouse = _warehouse_for(settings)
    try:
        from papersonar.warehouse.migration_runner import MigrationRunner

        applied = MigrationRunner(warehouse).apply_all()
        print(f"migrations applied: {', '.join(applied) if applied else 'none (up to date)'}")
    finally:
        warehouse.close()
    return 0


def _print_run_result(result) -> int:
    print(f"run_id={result.run_id}")
    print(f"mode={result.mode}")
    print(f"status={result.status}")
    for source, status in sorted(result.source_statuses.items()):
        print(f"source {source}: {status}")
    print(
        "counters: "
        f"raw_records={result.raw_records} staging_rows={result.staging_rows} "
        f"quarantined={result.quarantined} warehouse_rows={result.warehouse_rows} "
        f"retries={result.retry_count}"
    )
    print(f"quality_gate={result.gate_summary or 'not run'}")
    if result.error_summary:
        print(f"error_summary={result.error_summary}")
    if result.status == "succeeded":
        return 0
    if result.status == "partial":
        return 1
    return 2


def _run_sync_or_backfill(args: argparse.Namespace) -> int:
    settings = _load_settings_and_logging()
    from papersonar.orchestrator import Orchestrator

    if args.dry_run:
        settings.require_snowflake()
        orchestrator = Orchestrator(settings)
        mode = "sync" if args.command == "sync" else "backfill"
        for name, enabled in sorted(settings.sources.items()):
            if not enabled.enabled:
                print(f"source {name}: disabled")
                continue
            windows = orchestrator._windows_for(name, mode)
            for window in windows:
                print(
                    f"source {name}: {mode} window {window.stream_name} "
                    f"({window.window_start}..{window.window_end or 'open'})"
                )
        return 0

    warehouse = _warehouse_for(settings)
    try:
        orchestrator = Orchestrator(settings, warehouse=warehouse)
        result = orchestrator.run("sync" if args.command == "sync" else "backfill")
        return _print_run_result(result)
    finally:
        warehouse.close()


def _run_quality() -> int:
    settings = _load_settings_and_logging()
    warehouse = _warehouse_for(settings)
    try:
        from papersonar.warehouse.quality import QualityGate

        result = QualityGate(warehouse).run()
        print(f"quality_gate={result.summary}")
        for check in result.checks:
            print(
                f"check {check['name']}: value={check['value']} "
                f"passed={check['passed']} threshold={check['threshold']}"
            )
        return 0 if result.passed else 1
    finally:
        warehouse.close()


def _run_smoke_test() -> int:
    settings = _load_settings_and_logging()
    warehouse = _warehouse_for(settings)
    try:
        from papersonar.warehouse.migration_runner import MigrationRunner
        from papersonar.warehouse.quality import QualityGate

        applied = MigrationRunner(warehouse).apply_all()
        print(f"migrations applied: {', '.join(applied) if applied else 'none (up to date)'}")
        identity = warehouse.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_USER()")
        if identity:
            print(f"connected to database={identity[0][0]} schema={identity[0][1]} user={identity[0][2]}")
        gate = QualityGate(warehouse).run()
        print(f"quality_gate={gate.summary}")
        for table in (
            "PROJECT_OPS.ETL_RUN",
            "PROJECT_OPS.SOURCE_SYNC_STATE",
            "PROJECT_OPS.RAW_BATCH",
            "PROJECT_STAGING.STG_WORK_RECORD",
            "PROJECT_DW.DIM_WORK",
        ):
            count_rows = warehouse.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"{table}: {count_rows[0][0] if count_rows else 0} rows")
        return 0
    finally:
        warehouse.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-config":
            try:
                settings = Settings.from_env()
                setup_logging(settings.log_level, settings.secret_values)
            except Exception:  # noqa: BLE001 - configuration errors must still be logged safely
                setup_logging("INFO")
                raise
            return _run_validate_config(args)
        if args.command == "migrate":
            return _run_migrate()
        if args.command in ("sync", "backfill"):
            return _run_sync_or_backfill(args)
        if args.command == "quality":
            return _run_quality()
        if args.command == "smoke-test":
            return _run_smoke_test()
    except Exception as exc:  # noqa: BLE001 - single CLI error boundary; message is redacted
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
