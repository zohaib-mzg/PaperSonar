# Snowflake and zero-cost deployment decision

**Decision:** PostgreSQL is the required reproducible baseline. Snowflake is an optional compatibility target, not a dependency.

## Reason

The project requirement is that every necessary part remains free. Snowflake may offer a time-limited trial or educational credits, but the design must not assume a permanent free tier. A trial expiring must not block extraction, ETL, SQL analytics, or evaluation.

## Portable design rules

- Use portable SQL for keys, joins, constraints, and analytical views wherever reasonable.
- Isolate platform-specific SQL and loading syntax in separate scripts/adapters.
- Keep raw data and manifests in ordinary local files; do not require paid object storage.
- Avoid proprietary warehouse-only features in core transformation logic.
- Maintain a PostgreSQL run path for all essential requirements and tests.
- If Snowflake trial access is available, test it only on a small representative subset and document trial expiry, credits, and stop-before-charge controls.
- Never store credentials in Git or diagrams. No payment method is part of the project plan.

## Acceptance rule

PaperSonar is considered reproducible only if the core pipeline and analytical outputs can be rebuilt locally without Snowflake. Snowflake compatibility is a useful demonstration, not the zero-budget foundation.
