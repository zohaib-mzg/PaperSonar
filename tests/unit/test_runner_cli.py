"""CLI parser regression tests."""

from __future__ import annotations

import pytest

from runner.cli import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["check"],
        ["extract", "--source", "crossref"],
        ["status", "--batch-id", "BATCH_x"],
        ["deploy", "--yes"],
        ["trigger"],
        ["trigger", "--drain"],
    ],
)
def test_every_command_exposes_config(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    assert hasattr(args, "config")
