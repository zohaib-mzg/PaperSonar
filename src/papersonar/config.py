"""Typed runtime configuration with fail-closed validation.

The production target is fixed to Snowflake. Any other value — postgres,
sqlite, local, blank or unknown — is rejected at startup. Deterministic unit
tests inject a mocked Snowflake adapter as a testing technique; that does not
change the deployment target and no other database adapter exists in this
package.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from papersonar.errors import ConfigurationError

PRODUCTION_TARGET = "snowflake"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_FALSE_VALUES = {"0", "false", "no", "off"}

SNOWFLAKE_REQUIRED = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
    "SNOWFLAKE_PRIVATE_KEY",
)

SOURCES: tuple[str, ...] = ("openalex", "crossref", "arxiv", "datacite", "zenodo")

# Reserved per-source suffixes parsed into structured fields; everything else
# under the source prefix is passed through to the adapter as ``extras``.
_RESERVED_SUFFIXES = (
    "ENABLED",
    "PAGE_SIZE",
    "MAX_PAGES",
    "TIMEOUT_SECONDS",
    "RATE_DELAY_SECONDS",
    "SYNC_OVERLAP_DAYS",
    "BACKFILL_FROM_DATE",
    "MAX_ATTEMPTS",
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_MAX_SECONDS",
)

# Bounded, validated ranges (safe usage limits).
_PAGE_SIZE_RANGE = (1, 2000)
_MAX_PAGES_RANGE = (1, 200_000)
_TIMEOUT_RANGE = (1.0, 600.0)
_RATE_DELAY_RANGE = (0.0, 3600.0)
_OVERLAP_RANGE = (0, 90)
_ATTEMPTS_RANGE = (0, 10)
_BACKOFF_BASE_RANGE = (0.1, 600.0)
_BACKOFF_MAX_RANGE = (1.0, 3600.0)


def _clamp_error(name: str, value: object, lo: object, hi: object) -> ConfigurationError:
    return ConfigurationError(f"{name} must be between {lo} and {hi}, got {value!r}")


def _parse_bool(name: str, value: str) -> bool:
    return value.strip().lower() not in _FALSE_VALUES


def _parse_int(name: str, value: str, lo: int, hi: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {value!r}") from exc
    if parsed < lo or parsed > hi:
        raise _clamp_error(name, parsed, lo, hi)
    return parsed


def _parse_float(name: str, value: str, lo: float, hi: float) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {value!r}") from exc
    if parsed < lo or parsed > hi:
        raise _clamp_error(name, parsed, lo, hi)
    return parsed


def _parse_date(name: str, value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    text = value.strip()
    if not _DATE_RE.match(text):
        raise ConfigurationError(f"{name} must be YYYY-MM-DD, got {value!r}")
    return text


@dataclass(frozen=True)
class RetrySettings:
    """Bounded exponential-backoff retry policy."""

    max_attempts: int = 4
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 60.0


@dataclass(frozen=True)
class SourceSettings:
    """Per-source enablement, limits and raw extras."""

    name: str
    enabled: bool
    page_size: int
    max_pages: int
    timeout_seconds: float
    rate_delay_seconds: float
    sync_overlap_days: int
    backfill_from_date: str | None
    retries: RetrySettings
    extras: dict[str, str] = field(default_factory=dict)

    def extra(self, key: str, default: str | None = None) -> str | None:
        return self.extras.get(key, default)


@dataclass(frozen=True)
class SnowflakeSettings:
    """Mandatory production warehouse settings."""

    account: str
    user: str
    role: str
    warehouse: str
    database: str
    schema_name: str
    private_key: str
    private_key_passphrase: str | None

    def private_key_pem(self) -> bytes:
        """Return the private key PEM bytes from inline content or a file path."""
        value = self.private_key.strip()
        if not value:
            raise ConfigurationError("SNOWFLAKE_PRIVATE_KEY is empty")
        if "-----BEGIN" in value:
            return value.encode("utf-8")
        path = Path(value)
        if not path.is_file():
            raise ConfigurationError(
                "SNOWFLAKE_PRIVATE_KEY is neither PEM content nor a readable file path"
            )
        return path.read_bytes()


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    target: str
    snowflake: SnowflakeSettings
    sources: dict[str, SourceSettings]
    raw_dir: Path
    log_level: str
    schema_version: str
    corpus_config_path: str | None
    openalex_api_key: str | None
    crossref_contact_email: str | None

    # -- parsing ------------------------------------------------------------

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)

        target = (env.get("PAPERSONAR_TARGET") or "").strip().lower()
        if target != PRODUCTION_TARGET:
            raise ConfigurationError(
                "PAPERSONAR_TARGET must be 'snowflake' in production. "
                f"Got {target!r}. Values such as postgres, sqlite or local are "
                "rejected; there is no production fallback database."
            )

        snowflake = SnowflakeSettings(
            account=env.get("SNOWFLAKE_ACCOUNT", "").strip(),
            user=env.get("SNOWFLAKE_USER", "").strip(),
            role=env.get("SNOWFLAKE_ROLE", "").strip(),
            warehouse=env.get("SNOWFLAKE_WAREHOUSE", "").strip(),
            database=env.get("SNOWFLAKE_DATABASE", "").strip(),
            schema_name=env.get("SNOWFLAKE_SCHEMA", "").strip(),
            private_key=env.get("SNOWFLAKE_PRIVATE_KEY", ""),
            private_key_passphrase=env.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
        )

        sources = {name: _parse_source(env, name) for name in SOURCES}

        log_level = (env.get("PAPERSONAR_LOG_LEVEL") or "INFO").strip().upper()
        if log_level not in _LOG_LEVELS:
            raise ConfigurationError(
                f"PAPERSONAR_LOG_LEVEL must be one of {', '.join(_LOG_LEVELS)}, got {log_level!r}"
            )

        corpus_config_path = env.get("PAPERSONAR_CORPUS_CONFIG") or None
        if corpus_config_path and not Path(corpus_config_path).is_file():
            raise ConfigurationError(
                f"PAPERSONAR_CORPUS_CONFIG points to a missing file: {corpus_config_path}"
            )

        schema_version = (env.get("PAPERSONAR_SCHEMA_VERSION") or "1").strip()
        if not schema_version or not re.match(r"^[A-Za-z0-9._-]+$", schema_version):
            raise ConfigurationError(
                f"PAPERSONAR_SCHEMA_VERSION must be a short version token, got {schema_version!r}"
            )

        settings = cls(
            target=target,
            snowflake=snowflake,
            sources=sources,
            raw_dir=Path(env.get("PAPERSONAR_RAW_DIR") or "data/raw"),
            log_level=log_level,
            schema_version=schema_version,
            corpus_config_path=corpus_config_path,
            openalex_api_key=env.get("OPENALEX_API_KEY") or None,
            crossref_contact_email=env.get("CROSSREF_CONTACT_EMAIL") or None,
        )
        settings.validate()
        return settings

    # -- validation ----------------------------------------------------------

    def validate(self) -> None:
        """Structural validation that always applies (no network, no secrets check)."""
        if self.target != PRODUCTION_TARGET:
            raise ConfigurationError(
                f"Production target must be '{PRODUCTION_TARGET}', got {self.target!r}"
            )
        if not re.match(r"^[A-Za-z0-9._-]+$", self.schema_version):
            raise ConfigurationError(f"Invalid PAPERSONAR_SCHEMA_VERSION: {self.schema_version!r}")
        if self.log_level not in _LOG_LEVELS:
            raise ConfigurationError(f"Invalid PAPERSONAR_LOG_LEVEL: {self.log_level!r}")
        for source in self.sources.values():
            _validate_source(source)

    def require_snowflake(self) -> None:
        """Fail closed before ingestion if mandatory Snowflake settings are missing."""
        self.validate()
        missing: list[str] = []
        if not self.snowflake.account:
            missing.append("SNOWFLAKE_ACCOUNT")
        if not self.snowflake.user:
            missing.append("SNOWFLAKE_USER")
        if not self.snowflake.role:
            missing.append("SNOWFLAKE_ROLE")
        if not self.snowflake.warehouse:
            missing.append("SNOWFLAKE_WAREHOUSE")
        if not self.snowflake.database:
            missing.append("SNOWFLAKE_DATABASE")
        if not self.snowflake.schema_name:
            missing.append("SNOWFLAKE_SCHEMA")
        if not self.snowflake.private_key:
            missing.append("SNOWFLAKE_PRIVATE_KEY")
        if missing:
            raise ConfigurationError(
                "Missing mandatory Snowflake configuration: " + ", ".join(missing)
            )
        # Validate the key material is resolvable without printing it.
        try:
            self.snowflake.private_key_pem()
        except ConfigurationError as exc:
            raise ConfigurationError(f"SNOWFLAKE_PRIVATE_KEY unusable: {exc}") from exc

    # -- helpers -------------------------------------------------------------

    @property
    def secret_values(self) -> list[str]:
        """Secret strings that must be redacted from logs."""
        return [
            value
            for value in (
                self.snowflake.private_key,
                self.snowflake.private_key_passphrase,
                self.openalex_api_key,
            )
            if value
        ]


def _validate_source(source: SourceSettings) -> None:
    if not _PAGE_SIZE_RANGE[0] <= source.page_size <= _PAGE_SIZE_RANGE[1]:
        raise _clamp_error(
            f"{source.name.upper()}_PAGE_SIZE", source.page_size, *_PAGE_SIZE_RANGE
        )
    if not _MAX_PAGES_RANGE[0] <= source.max_pages <= _MAX_PAGES_RANGE[1]:
        raise _clamp_error(f"{source.name.upper()}_MAX_PAGES", source.max_pages, *_MAX_PAGES_RANGE)
    if not _TIMEOUT_RANGE[0] <= source.timeout_seconds <= _TIMEOUT_RANGE[1]:
        raise _clamp_error(
            f"{source.name.upper()}_TIMEOUT_SECONDS", source.timeout_seconds, *_TIMEOUT_RANGE
        )
    if not _RATE_DELAY_RANGE[0] <= source.rate_delay_seconds <= _RATE_DELAY_RANGE[1]:
        raise _clamp_error(
            f"{source.name.upper()}_RATE_DELAY_SECONDS",
            source.rate_delay_seconds,
            *_RATE_DELAY_RANGE,
        )
    if not _OVERLAP_RANGE[0] <= source.sync_overlap_days <= _OVERLAP_RANGE[1]:
        raise _clamp_error(
            f"{source.name.upper()}_SYNC_OVERLAP_DAYS",
            source.sync_overlap_days,
            *_OVERLAP_RANGE,
        )
    if not _ATTEMPTS_RANGE[0] <= source.retries.max_attempts <= _ATTEMPTS_RANGE[1]:
        raise _clamp_error(
            f"{source.name.upper()}_MAX_ATTEMPTS", source.retries.max_attempts, *_ATTEMPTS_RANGE
        )


def _parse_source(env: dict[str, str], name: str) -> SourceSettings:
    prefix = name.upper()
    page_size = _parse_int(f"{prefix}_PAGE_SIZE", env.get(f"{prefix}_PAGE_SIZE", "100"), *_PAGE_SIZE_RANGE)
    max_pages = _parse_int(f"{prefix}_MAX_PAGES", env.get(f"{prefix}_MAX_PAGES", "50"), *_MAX_PAGES_RANGE)
    timeout = _parse_float(
        f"{prefix}_TIMEOUT_SECONDS", env.get(f"{prefix}_TIMEOUT_SECONDS", "30"), *_TIMEOUT_RANGE
    )
    rate_delay = _parse_float(
        f"{prefix}_RATE_DELAY_SECONDS", env.get(f"{prefix}_RATE_DELAY_SECONDS", "1"), *_RATE_DELAY_RANGE
    )
    overlap = _parse_int(
        f"{prefix}_SYNC_OVERLAP_DAYS", env.get(f"{prefix}_SYNC_OVERLAP_DAYS", "1"), *_OVERLAP_RANGE
    )
    attempts = _parse_int(
        f"{prefix}_MAX_ATTEMPTS", env.get(f"{prefix}_MAX_ATTEMPTS", "4"), *_ATTEMPTS_RANGE
    )
    backoff_base = _parse_float(
        f"{prefix}_BACKOFF_BASE_SECONDS",
        env.get(f"{prefix}_BACKOFF_BASE_SECONDS", "2"),
        *_BACKOFF_BASE_RANGE,
    )
    backoff_max = _parse_float(
        f"{prefix}_BACKOFF_MAX_SECONDS",
        env.get(f"{prefix}_BACKOFF_MAX_SECONDS", "60"),
        *_BACKOFF_MAX_RANGE,
    )
    backfill_from = _parse_date(f"{prefix}_BACKFILL_FROM_DATE", env.get(f"{prefix}_BACKFILL_FROM_DATE"))
    enabled_value = env.get(f"{prefix}_ENABLED", "true")

    extras = {
        key[len(prefix) + 1 :]: value
        for key, value in env.items()
        if key.startswith(prefix + "_")
        and key[len(prefix) + 1 :] not in _RESERVED_SUFFIXES
        and key[len(prefix) + 1 :].isupper()
    }

    return SourceSettings(
        name=name,
        enabled=_parse_bool(f"{prefix}_ENABLED", enabled_value),
        page_size=page_size,
        max_pages=max_pages,
        timeout_seconds=timeout,
        rate_delay_seconds=rate_delay,
        sync_overlap_days=overlap,
        backfill_from_date=backfill_from,
        retries=RetrySettings(
            max_attempts=attempts,
            backoff_base_seconds=backoff_base,
            backoff_max_seconds=backoff_max,
        ),
        extras=extras,
    )
