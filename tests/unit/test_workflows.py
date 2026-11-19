"""Guard the GitHub-owned scheduling decision and workflow wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _triggers(workflow: dict) -> dict:
    # PyYAML 1.1 parses the key `on` as boolean True.
    triggers = workflow.get("on") or workflow.get(True)
    assert isinstance(triggers, dict)
    return triggers


def test_extract_workflow_is_the_only_scheduler() -> None:
    extract = _load("extract-load.yml")
    triggers = _triggers(extract)
    assert triggers["schedule"][0]["cron"] == "30 2 * * *"

    graph_sql = (
        PROJECT_ROOT / "sql" / "09_tasks" / "02_task_graph.sql"
    ).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in graph_sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "SCHEDULE =" not in executable
    assert "USING CRON" not in executable


def test_extract_workflow_reads_openalex_plan_variable() -> None:
    env = _load("extract-load.yml")["jobs"]["extract"]["env"]
    confirmation = env["OPENALEX_DAILY_SYNC"]
    assert "inputs.openalex_daily_sync" in confirmation
    assert "vars.OPENALEX_DAILY_SYNC" in confirmation


def test_extract_workflow_drains_task_graph_after_all_sources() -> None:
    steps = _load("extract-load.yml")["jobs"]["extract"]["steps"]
    extract_step = next(step for step in steps if step.get("name") == "Extract source windows")
    assert "SKIP_OPENALEX" in extract_step["run"]
    assert "python -m runner.cli trigger --drain" in extract_step["run"]


def test_deploy_workflow_deploys_on_main_with_approval_environment() -> None:
    deploy = _load("deploy-ci.yml")
    triggers = _triggers(deploy)
    assert triggers["push"]["branches"] == ["main"]
    assert deploy["jobs"]["deploy"]["environment"] == "snowflake-production"
