"""Tests for fail-closed configuration validation."""

import pytest

from papersonar.config import Settings
from papersonar.errors import ConfigurationError

SNOWFLAKE_FULL = {
    "SNOWFLAKE_ACCOUNT": "xy12345.eu-central-1",
    "SNOWFLAKE_USER": "svc_papersonar",
    "SNOWFLAKE_ROLE": "PAPERSONAR_INGEST",
    "SNOWFLAKE_WAREHOUSE": "PAPERSONAR_WH",
    "SNOWFLAKE_DATABASE": "PAPERSONAR",
    "SNOWFLAKE_SCHEMA": "INGEST",
    "SNOWFLAKE_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----",
}


def base_env(**overrides):
    env = {
        "PAPERSONAR_TARGET": "snowflake",
        "PAPERSONAR_RAW_DIR": "data/raw-test",
        **SNOWFLAKE_FULL,
    }
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


class TestTarget:
    def test_missing_target_rejected(self):
        env = base_env()
        del env["PAPERSONAR_TARGET"]
        with pytest.raises(ConfigurationError, match="PAPERSONAR_TARGET"):
            Settings.from_env(env)

    def test_blank_target_rejected(self):
        with pytest.raises(ConfigurationError, match="PAPERSONAR_TARGET"):
            Settings.from_env(base_env(PAPERSONAR_TARGET="   "))

    def test_postgres_rejected(self):
        with pytest.raises(ConfigurationError, match="no production fallback"):
            Settings.from_env(base_env(PAPERSONAR_TARGET="postgres"))

    def test_sqlite_rejected(self):
        with pytest.raises(ConfigurationError, match="PAPERSONAR_TARGET"):
            Settings.from_env(base_env(PAPERSONAR_TARGET="sqlite"))

    def test_snowflake_accepted(self):
        settings = Settings.from_env(base_env())
        assert settings.target == "snowflake"


class TestSnowflakeRequirement:
    def test_require_snowflake_lists_missing(self):
        env = base_env()
        for key in SNOWFLAKE_FULL:
            env[key] = ""
        settings = Settings.from_env(env)
        with pytest.raises(ConfigurationError) as excinfo:
            settings.require_snowflake()
        message = str(excinfo.value)
        for key in SNOWFLAKE_FULL:
            assert key in message

    def test_require_snowflake_ok(self):
        Settings.from_env(base_env()).require_snowflake()

    def test_private_key_path_resolution(self, tmp_path):
        key_file = tmp_path / "rsa_key.p8"
        key_file.write_text("-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----", encoding="utf-8")
        settings = Settings.from_env(base_env(SNOWFLAKE_PRIVATE_KEY=str(key_file)))
        assert b"BEGIN PRIVATE KEY" in settings.snowflake.private_key_pem()

    def test_private_key_missing_path_fails(self):
        settings = Settings.from_env(base_env(SNOWFLAKE_PRIVATE_KEY="Z:/no/such/key.pem"))
        with pytest.raises(ConfigurationError, match="SNOWFLAKE_PRIVATE_KEY"):
            settings.require_snowflake()


class TestSourceSettings:
    def test_defaults(self):
        settings = Settings.from_env(base_env())
        openalex = settings.sources["openalex"]
        assert openalex.enabled is True
        assert openalex.page_size == 100
        assert openalex.max_pages == 50
        assert openalex.timeout_seconds == 30.0
        assert openalex.retries.max_attempts == 4

    def test_disabled_source(self):
        settings = Settings.from_env(base_env(ARXIV_ENABLED="false"))
        assert settings.sources["arxiv"].enabled is False

    def test_bad_page_size_rejected(self):
        with pytest.raises(ConfigurationError, match="OPENALEX_PAGE_SIZE"):
            Settings.from_env(base_env(OPENALEX_PAGE_SIZE="0"))

    def test_bad_page_size_nonint_rejected(self):
        with pytest.raises(ConfigurationError, match="OPENALEX_PAGE_SIZE"):
            Settings.from_env(base_env(OPENALEX_PAGE_SIZE="lots"))

    def test_bad_backfill_date_rejected(self):
        with pytest.raises(ConfigurationError, match="CROSSREF_BACKFILL_FROM_DATE"):
            Settings.from_env(base_env(CROSSREF_BACKFILL_FROM_DATE="01/02/2020"))

    def test_good_backfill_date(self):
        settings = Settings.from_env(base_env(CROSSREF_BACKFILL_FROM_DATE="2020-01-01"))
        assert settings.sources["crossref"].backfill_from_date == "2020-01-01"

    def test_extras_passthrough(self):
        settings = Settings.from_env(base_env(ARXIV_SET="cs.se"))
        assert settings.sources["arxiv"].extra("SET") == "cs.se"

    def test_excludes_reserved_keys(self):
        settings = Settings.from_env(base_env(ZENODO_PAGE_SIZE="25"))
        assert "PAGE_SIZE" not in settings.sources["zenodo"].extras
        assert settings.sources["zenodo"].page_size == 25


class TestCorpusConfig:
    def test_missing_corpus_file_rejected(self):
        with pytest.raises(ConfigurationError, match="PAPERSONAR_CORPUS_CONFIG"):
            Settings.from_env(base_env(PAPERSONAR_CORPUS_CONFIG="no/such/corpus.json"))

    def test_existing_corpus_file_ok(self, tmp_path):
        corpus = tmp_path / "corpus.json"
        corpus.write_text("{}", encoding="utf-8")
        settings = Settings.from_env(base_env(PAPERSONAR_CORPUS_CONFIG=str(corpus)))
        assert settings.corpus_config_path == str(corpus)
