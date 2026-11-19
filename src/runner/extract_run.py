"""Extraction runner: fetch pages, write gzip NDJSON shards, upload and register.

The runner is deliberately thin. It does not interpret source fields. It only
enforces the extraction contract: deterministic shard names, checksum capture,
staged-file verification, batch state transitions, and no watermark movement
(watermarks advance inside Snowflake only after publication).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from extract.base import (
    FetchWindow,
    ShardResult,
    batch_id_for,
    merge_oversize,
    ndjson_line,
    oversized,
    relative_shard_path,
    write_ndjson_gzip,
)
from extract.http import HttpClient, RetryableHttpError
from extract.registry import build_adapter
from runner.config import ConfigurationError, Settings
from runner.snowflake import SnowflakeClient

logger = logging.getLogger(__name__)


@dataclass
class ExtractionReport:
    batch_id: str
    source_name: str
    entity_name: str
    mode: str
    window_start: str
    window_end: str
    status: str = "extracting"
    file_count: int = 0
    record_count: int = 0
    oversize_count: int = 0
    shards: list[dict[str, Any]] = field(default_factory=list)
    task_triggered: bool = False
    dry_run: bool = False
    skip_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_name": self.source_name,
            "entity_name": self.entity_name,
            "mode": self.mode,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "status": self.status,
            "file_count": self.file_count,
            "record_count": self.record_count,
            "oversize_count": self.oversize_count,
            "shards": self.shards,
            "task_triggered": self.task_triggered,
            "dry_run": self.dry_run,
            "skip_reason": self.skip_reason,
        }


def run_extraction(
    settings: Settings,
    source_name: str,
    window: FetchWindow,
    *,
    dry_run: bool = False,
    force: bool = False,
    execute_task: bool = True,
    client: SnowflakeClient | None = None,
) -> ExtractionReport:
    """Extract one window and (unless ``dry_run``) load it to the raw stage."""
    source = settings.require_source(source_name)
    adapter_config = source.adapter_config()
    # A page cap truncates the window. The runner would still mark the batch
    # loaded and clear its cursor, silently losing the rest of the window.
    if adapter_config.get("max_pages") and not dry_run:
        raise ConfigurationError(
            f"{source_name}: 'max_pages' is a test-only setting and requires --dry-run; "
            "remove it from config/sources.yml for real runs"
        )
    batch_id = batch_id_for(source_name, source.entity, window.window_start, window.window_end)
    report = ExtractionReport(
        batch_id=batch_id,
        source_name=source_name,
        entity_name=source.entity,
        mode=window.mode,
        window_start=window.window_start,
        window_end=window.window_end,
        dry_run=dry_run,
    )

    snowflake = client
    existing = None
    if not dry_run:
        if snowflake is None:
            snowflake = SnowflakeClient.from_settings(settings)
        existing = snowflake.get_batch(batch_id)
        if existing and existing["STATUS"] in ("LOADED", "PROCESSING", "PUBLISHED") and not force:
            report.status = "skipped"
            report.skip_reason = (
                f"batch already {existing['STATUS']}; rerun with --force to re-extract"
            )
            logger.info("%s: %s", batch_id, report.skip_reason)
            return report
        if existing and force and existing["STATUS"] in ("PROCESSING", "PUBLISHED"):
            raise ConfigurationError(
                f"{batch_id}: batch is {existing['STATUS']}; refusing --force because "
                "an in-flight or published batch is immutable"
            )

    # Resume only an interrupted batch. --force always starts a clean window so
    # a changed filter or page size cannot resume against a stale cursor.
    resumable = (
        not dry_run
        and existing is not None
        and existing["STATUS"] in ("EXTRACTING", "FAILED")
        and not force
    )

    # A crash can happen after the last shard is durable but before the final
    # LOADED transition. A non-empty batch with a NULL cursor has exhausted its
    # window, so finish the transition instead of re-fetching (and duplicating).
    if (
        resumable
        and existing is not None
        and int(existing.get("FILE_COUNT") or 0) > 0
        and existing.get("CURSOR_END") is None
    ):
        report.file_count = int(existing["FILE_COUNT"])
        report.record_count = int(existing.get("RECORD_COUNT") or 0)
        report.status = "loaded"
        if snowflake is not None:
            snowflake.mark_batch_loaded(batch_id, report.file_count, report.record_count)
            if execute_task:
                snowflake.execute_root_task()
                report.task_triggered = True
        logger.info(
            "%s: already exhausted (%d files, %d records); marked LOADED",
            batch_id,
            report.file_count,
            report.record_count,
        )
        return report

    resume_cursor = (
        str(existing["CURSOR_END"])
        if resumable and existing is not None and existing.get("CURSOR_END")
        else None
    )
    started_shards = (
        int(existing.get("FILE_COUNT") or 0) if resumable and existing is not None else 0
    )
    started_records = (
        int(existing.get("RECORD_COUNT") or 0) if resumable and existing is not None else 0
    )

    if not dry_run and snowflake is not None:
        if force and existing is not None:
            snowflake.clear_batch_outputs(
                batch_id,
                f"{source_name}/{source.entity}/{window.window_start}_{window.window_end}",
            )
        snowflake.register_batch(
            batch_id=batch_id,
            source_name=source_name,
            entity_name=source.entity,
            mode=window.mode,
            window_start=window.window_start,
            window_end=window.window_end,
            cursor_start=resume_cursor,
        )

    adapter = build_adapter(
        source_name,
        adapter_config,
        openalex_api_key=_env("OPENALEX_API_KEY"),
        crossref_contact_email=_env("CROSSREF_CONTACT_EMAIL"),
    )
    http = HttpClient(
        timeout_seconds=source.timeout_seconds,
        max_attempts=source.max_attempts,
        backoff_base_seconds=source.backoff_base_seconds,
        backoff_max_seconds=source.backoff_max_seconds,
        rate_delay_seconds=source.rate_delay_seconds,
        user_agent=settings.user_agent,
        # Optional per-source override; HttpClient defaults to 4 x timeout_seconds.
        total_timeout_seconds=source.total_timeout_seconds,
    )

    oversize: list[dict[str, Any]] = []

    logger.info(
        "%s: extracting %s..%s (dry_run=%s, resume_cursor=%s, files=%d, records=%d)",
        batch_id,
        window.window_start,
        window.window_end,
        dry_run,
        "yes" if resume_cursor else "no",
        started_shards,
        started_records,
    )
    try:
        report.record_count, report.file_count = _extract_pages(
            settings=settings,
            adapter=adapter,
            http=http,
            window=window,
            batch_id=batch_id,
            report=report,
            snowflake=snowflake,
            resume_cursor=resume_cursor,
            started_shards=started_shards,
            started_records=started_records,
            dry_run=dry_run,
            oversize=oversize,
        )
        report.oversize_count = len(oversize)
        report.status = "extracted" if dry_run else "loaded"
        if not dry_run and snowflake is not None:
            snowflake.mark_batch_loaded(batch_id, report.file_count, report.record_count)
            if execute_task:
                snowflake.execute_root_task()
                report.task_triggered = True
    except (Exception, KeyboardInterrupt) as exc:
        # KeyboardInterrupt is included so a Ctrl+C does not leave the batch
        # stuck in 'extracting'; it is re-raised below.
        report.status = "failed"
        if not dry_run and snowflake is not None:
            snowflake.mark_batch_failed(batch_id, f"{type(exc).__name__}: {exc}")
        raise
    return report


def _extract_pages(
    *,
    settings: Settings,
    adapter: Any,
    http: HttpClient,
    window: FetchWindow,
    batch_id: str,
    report: ExtractionReport,
    snowflake: SnowflakeClient | None,
    resume_cursor: str | None,
    started_shards: int,
    started_records: int,
    dry_run: bool,
    oversize: list[dict[str, Any]],
) -> tuple[int, int]:
    shard_number = started_shards + 1
    shard_start_cursor = resume_cursor
    pending_records: list[dict[str, Any]] = []
    pending_bytes = 0
    # Cursor that fetched the current page; it becomes the resume point when a
    # shard is rolled before this page's records are added.
    fetch_cursor = resume_cursor
    total_records = started_records
    files = started_shards

    for page in _pages_with_restart(adapter, http, window, resume_cursor, batch_id):
        request_params = (page.request or {}).get("params") or {}
        page_cursor = request_params.get("cursor")
        if page_cursor is None:
            page_cursor = fetch_cursor

        page_records: list[dict[str, Any]] = []
        page_bytes = 0
        for record in page.records:
            if oversized(record):
                merge_oversize(oversize, record)
                if not dry_run and snowflake is not None:
                    entry = oversize[-1]
                    snowflake.register_oversize(
                        batch_id=batch_id,
                        source_name=window.source_name,
                        entity_name=window.entity_name,
                        record_sha256=entry["record_sha256"],
                        detail=entry,
                    )
                continue
            page_records.append(record)
            page_bytes += len(ndjson_line(record)) + 1

        # Roll before adding a page that would exceed the target. A page is the
        # smallest resumable cursor unit, so shards never cross a page boundary;
        # at most one page (100 works) can push a shard past the target.
        if pending_records and pending_bytes + page_bytes > settings.target_file_bytes:
            shard = _flush_shard(
                settings=settings,
                window=window,
                batch_id=batch_id,
                shard_number=shard_number,
                records=pending_records,
                cursor_start=shard_start_cursor,
                cursor_end=page_cursor,
                snowflake=snowflake,
                dry_run=dry_run,
                report=report,
            )
            files += 1
            total_records += shard.record_count
            report.shards.append(
                {
                    "file": shard.relative_path,
                    "records": shard.record_count,
                    "bytes": shard.size_bytes,
                    "checksum": shard.checksum,
                }
            )
            if not dry_run and snowflake is not None:
                snowflake.update_batch_progress(batch_id, page_cursor, files, total_records)
            shard_number += 1
            shard_start_cursor = page_cursor
            pending_records = []
            pending_bytes = 0

        pending_records.extend(page_records)
        pending_bytes += page_bytes
        fetch_cursor = page.next_cursor

    if pending_records:
        shard = _flush_shard(
            settings=settings,
            window=window,
            batch_id=batch_id,
            shard_number=shard_number,
            records=pending_records,
            cursor_start=shard_start_cursor,
            cursor_end=None,
            snowflake=snowflake,
            dry_run=dry_run,
            report=report,
        )
        files += 1
        total_records += shard.record_count
        report.shards.append(
            {
                "file": shard.relative_path,
                "records": shard.record_count,
                "bytes": shard.size_bytes,
                "checksum": shard.checksum,
            }
        )

    if not dry_run and snowflake is not None:
        # NULL is the durable "window exhausted" marker. Persist it even when
        # the window produced no shard (zero records or all records oversized).
        snowflake.update_batch_progress(batch_id, None, files, total_records)

    return total_records, files


def _pages_with_restart(
    adapter: Any,
    http: HttpClient,
    window: FetchWindow,
    resume_cursor: str | None,
    batch_id: str,
):
    """Yield pages; restart the window once when an OAI token has expired."""
    cursor = resume_cursor
    restarted = False
    while True:
        try:
            yield from adapter.iter_pages(http, window, cursor)
            return
        except RetryableHttpError as exc:
            if _is_expired_token(exc) and not restarted and cursor:
                logger.warning("%s: resumption token expired; restarting window", batch_id)
                cursor = None
                restarted = True
                continue
            raise


def _flush_shard(
    *,
    settings: Settings,
    window: FetchWindow,
    batch_id: str,
    shard_number: int,
    records: Iterable[dict[str, Any]],
    cursor_start: str | None,
    cursor_end: str | None,
    snowflake: SnowflakeClient | None,
    dry_run: bool,
    report: ExtractionReport,
) -> ShardResult:
    relative_path = relative_shard_path(
        window.source_name,
        window.entity_name,
        window.window_start,
        window.window_end,
        shard_number,
    )
    local_path = settings.raw_dir / relative_path
    checksum, size_bytes, record_count = write_ndjson_gzip(local_path, records)
    shard = ShardResult(
        relative_path=relative_path,
        local_path=local_path,
        checksum=checksum,
        size_bytes=size_bytes,
        record_count=record_count,
    )
    if dry_run or snowflake is None:
        logger.info("dry-run wrote %s (%d records)", local_path, record_count)
        return shard

    stage_dir = relative_path.rsplit("/", 1)[0]
    file_name = relative_path.rsplit("/", 1)[-1]
    upload = snowflake.put_file(local_path, stage_dir)
    snowflake.verify_staged_file(stage_dir, file_name, size_bytes, upload=upload)
    snowflake.register_manifest(
        batch_id=batch_id,
        source_name=window.source_name,
        entity_name=window.entity_name,
        file_name=relative_path,
        checksum=checksum,
        size_bytes=size_bytes,
        record_count=record_count,
        window_start=window.window_start,
        window_end=window.window_end,
        cursor_start=cursor_start,
        cursor_end=cursor_end,
    )
    logger.info("uploaded %s (%d records, %d bytes)", relative_path, record_count, size_bytes)
    return shard


def _is_expired_token(exc: RetryableHttpError) -> bool:
    return "resumption token" in str(exc).lower()


def _env(name: str) -> str | None:
    import os

    value = os.environ.get(name)
    return value or None


def plan_and_run(
    settings: Settings,
    source_name: str,
    mode: str,
    windows: list[FetchWindow],
    *,
    dry_run: bool = False,
    force: bool = False,
    execute_task: bool = True,
) -> list[ExtractionReport]:
    """Run every planned window sequentially and return per-window reports.

    Extraction loads all windows first, then a single drain loop triggers the
    Snowflake task graph once per LOADED batch. Waiting between windows wastes
    API time and would leave earlier windows unprocessed when only the last
    window triggered the graph.
    """
    if not windows:
        raise ConfigurationError(f"No windows planned for {source_name}/{mode}")
    client: SnowflakeClient | None = None
    try:
        if not dry_run:
            client = SnowflakeClient.from_settings(settings)
        reports = [
            run_extraction(
                settings,
                source_name,
                window,
                dry_run=dry_run,
                force=force,
                execute_task=False,
                client=client,
            )
            for window in windows
        ]
        if execute_task and not dry_run and client is not None:
            rounds = client.drain_batches()
            if reports:
                reports[-1].task_triggered = True
            logger.info("drained %d ELT trigger round(s) for %s/%s", rounds, source_name, mode)
        return reports
    finally:
        if client is not None:
            client.close()
