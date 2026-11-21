"""CLI parser and drain-outcome regression tests."""

from __future__ import annotations

import argparse

import pytest

from runner.cli import _trigger, build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["check"],
        ["extract", "--source", "crossref"],
        ["status", "--batch-id", "BATCH_x"],
        ["deploy", "--yes"],
        ["trigger"],
        ["trigger", "--drain"],
        ["trigger", "--drain", "--retry-batch-id", "BATCH_x"],
        ["report"],
    ],
)
def test_every_command_exposes_config(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    assert hasattr(args, "config")


class _FakeClient:
    def __init__(self, statuses: list[dict[str, object]]) -> None:
        self._statuses = statuses
        self.drained = False

    def batch_statuses(self) -> list[dict[str, object]]:
        return list(self._statuses)

    def drain_batches(self) -> int:
        self.drained = True
        return 1

    def requeue_failed_batch(self, batch_id: str) -> bool:
        return True

    def execute_root_task(self) -> None:
        return None

    def close(self) -> None:
        return None


def _args() -> argparse.Namespace:
    return build_parser().parse_args(["trigger", "--drain"])


def test_drain_succeeds_when_every_pending_batch_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([])
    phase = {"n": 0}

    def batch_statuses() -> list[dict[str, object]]:
        phase["n"] += 1
        if phase["n"] == 1:
            return [
                {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "CROSSREF", "STATUS": "LOADED", "ERROR_SUMMARY": None},
            ]
        return [
            {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "CROSSREF", "STATUS": "PUBLISHED", "ERROR_SUMMARY": None},
            {"BATCH_ID": "BATCH_B", "SOURCE_NAME": "ZENODO", "STATUS": "FAILED", "ERROR_SUMMARY": "old failure"},
        ]

    monkeypatch.setattr("runner.cli._settings", lambda args: object())
    monkeypatch.setattr("runner.cli.SnowflakeClient.from_settings", lambda settings: client)
    monkeypatch.setattr(client, "batch_statuses", batch_statuses)

    assert _trigger(_args()) == 0


def test_drain_fails_when_a_pending_batch_ends_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([])
    phase = {"n": 0}

    def batch_statuses() -> list[dict[str, object]]:
        phase["n"] += 1
        if phase["n"] == 1:
            return [
                {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "ARXIV", "STATUS": "LOADED", "ERROR_SUMMARY": None},
            ]
        return [
            {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "ARXIV", "STATUS": "FAILED", "ERROR_SUMMARY": "critical DQ failure"},
        ]

    monkeypatch.setattr("runner.cli._settings", lambda args: object())
    monkeypatch.setattr("runner.cli.SnowflakeClient.from_settings", lambda settings: client)
    monkeypatch.setattr(client, "batch_statuses", batch_statuses)

    assert _trigger(_args()) == 1


def test_drain_ignores_failures_from_earlier_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient([])
    phase = {"n": 0}

    def batch_statuses() -> list[dict[str, object]]:
        phase["n"] += 1
        if phase["n"] == 1:
            return [
                {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "CROSSREF", "STATUS": "LOADED", "ERROR_SUMMARY": None},
            ]
        return [
            {"BATCH_ID": "BATCH_A", "SOURCE_NAME": "CROSSREF", "STATUS": "PUBLISHED", "ERROR_SUMMARY": None},
            {"BATCH_ID": "BATCH_OLD", "SOURCE_NAME": "DATACITE", "STATUS": "FAILED", "ERROR_SUMMARY": "old failure"},
        ]

    monkeypatch.setattr("runner.cli._settings", lambda args: object())
    monkeypatch.setattr("runner.cli.SnowflakeClient.from_settings", lambda settings: client)
    monkeypatch.setattr(client, "batch_statuses", batch_statuses)

    assert _trigger(_args()) == 0
