# 10. Source and Runtime Configuration Reference

## Production target

- `PAPERSONAR_TARGET`: production value is fixed to `snowflake`. Reject `postgres`, `sqlite`, `local`, blank, and unknown values in production. Do not expose a production database switch.
- Unit tests may inject a mocked Snowflake adapter; this is a testing technique, not an alternate deployment target.

## Snowflake settings (mandatory in production)

- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_SCHEMA`
- `SNOWFLAKE_PRIVATE_KEY` or the exact secure authentication material required by the selected official connector
- `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` when the key is encrypted

Do not log these values. `.env.example` must contain placeholders only. In GitHub Actions, use secrets for authentication material and non-secret variables for safe runtime configuration.

## Ingestion settings

Use explicit settings for source enablement, source-specific page/batch limits, historical backfill date bounds, sync lookback/reconciliation windows, request timeouts, retry limits, concurrency, and rate-limit delays. Document defaults and validate invalid ranges at startup. A normal scheduled run must use incremental `sync`, not historical `backfill`.

## Data and operational settings

- `PAPERSONAR_RAW_DIR` may be used for local development/testing only; it must not be the sole durable raw-data location for production runs.
- Configure run IDs, parser/schema versions, retention, quarantine behavior, and logging level.
- Persist production checkpoints, run state, and manifests durably; do not rely on the GitHub runner filesystem.

## Startup validation

Production must fail before making source API calls if:

- mandatory Snowflake configuration is missing;
- the production target is not Snowflake;
- authentication fails or required permissions are absent;
- the configured resource settings violate safe usage limits; or
- required durable state tables/migrations are not ready.

Never silently fall back to PostgreSQL, SQLite, or local files. If Snowflake access is unavailable, deterministic tests can still run with fixtures and a mocked adapter, but production ingestion and acceptance must be reported as blocked.
