"""Deployment selection tests: setup SQL is manual-only by default."""

from __future__ import annotations

from pathlib import Path

from runner.snowflake import (
    ELT_CHILD_TASKS,
    ROOT_TASK,
    TASK_GRAPH_SQL,
    SnowflakeClient,
)


def _client(executed: list[str] | None = None) -> SnowflakeClient:
    client = object.__new__(SnowflakeClient)
    client.put_file = lambda *args, **kwargs: None  # type: ignore[method-assign]

    def execute(sql: str, params: object = None) -> None:
        if executed is not None:
            executed.append(sql)

    client.execute = execute  # type: ignore[method-assign]
    return client


def _write(root: Path, relative: str, header: str = "-- test\nSELECT 1;\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header, encoding="utf-8")


def test_deploy_skips_setup_and_evidence_by_default(tmp_path: Path) -> None:
    _write(tmp_path, "00_setup/00_database.sql")
    _write(tmp_path, "01_staging/01_tables.sql")
    _write(tmp_path, "99_tests/01_acceptance.sql")
    _write(tmp_path, "07_reporting/02_manual.sql", "-- Deploy: manual\nSELECT 1;\n")

    deployed = _client().deploy_sql(tmp_path)

    assert deployed == ["01_staging/01_tables.sql"]


def test_deploy_can_include_setup_explicitly(tmp_path: Path) -> None:
    _write(tmp_path, "00_setup/00_database.sql")
    _write(tmp_path, "01_staging/01_tables.sql")

    deployed = _client().deploy_sql(tmp_path, include_setup=True)

    assert deployed == ["00_setup/00_database.sql", "01_staging/01_tables.sql"]


def test_deploying_setup_directory_directly_is_allowed(tmp_path: Path) -> None:
    _write(tmp_path, "00_database.sql")

    deployed = _client().deploy_sql(tmp_path)

    assert deployed == ["00_database.sql"]


def test_deploy_prepares_task_graph_for_on_demand_runs(tmp_path: Path) -> None:
    _write(tmp_path, TASK_GRAPH_SQL)
    executed: list[str] = []

    deployed = _client(executed).deploy_sql(tmp_path)

    assert deployed == [TASK_GRAPH_SQL]
    assert executed[0].startswith("EXECUTE IMMEDIATE FROM")
    assert f"ALTER TASK {ROOT_TASK} SUSPEND" in executed
    for task in ELT_CHILD_TASKS:
        assert f"ALTER TASK {task} RESUME" in executed
    assert f"ALTER TASK {ROOT_TASK} RESUME" not in executed
    assert executed[-1] == f"ALTER TASK {ELT_CHILD_TASKS[-1]} RESUME"


def test_execute_root_task_runs_suspended_root_on_demand() -> None:
    executed: list[str] = []

    _client(executed).execute_root_task()

    assert executed == [f"EXECUTE TASK {ROOT_TASK}"]


def test_deploy_without_task_graph_does_not_resume(tmp_path: Path) -> None:
    _write(tmp_path, "06_facts/02_load_facts.sql")
    executed: list[str] = []

    _client(executed).deploy_sql(tmp_path)

    assert not any(sql.startswith("ALTER TASK") for sql in executed)
