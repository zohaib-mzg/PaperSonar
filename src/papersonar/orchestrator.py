"""Orchestration: run modes, per-source windows, checkpoints and recovery.

Run policy (per the Phase 2 pack):
- ``require_snowflake`` is enforced before any source API call (fail closed).
- Every run gets a unique run id recorded in PROJECT_OPS.ETL_RUN with mode,
  timestamps, config checksum and per-source statuses.
- A run is ``succeeded`` only when every enabled source succeeded AND the
  quality gate passed; any source failure makes it ``partial`` at best; the
  quality gate failing can never produce ``succeeded``.
- The completed watermark advances only after a window's pages were all
  persisted, parsed, staged and loaded; checkpoint writes are transactional.
- In-progress pagination state (``cursor_or_token``) is separate from the
  completed watermark and is used to resume after interruption. Expired OAI
  resumption tokens restart the bounded window once (idempotent upserts).
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from papersonar import __version__
from papersonar.canonical import CanonicalResolver
from papersonar.config import Settings
from papersonar.errors import ConfigurationError, RetryableError
from papersonar.http_client import HttpClient
from papersonar.identifiers import canonical_json_hash
from papersonar.raw_store import RawStore
from papersonar.sources import ADAPTERS, BaseAdapter
from papersonar.sources.base import FetchWindow
from papersonar.staging import StagingValidator
from papersonar.timeutil import today_utc, utc_now
from papersonar.warehouse.adapter import SnowflakeAdapter, Warehouse
from papersonar.warehouse.loaders import WarehouseLoader
from papersonar.warehouse.migration_runner import MigrationRunner
from papersonar.warehouse.quality import QualityGate
from papersonar.warehouse.state_store import StateStore, SyncState

logger = logging.getLogger(__name__)

USER_AGENT = f"PaperSonar/{__version__}"

# Backfill is chunked into bounded daily windows; one run advances at most this
# many windows per source to keep GitHub Actions runs inside their time budget.
BACKFILL_MAX_WINDOWS = 60


@dataclass
class RunResult:
    run_id: str
    mode: str
    status: str = "started"
    source_statuses: dict[str, str] = field(default_factory=dict)
    raw_records: int = 0
    staging_rows: int = 0
    quarantined: int = 0
    warehouse_rows: int = 0
    retry_count: int = 0
    gate_summary: str = ""
    error_summary: str | None = None


class Orchestrator:
    """Executes backfill/sync runs against Snowflake."""

    def __init__(
        self,
        settings: Settings,
        warehouse: Warehouse | None = None,
        sleep: Any = None,
    ) -> None:
        self.settings = settings
        self._warehouse = warehouse
        self._sleep = sleep  # test hook; None uses default pacing

    # -- public API ----------------------------------------------------------

    def run(self, mode: str) -> RunResult:
        """Execute one pipeline run. Mode: ``backfill`` or ``sync``."""
        if mode not in ("backfill", "sync"):
            raise ConfigurationError(f"Unknown run mode: {mode!r}")
        # Fail closed BEFORE any source API call.
        self.settings.require_snowflake()
        enabled = [name for name, source in self.settings.sources.items() if source.enabled]
        if not enabled:
            raise ConfigurationError("No sources enabled; nothing to run")
        warehouse = self._ensure_warehouse()
        run_id = _new_run_id()
        result = RunResult(run_id=run_id, mode=mode)
        state = StateStore(warehouse)
        started_at = utc_now()
        state.create_run(
            run_id=run_id,
            mode=mode,
            started_at=started_at,
            git_commit=_git_commit(),
            config_checksum=self._config_checksum(),
            code_version=__version__,
        )
        try:
            MigrationRunner(warehouse).apply_all()
            for name in enabled:
                source_status, counters = self._run_source(name, run_id, mode, state)
                result.source_statuses[name] = source_status
                result.raw_records += counters.get("raw_records", 0)
                result.staging_rows += counters.get("staging_rows", 0)
                result.quarantined += counters.get("quarantined", 0)
                result.warehouse_rows += counters.get("warehouse_rows", 0)
                result.retry_count += counters.get("retries", 0)
            gate = QualityGate(warehouse).run()
            result.gate_summary = gate.summary
            result.status = _final_status(result.source_statuses, gate.passed)
        except Exception as exc:  # noqa: BLE001 - run-level error boundary
            result.status = "failed"
            result.error_summary = f"{type(exc).__name__}: {exc}"
            logger.error("run failed: %s", exc)
        finally:
            state.finish_run(
                run_id=run_id,
                status=result.status,
                finished_at=utc_now(),
                source_statuses=result.source_statuses,
                raw_rows=result.raw_records,
                staging_rows=result.staging_rows,
                quarantined_rows=result.quarantined,
                warehouse_rows=result.warehouse_rows,
                retry_count=result.retry_count,
                quality_gate_result=result.gate_summary or None,
                error_summary=result.error_summary,
            )
        return result

    # -- internals -----------------------------------------------------------

    def _ensure_warehouse(self) -> Warehouse:
        if self._warehouse is None:
            self._warehouse = SnowflakeAdapter.from_settings(self.settings)
        return self._warehouse

    def _config_checksum(self) -> str:
        return canonical_json_hash(
            {
                "schema_version": self.settings.schema_version,
                "sources": {
                    name: {
                        "enabled": source.enabled,
                        "page_size": source.page_size,
                        "max_pages": source.max_pages,
                        "backfill_from": source.backfill_from_date,
                        "overlap_days": source.sync_overlap_days,
                    }
                    for name, source in sorted(self.settings.sources.items())
                },
            }
        )

    def _run_source(
        self, name: str, run_id: str, mode: str, state: StateStore
    ) -> tuple[str, dict[str, int]]:
        counters = {"raw_records": 0, "staging_rows": 0, "quarantined": 0, "warehouse_rows": 0, "retries": 0}
        adapter = self._build_adapter(name)
        raw_store = RawStore(
            warehouse=self._warehouse,
            state_store=state,
            raw_dir=self.settings.raw_dir,
            schema_version=self.settings.schema_version,
        )
        validator = StagingValidator(schema_version=self.settings.schema_version)
        loader = WarehouseLoader(self._warehouse)
        resolver = CanonicalResolver(self._warehouse)

        statuses: list[str] = []
        try:
            windows = self._windows_for(name, mode)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s: window planning failed: %s", name, exc)
            return "failed", counters

        for window in windows:
            try:
                status = self._run_window(
                    adapter, window, run_id, mode, state, raw_store, validator, loader, resolver, counters
                )
            except Exception as exc:  # noqa: BLE001 - one failing source must not abort the run
                logger.error("%s/%s failed: %s", adapter.name, window.stream_name, exc)
                failed_state = SyncState(
                    source_name=adapter.name, stream_name=window.stream_name, sync_mode=mode
                )
                self._record_failure(state, adapter.name, window.stream_name, run_id, mode, exc, failed_state)
                status = "failed"
            statuses.append(status)
        source_status = (
            "succeeded"
            if all(s == "succeeded" for s in statuses)
            else "partial"
            if any(s == "succeeded" for s in statuses)
            else "failed"
        )
        return source_status, counters

    def _run_window(
        self,
        adapter: BaseAdapter,
        window: FetchWindow,
        run_id: str,
        mode: str,
        state: StateStore,
        raw_store: RawStore,
        validator: StagingValidator,
        loader: WarehouseLoader,
        resolver: CanonicalResolver,
        counters: dict[str, int],
    ) -> str:
        """Process one window with resume + one expired-token restart."""
        existing = state.get_sync_state(adapter.name, window.stream_name)
        base = existing or SyncState(source_name=adapter.name, stream_name=window.stream_name)
        resume_cursor = base.cursor_or_token or window.resume_cursor
        restarted = False
        while True:
            try:
                return self._process_window(
                    adapter,
                    replace(window, resume_cursor=resume_cursor),
                    run_id,
                    mode,
                    state,
                    raw_store,
                    validator,
                    loader,
                    resolver,
                    counters,
                )
            except RetryableError as exc:
                token_expired = "resumption token" in str(exc).lower()
                if token_expired and not restarted and resume_cursor:
                    logger.warning(
                        "%s/%s: resumption token expired; restarting window from beginning",
                        adapter.name,
                        window.stream_name,
                    )
                    resume_cursor = None
                    restarted = True
                    continue
                self._record_failure(state, adapter.name, window.stream_name, run_id, mode, exc, base)
                raise

    def _process_window(
        self,
        adapter: BaseAdapter,
        window: FetchWindow,
        run_id: str,
        mode: str,
        state: StateStore,
        raw_store: RawStore,
        validator: StagingValidator,
        loader: WarehouseLoader,
        resolver: CanonicalResolver,
        counters: dict[str, int],
    ) -> str:
        # Mark attempt start (in-progress state; watermark untouched).
        attempt_state = SyncState(
            source_name=adapter.name,
            stream_name=window.stream_name,
            sync_mode=mode,
            window_start=window.window_start,
            window_end=window.window_end,
            cursor_or_token=window.resume_cursor,
            last_attempt_at=utc_now(),
            last_run_id=run_id,
            status="running",
            last_successful_watermark=self._prev_watermark(adapter.name, window.stream_name),
            last_success_at=self._prev_success_at(adapter.name, window.stream_name),
        )
        state.save_sync_state(attempt_state)
        pages = 0
        window_staging = 0
        try:
            for batch in adapter.stream_pages(run_id, window):
                parsed = adapter.parse_page(batch.local_payload_path.read_bytes())
                outcome = validator.validate_batch(
                    parsed.records, run_id=run_id, batch_id=batch.batch_id
                )
                loader.load_staging(outcome)
                loader.load_quarantine(outcome)
                resolved = resolver.resolve_batch(outcome.accepted, run_id)
                loader.load_canonical(resolved)
                loader.load_dimensions(resolved.resolved_rows)
                loader.load_facts(resolved, run_id)
                loader.refresh_citation_resolution()
                raw_store.mark_complete(batch.batch_id)
                pages += 1
                window_staging += len(outcome.accepted)
                counters["raw_records"] += batch.records_seen or 0
                counters["staging_rows"] += len(outcome.accepted)
                counters["quarantined"] += len(outcome.quarantined)
                counters["warehouse_rows"] += len(resolved.canonical_rows)
        except Exception:
            # Never advance the watermark: raw is durable, staging is idempotent.
            raise
        now = utc_now()
        state.save_sync_state_transactional(
            SyncState(
                source_name=adapter.name,
                stream_name=window.stream_name,
                sync_mode=mode,
                window_start=window.window_start,
                window_end=window.window_end,
                cursor_or_token=None,
                last_successful_watermark=window.window_end or window.window_start,
                last_success_at=now,
                last_attempt_at=now,
                last_run_id=run_id,
                status="succeeded",
                pages_completed=pages,
                records_seen=counters.get("raw_records", 0),
                records_written=window_staging,
                config_checksum=self._config_checksum(),
            )
        )
        return "succeeded"

    def _prev_watermark(self, source_name: str, stream_name: str) -> str | None:
        return _previous_watermark(self._warehouse, source_name, stream_name)

    def _prev_success_at(self, source_name: str, stream_name: str):
        return _previous_success_at(self._warehouse, source_name, stream_name)

    def _record_failure(
        self,
        state: StateStore,
        source_name: str,
        stream_name: str,
        run_id: str,
        mode: str,
        exc: Exception,
        base: SyncState,
    ) -> None:
        try:
            state.save_sync_state(
                SyncState(
                    source_name=source_name,
                    stream_name=stream_name,
                    sync_mode=mode,
                    last_attempt_at=utc_now(),
                    last_run_id=run_id,
                    status="failed",
                    error_code=type(exc).__name__,
                    error_summary=str(exc)[:500],
                    cursor_or_token=base.cursor_or_token,  # keep resume point
                    last_successful_watermark=base.last_successful_watermark,
                )
            )
        except Exception:  # noqa: BLE001 - failure bookkeeping must not mask the original error
            logger.exception("could not persist failure state for %s/%s", source_name, stream_name)

    def _build_adapter(self, name: str) -> BaseAdapter:
        source = self.settings.sources[name]
        http = HttpClient(
            timeout_seconds=source.timeout_seconds,
            max_attempts=source.retries.max_attempts,
            backoff_base_seconds=source.retries.backoff_base_seconds,
            backoff_max_seconds=source.retries.backoff_max_seconds,
            rate_delay_seconds=source.rate_delay_seconds,
            user_agent=USER_AGENT,
            sleep=self._sleep,
        )
        raw_store = RawStore(
            warehouse=self._ensure_warehouse(),
            state_store=StateStore(self._warehouse),
            raw_dir=self.settings.raw_dir,
            schema_version=self.settings.schema_version,
        )
        if name == "openalex":
            return ADAPTERS[name](source, http, raw_store, api_key=self.settings.openalex_api_key)
        if name == "crossref":
            return ADAPTERS[name](source, http, raw_store, contact_email=self.settings.crossref_contact_email)
        return ADAPTERS[name](source, http, raw_store)

    # -- window planning -----------------------------------------------------

    def _windows_for(self, name: str, mode: str) -> list[FetchWindow]:
        source = self.settings.sources[name]
        today = today_utc()
        if name == "openalex":
            if mode == "backfill":
                start_year = int((source.backfill_from_date or f"{today.year - 3}").split("-")[0])
                years = range(start_year, today.year + 1)
                return [
                    FetchWindow(f"year:{year}", f"{year}-01-01", f"{year}-12-31", mode) for year in years
                ]
            year = today.year
            return [FetchWindow(f"year:{year}", f"{year}-01-01", f"{year}-12-31", "reconciliation")]
        if name == "crossref":
            if mode == "backfill":
                start = _date_from(source.backfill_from_date or f"{today - timedelta(days=30)}")
                days = _day_range(start, today)
                return [
                    FetchWindow(f"indexdate:{day}", day, day, mode) for day in days[:BACKFILL_MAX_WINDOWS]
                ]
            end = today - timedelta(days=1)  # index-date lag day
            start = end - timedelta(days=source.sync_overlap_days)
            return [FetchWindow(f"indexdate:{start}", start.isoformat(), end.isoformat(), mode)]
        if name == "arxiv":
            start = (
                _previous_watermark(self._warehouse, name, "oai:arxiv")
                or source.backfill_from_date
                or f"{today - timedelta(days=7)}"
            )
            if mode == "sync":
                start = _shift_date(start, -source.sync_overlap_days)
            return [FetchWindow("oai:arxiv", start, None, mode)]
        if name == "datacite":
            if mode == "backfill":
                start = _date_from(source.backfill_from_date or f"{today - timedelta(days=14)}")
                days = _day_range(start, today)
                return [
                    FetchWindow(f"updated:{day}", day, day, mode) for day in days[:BACKFILL_MAX_WINDOWS]
                ]
            days = _day_range(
                _date_from(f"{today - timedelta(days=source.sync_overlap_days)}"),
                today,
            )
            return [FetchWindow(f"updated:{day}", day, day, mode) for day in days]
        if name == "zenodo":
            end = today - timedelta(days=1)
            start = _previous_watermark(self._warehouse, name, "oai:zenodo") or source.backfill_from_date
            if mode == "sync":
                start = _shift_date(start or f"{end}", -source.sync_overlap_days)
            return [FetchWindow("oai:zenodo", start, end.isoformat(), mode)]
        raise ConfigurationError(f"No window planning for source {name!r}")


def _previous_watermark(warehouse: Warehouse | None, source_name: str, stream_name: str) -> str | None:
    if warehouse is None:
        return None
    state = StateStore(warehouse).get_sync_state(source_name, stream_name)
    return state.last_successful_watermark if state else None


def _previous_success_at(warehouse: Warehouse | None, source_name: str, stream_name: str):
    if warehouse is None:
        return None
    state = StateStore(warehouse).get_sync_state(source_name, stream_name)
    return state.last_success_at if state else None


def _final_status(source_statuses: dict[str, str], gate_passed: bool) -> str:
    if not source_statuses:
        return "failed"
    all_ok = all(status == "succeeded" for status in source_statuses.values())
    any_ok = any(status == "succeeded" for status in source_statuses.values())
    if all_ok and gate_passed:
        return "succeeded"
    if any_ok or all_ok:
        # Gate failed -> partial at best; some sources failed -> partial.
        return "partial"
    return "failed"


def _new_run_id() -> str:
    import uuid

    return uuid.uuid4().hex


def _git_commit() -> str | None:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return output.stdout.strip() or None
    except Exception:  # noqa: BLE001 - commit id is informational
        return None


def _day_range(start: str, end: Any) -> list[str]:
    from datetime import date

    start_date = date.fromisoformat(str(start)[:10])
    end_date = end if isinstance(end, date) else date.fromisoformat(str(end)[:10])
    days = []
    current = start_date
    while current <= end_date:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _date_from(value: Any) -> str:
    return str(value)[:10]


def _shift_date(value: str, days: int) -> str:
    from datetime import date

    return (date.fromisoformat(str(value)[:10]) + timedelta(days=days)).isoformat()
