"""PaperSonar command-line interface.

Every command has help text; secrets are never printed. Additional commands
(``sync``, ``backfill``, ``load``, ``replay``, ``smoke-test``) are registered by
the orchestration step once implemented.
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
    return parser


def _run_validate_config(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.mode == "ingest":
        settings.require_snowflake()
        print("configuration OK for ingestion (Snowflake settings present)")
    else:
        settings.validate()
        print("configuration OK (structural validation; Snowflake presence not required)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-config":
            # Configure logging before anything else so configuration errors are
            # emitted through the redacting formatter.
            try:
                settings = Settings.from_env()
                setup_logging(settings.log_level, settings.secret_values)
            except Exception:  # noqa: BLE001 - configuration errors must still be logged safely
                setup_logging("INFO")
                raise
            return _run_validate_config(args)
    except Exception as exc:  # noqa: BLE001 - single CLI error boundary; message is redacted
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
