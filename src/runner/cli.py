"""Command line entry point for extraction and deployment.

Examples
--------
Check configuration without touching Snowflake::

    python -m runner.cli check

Dry-run one source window to a local directory::

    python -m runner.cli extract --source openalex --mode incremental --dry-run

Extract and load one source, then drain the Snowflake task graph::

    python -m runner.cli extract --source crossref --mode incremental

Deploy transformation SQL via the internal stage (setup is one-time and
requires ``--include-setup`` with an administrative role)::

    python -m runner.cli deploy --sql-dir sql --yes

Trigger the graph until all loaded batches are resolved::

    python -m runner.cli trigger --drain
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from runner.config import ConfigurationError, Settings
from runner.extract_run import plan_and_run
from runner.snowflake import SnowflakeClient
from runner.windows import plan_windows

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m runner.cli",
        description="PaperSonar strict-ELT extraction and Snowflake deployment runner.",
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Validate configuration and secret presence.")
    check.add_argument("--config", default=None, help="Path to config/sources.yml")

    extract = sub.add_parser("extract", help="Extract one or more source windows.")
    extract.add_argument("--source", required=True, help="openalex, crossref, arxiv, datacite or zenodo")
    extract.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    extract.add_argument("--from", dest="from_date", default=None, help="Override window start (YYYY-MM-DD)")
    extract.add_argument("--until", dest="until_date", default=None, help="Override window end (YYYY-MM-DD)")
    extract.add_argument("--config", default=None, help="Path to config/sources.yml")
    extract.add_argument("--dry-run", action="store_true", help="Write local files only; no Snowflake calls")
    extract.add_argument("--force", action="store_true", help="Re-extract a LOADED/PROCESSING batch")
    extract.add_argument(
        "--no-task",
        action="store_true",
        help="Do not EXECUTE TASK after the last window loads",
    )
    extract.add_argument("--json", action="store_true", help="Print machine-readable report")

    status = sub.add_parser("status", help="Show one batch and its manifest.")
    status.add_argument("--batch-id", required=True)
    status.add_argument("--config", default=None, help="Path to config/sources.yml")

    deploy = sub.add_parser("deploy", help="Upload and execute SQL files via the internal stage.")
    deploy.add_argument("--sql-dir", default="sql")
    deploy.add_argument("--yes", action="store_true", help="Required confirmation for DDL execution")
    deploy.add_argument("--config", default=None, help="Path to config/sources.yml")
    deploy.add_argument(
        "--include-setup",
        action="store_true",
        help="Also deploy sql/00_setup; requires one-time administrative privileges",
    )

    trigger = sub.add_parser("trigger", help="Execute the Snowflake ELT root task.")
    trigger.add_argument(
        "--drain",
        action="store_true",
        help="Trigger the root task until every LOADED/PROCESSING batch is resolved",
    )
    trigger.add_argument("--config", default=None, help="Path to config/sources.yml")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "extract":
            return _extract(args)
        if args.command == "status":
            return _status(args)
        if args.command == "deploy":
            return _deploy(args)
        if args.command == "trigger":
            return _trigger(args)
    except ConfigurationError as exc:
        logger.error("configuration error: %s", exc)
        return 2
    return 1


def _settings(args: argparse.Namespace) -> Settings:
    # Not every subcommand needs Snowflake, but every subcommand that does must
    # expose --config. The fallback keeps future commands from failing on a
    # missing attribute.
    return Settings.from_env(config_path=getattr(args, "config", None))


def _check(args: argparse.Namespace) -> int:
    settings = _settings(args)
    print(f"config: {settings.config_path}")
    print(f"target: {settings.target}")
    print(f"sources enabled: {', '.join(settings.enabled_sources())}")
    missing = settings.snowflake.missing()
    if missing:
        print("snowflake: NOT CONFIGURED (missing " + ", ".join(missing) + ")")
    else:
        print("snowflake: configured")
    print("secrets: values are never printed")
    return 0


def _extract(args: argparse.Namespace) -> int:
    settings = _settings(args)
    watermark_end: str | None = None
    if not args.dry_run:
        client = SnowflakeClient.from_settings(settings)
        try:
            entity_name = settings.require_source(args.source).entity
            watermark_end = client.get_watermark(args.source, entity_name)
        finally:
            client.close()
    windows = plan_windows(
        settings,
        args.source,
        args.mode,
        from_date=args.from_date,
        until_date=args.until_date,
        watermark_end=watermark_end,
    )
    reports = plan_and_run(
        settings,
        args.source,
        args.mode,
        windows,
        dry_run=args.dry_run,
        force=args.force,
        execute_task=not args.no_task,
    )
    payload = [report.as_dict() for report in reports]
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for report in reports:
            print(
                f"{report.batch_id} {report.source_name}/{report.entity_name} "
                f"{report.window_start}..{report.window_end} status={report.status} "
                f"files={report.file_count} records={report.record_count} "
                f"oversize={report.oversize_count} task={report.task_triggered}"
            )
    return 0 if all(report.status in ("loaded", "extracted", "skipped") for report in reports) else 1


def _status(args: argparse.Namespace) -> int:
    settings = _settings(args)
    client = SnowflakeClient.from_settings(settings)
    try:
        batch = client.get_batch(args.batch_id)
        if batch is None:
            print(f"batch not found: {args.batch_id}")
            return 1
        rows = client.execute(
            "SELECT FILE_NAME, RECORD_COUNT, STATUS FROM PROJECT_AUDIT.BATCH_MANIFEST "
            "WHERE BATCH_ID = %s ORDER BY FILE_NAME",
            [args.batch_id],
        )
        print(json.dumps({"batch": batch, "manifest": rows}, indent=2, default=str))
        return 0
    finally:
        client.close()


def _deploy(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to execute DDL without --yes (review the diff first).")
        return 2
    settings = _settings(args)
    client = SnowflakeClient.from_settings(settings)
    try:
        deployed = client.deploy_sql(
            Path(args.sql_dir), include_setup=args.include_setup
        )
        print(json.dumps({"deployed": deployed}, indent=2))
        return 0
    finally:
        client.close()


def _trigger(args: argparse.Namespace) -> int:
    settings = _settings(args)
    client = SnowflakeClient.from_settings(settings)
    try:
        if args.drain:
            rounds = client.drain_batches()
            print(f"drained pending batches in {rounds} trigger round(s)")
        else:
            client.execute_root_task()
            print("triggered PAPERSONAR.PROJECT_AUDIT.TASK_ELT_ROOT")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
