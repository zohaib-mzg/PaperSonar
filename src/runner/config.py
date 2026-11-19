"""Typed runner configuration loaded from ``config/sources.yml`` and environment.

Secrets never appear in the YAML. ``Settings.require_snowflake`` fails closed
with a list of missing variable *names* (never values), matching the Phase 2
production contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PRODUCTION_TARGET = "snowflake"
DEFAULT_DATABASE = "PAPERSONAR"
DEFAULT_SCHEMA = "PROJECT_STAGING"
DEFAULT_WAREHOUSE = "WH_PAPERSONAR_ELT"
DEFAULT_ROLE = "PAPERSONAR_LOADER"


class ConfigurationError(RuntimeError):
    """Raised for missing/invalid runtime configuration."""


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str | None
    user: str | None
    role: str | None
    warehouse: str | None
    database: str | None
    schema_name: str | None
    private_key: str | None
    private_key_passphrase: str | None

    @property
    def configured(self) -> bool:
        return all(
            [
                self.account,
                self.user,
                self.role,
                self.warehouse,
                self.database,
                self.schema_name,
                self.private_key,
            ]
        )

    def missing(self) -> list[str]:
        names = {
            "SNOWFLAKE_ACCOUNT": self.account,
            "SNOWFLAKE_USER": self.user,
            "SNOWFLAKE_ROLE": self.role,
            "SNOWFLAKE_WAREHOUSE": self.warehouse,
            "SNOWFLAKE_DATABASE": self.database,
            "SNOWFLAKE_SCHEMA": self.schema_name,
            "SNOWFLAKE_PRIVATE_KEY": self.private_key,
        }
        return [name for name, value in names.items() if not value]


@dataclass(frozen=True)
class SourceSettings:
    name: str
    enabled: bool
    entity: str
    page_size: int
    rate_delay_seconds: float
    timeout_seconds: float
    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    overlap_days: int
    backfill_from: str
    total_timeout_seconds: float | None = None
    adapter: dict[str, Any] = field(default_factory=dict)

    def adapter_config(self) -> dict[str, Any]:
        return {
            "page_size": self.page_size,
            "rate_delay_seconds": self.rate_delay_seconds,
            **self.adapter,
        }


@dataclass(frozen=True)
class Settings:
    sources: dict[str, SourceSettings]
    runtime: dict[str, Any]
    snowflake: SnowflakeSettings
    config_path: Path
    target: str = PRODUCTION_TARGET

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, config_path: str | None = None) -> Settings:
        values = dict(os.environ if env is None else env)
        path = Path(values.get("PAPERSONAR_CONFIG", config_path or "config/sources.yml"))
        document = _load_yaml(path)
        runtime = document.get("runtime") or {}
        sources = {
            name: _source_settings(name, block or {})
            for name, block in (document.get("sources") or {}).items()
        }
        if not sources:
            raise ConfigurationError(f"No sources configured in {path}")
        snowflake = SnowflakeSettings(
            account=values.get("SNOWFLAKE_ACCOUNT"),
            user=values.get("SNOWFLAKE_USER"),
            role=values.get("SNOWFLAKE_ROLE", DEFAULT_ROLE),
            warehouse=values.get("SNOWFLAKE_WAREHOUSE", DEFAULT_WAREHOUSE),
            database=values.get("SNOWFLAKE_DATABASE", DEFAULT_DATABASE),
            schema_name=values.get("SNOWFLAKE_SCHEMA", DEFAULT_SCHEMA),
            private_key=values.get("SNOWFLAKE_PRIVATE_KEY"),
            private_key_passphrase=values.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
        )
        return cls(
            sources=sources,
            runtime=runtime,
            snowflake=snowflake,
            config_path=path,
            target=values.get("PAPERSONAR_TARGET", PRODUCTION_TARGET),
        )

    @property
    def raw_dir(self) -> Path:
        return Path(str(self.runtime.get("raw_dir", "data/extract")))

    @property
    def target_file_bytes(self) -> int:
        return int(self.runtime.get("target_file_bytes", 134_217_728))

    @property
    def max_windows_per_run(self) -> int:
        return int(self.runtime.get("max_windows_per_run", 60))

    @property
    def user_agent(self) -> str:
        configured = str(
            self.runtime.get("user_agent", "PaperSonar/0.3 (research metadata extraction)")
        )
        contact = os.environ.get("CROSSREF_CONTACT_EMAIL")
        return configured.replace("CROSSREF_CONTACT_EMAIL", contact or "no-contact@example.org")

    def enabled_sources(self) -> list[str]:
        return [name for name, source in self.sources.items() if source.enabled]

    def require_snowflake(self) -> None:
        if self.target != PRODUCTION_TARGET:
            raise ConfigurationError(
                f"PAPERSONAR_TARGET must be {PRODUCTION_TARGET!r}; got {self.target!r}. "
                "There is no production fallback database."
            )
        missing = self.snowflake.missing()
        if missing:
            raise ConfigurationError(
                "Snowflake is mandatory for extraction/load. Missing: " + ", ".join(missing)
            )

    def require_source(self, name: str) -> SourceSettings:
        try:
            source = self.sources[name]
        except KeyError as exc:
            raise ConfigurationError(
                f"Unknown source {name!r}; configured: {', '.join(sorted(self.sources))}"
            ) from exc
        if not source.enabled:
            raise ConfigurationError(f"Source {name!r} is disabled in {self.config_path}")
        return source


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    return document


def _source_settings(name: str, block: dict[str, Any]) -> SourceSettings:
    adapter_keys = {
        key: value
        for key, value in block.items()
        if key
        not in {
            "enabled",
            "entity",
            "page_size",
            "rate_delay_seconds",
            "timeout_seconds",
            "max_attempts",
            "backoff_base_seconds",
            "backoff_max_seconds",
            "overlap_days",
            "backfill_from",
            "total_timeout_seconds",
        }
    }
    total_timeout = block.get("total_timeout_seconds")
    return SourceSettings(
        name=name,
        enabled=bool(block.get("enabled", True)),
        entity=str(block.get("entity", "record")),
        page_size=int(block.get("page_size", 100)),
        rate_delay_seconds=float(block.get("rate_delay_seconds", 0.0)),
        timeout_seconds=float(block.get("timeout_seconds", 60)),
        max_attempts=int(block.get("max_attempts", 4)),
        backoff_base_seconds=float(block.get("backoff_base_seconds", 2)),
        backoff_max_seconds=float(block.get("backoff_max_seconds", 60)),
        overlap_days=int(block.get("overlap_days", 2)),
        backfill_from=str(block.get("backfill_from", "2024-01-01")),
        total_timeout_seconds=float(total_timeout) if total_timeout is not None else None,
        adapter=adapter_keys,
    )


def load_taxonomy(path: Path = Path("config/taxonomy.yml")) -> dict[str, Any]:
    """Load the taxonomy contract (used by static contract tests)."""
    return _load_yaml(path)


def load_quality_rules(path: Path = Path("config/quality_rules.yml")) -> dict[str, Any]:
    """Load the data-quality contract (used by static contract tests)."""
    return _load_yaml(path)
