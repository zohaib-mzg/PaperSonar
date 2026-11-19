# 08. Security, Free-Only Costs, and Operations

## Free-only policy

- Use public metadata APIs and free/open-source libraries.
- Do not use paid API endpoints or paid data services.
- Snowflake is mandatory. Use only an account/trial/credits that are available at no cost and configure strict usage safeguards. Never activate a paid plan or paid resource without explicit user authorization.
- Do not add a payment method or accept a paid upgrade as part of automated setup.
- If no free Snowflake account/trial/credits are available or they expire, stop production deployment and report BLOCKED. Do not replace Snowflake with PostgreSQL, SQLite, or local files.
- GitHub Actions usage is subject to GitHub's current plan limits. Do not promise unlimited free execution.
- Respect provider rate limits, API terms, robots/usage rules and attribution requirements.

## Secret handling

- `.env`, private keys, credentials, raw auth headers and tokens must be ignored by Git.
- `.env.example` contains placeholders only.
- Use GitHub Actions secrets for workflow credentials.
- Redact authorization headers, passwords, private keys, key passphrases, and any secret query parameters from logs.
- Never print the environment wholesale.
- Never include secrets in exception text or artifact names.
- Use least-privilege database roles.
- Rotate any credential that was accidentally committed; removing it from a later commit is not sufficient.

## Data handling

- Metadata-only collection. No full-text PDF downloads.
- Store raw metadata with source, timestamp, payload hash and attribution.
- Keep provider licensing/terms in the source register.
- Avoid committing large raw datasets. Use fixtures for tests and document local storage.
- Avoid public workflow artifacts containing source payloads unless the project has reviewed licensing and privacy implications.
- Preserve source-provided links and identifiers.

## Operational runbook

### Normal scheduled run
1. Validate configuration and required secrets.
2. Acquire the concurrency lock.
3. Create an ETL run record.
4. Read each source's durable checkpoint.
5. Fetch bounded incremental windows/reconciliation partitions.
6. Persist raw page and manifest.
7. Parse and validate into staging.
8. Upsert canonical identities and dimensions.
9. Load facts/bridges.
10. Run quality checks.
11. Commit successful checkpoint advancement only after durable completion.
12. Record source and global run status.
13. Publish concise run summary.

### If a source fails
1. Check the source-specific error and last successful watermark.
2. Confirm the failed window was not marked complete.
3. Fix credentials/configuration or wait for provider recovery.
4. Replay stored raw payloads first if the failure occurred after retrieval.
5. Retry the same bounded window.
6. Verify idempotency and quality checks.
7. Do not reset all source checkpoints to solve one source's issue.

### If warehouse load fails
1. Preserve raw and staging batches.
2. Inspect transaction/run status.
3. Re-run the idempotent load for the affected batch.
4. Verify fact grain and foreign keys.
5. Advance checkpoint only when the documented durability contract is satisfied.

### Snowflake outage handling
- Run deterministic tests with fixtures and a mocked Snowflake adapter.
- Disable production ingestion and warehouse loading until connectivity is restored.
- Do not switch to another database or activate paid resources automatically.
- Do not delete checkpoints.
- Resume only after Snowflake connectivity and permissions are restored.

## Monitoring and alerts

At minimum, the workflow summary should report:
- run ID and commit;
- source success/partial/failure;
- records seen/written/quarantined;
- checkpoint/watermark before and after;
- elapsed time;
- quality gate status;
- Snowflake account/warehouse/schema identifiers (never secrets) and whether the Snowflake load completed.

Do not send email, Slack or third-party alerts requiring new services in Phase 2 unless already configured and free.
