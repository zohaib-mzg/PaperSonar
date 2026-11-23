# 08 — Runbook and Launch

**Read after:** `07_IMPLEMENTATION_PLAN_AND_TESTS.md`  
**Owner:** launch / operations  
**Launch owner:** Team PaperSonar  
**Support:** `zohaib.mzg158@gmail.com`

This runbook starts **after development is complete**. Infrastructure is
provisioned by the owner. The code must already build without secrets.

---

## 1. Launch prerequisites

Do not start the launch sequence until all are true:

- [ ] Stages 0–11 in `07_IMPLEMENTATION_PLAN_AND_TESTS.md` are complete.
- [ ] The public SQL views and grants are ready to deploy.
- [ ] The Vercel project can build `apps/web`.
- [ ] The owner has Snowflake, Groq, Gemini, Upstash and PostHog accounts.
- [ ] The support email is monitored.
- [ ] The rollback deployment is known.
- [ ] The 150-question eval passes at ≥ 95%.
- [ ] No secret is present in git history for this work.

The site domain is the Vercel subdomain `paper-sonar.vercel.app`. No custom DNS
is required for MVP. If a custom domain is added later, use Vercel’s domain
wizard and do not change the app origin until the new origin is verified.

---

## 2. Snowflake setup

Use an administrative worksheet for one-time setup. Do **not** use
`ACCOUNTADMIN` for the application, CI or routine operation. If your org
requires `ACCOUNTADMIN` to create roles, use it only in this worksheet and
never store it anywhere.

### 2.1 Key pair

On a trusted machine outside the repository:

```powershell
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -outform pem > papersonar_public_key.p8
openssl rsa -in papersonar_public_key.p8 -pubout -out papersonar_public_key.pub
```

- Private key: `papersonar_public_key.p8` → Vercel only.
- Public key: `papersonar_public_key.pub` → Snowflake user.
- Delete local copies after upload if they are not needed for rotation.
- Never commit either file.

### 2.2 Create objects

Run the setup SQL from `02_SNOWFLAKE_PUBLIC_LAYER.md`:

1. `PAPERSONAR_PUBLIC_RO`
2. `WH_PAPERSONAR_PUBLIC`
3. `RM_PAPERSONAR_PUBLIC`
4. `SVC_PAPERSONAR_PUBLIC`
5. `RSA_PUBLIC_KEY`
6. schema/warehouse usage grants
7. role grant to service user

Set the resource-monitor credit quota to the owner’s actual free/trial
allowance. The recommended starting value is 10 credits/month with suspend at
100%.

### 2.3 Deploy views and grants

Run, in order:

```text
sql/11_public_api/01_public_views.sql
sql/11_public_api/02_public_grants.sql
```

Do not run these as the public role. Do not run `CREATE OR REPLACE` against any
existing reporting view.

### 2.4 Verify as the public role

Open a new worksheet and run:

```sql
USE ROLE PAPERSONAR_PUBLIC_RO;
USE WAREHOUSE WH_PAPERSONAR_PUBLIC;

SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_YEAR;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_CITATIONS;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_INTERSECTIONS;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_INSTITUTION_TOPIC;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_AUTHOR_ACTIVITY;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_VENUE_TOPIC;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_ACCESS_TOPIC;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_OUTPUT_SEARCH;
SELECT * FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_DATA_STATUS;
SELECT * FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY;
```

These must fail:

```sql
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH;
```

If any base-table query succeeds, **stop**. Revoke the grant, fix the role, and
repeat verification.

---

## 3. Vercel setup

### 3.1 Project

1. Create one Vercel project from the repository.
2. Set **Root Directory** to `apps/web`.
3. Framework preset: Next.js.
4. Install command: `npm ci`.
5. Build command: `npm run build`.
6. Node version: current LTS supported by Vercel.
7. Production branch: `main`.
8. Preview deployments: enabled.
9. Deployment protection: previews protected; production public.

### 3.2 Environment variables

Set for **Production** and **Preview** as appropriate.

Server-only:

```text
SNOWFLAKE_ACCOUNT
SNOWFLAKE_ACCOUNT_URL
SNOWFLAKE_PUBLIC_USER
SNOWFLAKE_PUBLIC_ROLE
SNOWFLAKE_PUBLIC_WAREHOUSE
SNOWFLAKE_DATABASE
SNOWFLAKE_SCHEMA
SNOWFLAKE_PUBLIC_PRIVATE_KEY
SNOWFLAKE_PUBLIC_PRIVATE_KEY_PASSPHRASE
GROQ_API_KEY
GROQ_MODEL
GEMINI_API_KEY
GEMINI_MODEL
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
PUBLIC_APP_ORIGIN
PUBLIC_CHAT_ENABLED
LLM_MODE
IP_HASH_SALT
SENTRY_DSN
```

Browser-safe:

```text
NEXT_PUBLIC_SITE_URL
NEXT_PUBLIC_POSTHOG_KEY
NEXT_PUBLIC_POSTHOG_HOST
```

Rules:

- `PUBLIC_APP_ORIGIN=https://paper-sonar.vercel.app`.
- `PUBLIC_CHAT_ENABLED=false` for the first deployment; turn on after smoke
  tests.
- `LLM_MODE=auto`.
- `IP_HASH_SALT` is a long random value; rotate only with a cache reset.
- Do not put any secret in `NEXT_PUBLIC_*`.
- Private key: preserve PEM newlines or store base64. Test both on preview.
- Preview and production must not share a mutable Snowflake role or key if
  possible; if they do, label the risk and rotate on schedule.

### 3.3 Domain

1. Add `paper-sonar.vercel.app` in Vercel.
2. Confirm HTTPS and the canonical redirect.
3. Set `NEXT_PUBLIC_SITE_URL=https://paper-sonar.vercel.app`.
4. No DNS change is needed for the Vercel subdomain.

### 3.4 Function limits

- Set the chat route `maxDuration` within the Vercel plan.
- Snowflake statement timeout must be lower than the route duration.
- If the plan’s function limit is too low for 30 seconds of Snowflake plus LLM
  time, reduce Snowflake timeout or narrow the metric; do not disable timeouts.

---

## 4. Provider setup

### 4.1 Groq

1. Create a free Groq account.
2. Create an API key.
3. Select a currently available free-tier chat model.
4. Set `GROQ_API_KEY` and `GROQ_MODEL`.
5. Confirm the model supports JSON output.
6. Check the provider dashboard for free-tier rate limits.

### 4.2 Gemini

1. Create a free Google AI Studio key.
2. Select a currently available free-tier Gemini Flash-class model.
3. Set `GEMINI_API_KEY` and `GEMINI_MODEL`.
4. Confirm `generateContent` works with JSON response mode.
5. Keep billing disabled. The app must not use a paid project.

### 4.3 Upstash

1. Create a Redis database in a region close to the Vercel functions.
2. Use the REST URL and token.
3. Set `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
4. Confirm `PING` succeeds from the app.
5. Keep the free tier; monitor request count.

### 4.4 PostHog

1. Create a project.
2. Set `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_HOST`.
3. Disable autocapture, session recording and heatmaps.
4. Confirm no question or answer text appears in events.
5. If PostHog is unavailable, the site must still work.

### 4.5 Sentry (optional)

1. Create a free project.
2. Set `SENTRY_DSN`.
3. Enable scrubbing for `message`, `query`, `authorization`, `cookie`, `ip`,
   `session_id`, `private_key`.
4. If absent, continue without it.

---

## 5. Deploy sequence

### 5.1 First deployment

1. Deploy with `PUBLIC_CHAT_ENABLED=false`.
2. Confirm the static site renders.
3. Confirm `/api/health` reports `not_ready` or `degraded` with missing checks.
4. Add/verify all env vars.
5. Redeploy.
6. Confirm `/api/health` is `ok`.
7. Confirm `/api/data-status` returns published data.
8. Confirm `/api/metrics` returns the catalogue.
9. Confirm `/api/topics` returns taxonomy labels.

### 5.2 Enable chat

1. Set `PUBLIC_CHAT_ENABLED=true`.
2. Redeploy.
3. Ask five questions from `03_METRIC_CATALOGUE_AND_QUESTIONS.md`.
4. Check the inline terminal evidence receipts.
5. Confirm a series answer shows an inline terminal chart with table fallback.
6. Test a clarification question.
7. Test a below-threshold question (no chart).
8. Test a title search (no chart).
9. Test a rate-limit response from a second network.
10. Test mobile layout and keyboard.
11. Test `+ New chat` restores the welcome state and chips.

### 5.3 Smoke-test matrix

| Test | Expected |
|---|---|
| `GET /api/health` | `ok` |
| `GET /api/data-status` | latest batch and snapshot |
| `GET /api/metrics` | 24 metric IDs |
| `GET /api/topics` | taxonomy v3 labels |
| “Which topics grew fastest in 2025?” | M01 answer + receipt + inline chart |
| “How many citations does RAG have?” | M04 answer, RAG category |
| “Compare AI/ML and physics.” | comparison with two receipts |
| “Find papers about RAG.” | title results, limit 20 |
| “Why did this fail?” | unsupported/refusal, no SQL |
| 21st request in an hour | 429 with retry message |
| Base-table query as public role | denied |

### 5.4 Manual data validation

For 20 questions, compare the answer to a direct SQL query in the public
worksheet. Record the question, metric, as-of date and any mismatch.

Do not launch with a known numeric mismatch. If a metric is wrong, disable the
metric or chat and fix it.

---

## 6. Launch checklist

### T-1 day

- [ ] Freeze non-essential changes.
- [ ] Run the full Python and web test suites.
- [ ] Run the 150-question eval.
- [ ] Verify Snowflake resource monitor.
- [ ] Verify provider quotas.
- [ ] Check support email access.
- [ ] Confirm rollback deployment.
- [ ] Confirm `PUBLIC_CHAT_ENABLED` control.
- [ ] Confirm no secrets in git or client bundles.
- [ ] Run base-table deny tests.
- [ ] Check mobile layout on a real phone.

### T-0

- [ ] Merge the release commit.
- [ ] Deploy production.
- [ ] `/api/health` = `ok`.
- [ ] `/api/data-status` matches Snowflake.
- [ ] Ask 10 launch questions.
- [ ] Open the site logged out in a private window.
- [ ] Verify no login prompt.
- [ ] Verify terminal header, footer and `RESEARCH INTELLIGENCE` mark.
- [ ] Verify inline answer to “How was this calculated?” includes caveats and
  support email from site metadata.
- [ ] Verify PostHog `terminal_loaded` event (if enabled).
- [ ] Post the launch note to the owner.

### T+1 hour

- [ ] Error rate < 5%.
- [ ] p95 latency < 8 s.
- [ ] No 5xx storm.
- [ ] Rate-limit count sane.
- [ ] Groq fallback rate sane.
- [ ] Snowflake monitor below 75%.
- [ ] No secret or raw question in logs.

### T+24 hours

- [ ] Review top questions and failures.
- [ ] Review feedback.
- [ ] Check cache hit rate.
- [ ] Check quota dashboards.
- [ ] Check database credits.
- [ ] Decide whether to adjust limits or prompts.

---

## 7. Monitoring and alerts

Watch:

- `/api/health`
- 5xx rate
- p95 latency
- 429 rate
- provider fallback rate
- provider quota errors
- Snowflake timeouts
- Snowflake resource-monitor percentage
- cache errors
- PostHog page views
- feedback counts

Configure alerts or a daily manual check. The owner must receive the 75% and 90%
resource-monitor notifications.

---

## 8. Incident runbooks

### 8.1 Snowflake authentication failure

Symptoms: all chat requests 503; health Snowflake check fails.

Actions:

1. Confirm the service user exists and is not disabled.
2. Confirm the public key fingerprint matches the private key.
3. Confirm the JWT `iss`/`sub` format.
4. Confirm the role and warehouse grants.
5. Test `SELECT 1` from a trusted client with the public role.
6. If the key is suspect, rotate immediately.
7. Keep `PUBLIC_CHAT_ENABLED=false` until verified.

### 8.2 Public role can read a base table

This is SEV-1.

1. Set `PUBLIC_CHAT_ENABLED=false`.
2. `REVOKE` the grant.
3. Rotate the service user key.
4. Check whether any request returned raw rows.
5. Review logs and cache.
6. Fix the view/role model.
7. Re-run deny tests.
8. Re-enable only after owner sign-off.

### 8.3 Groq quota or outage

1. Confirm the fallback to Gemini occurs once.
2. If Gemini is healthy, keep serving.
3. If both fail, return the quota message.
4. Do not add a paid key or upgrade.
5. Check the provider dashboard for a reset time.
6. Reduce cache TTL only if it improves reuse; do not disable cache.

### 8.4 Gemini quota or outage

1. Groq remains primary.
2. If Groq is healthy, no user impact.
3. If both fail, degrade gracefully.
4. Do not switch to a paid model.

### 8.5 Redis/Upstash failure

1. Chat returns 503; do not bypass rate limits in production.
2. Check Upstash status and credentials.
3. Confirm the database is not over quota.
4. Restore or rotate the token.
5. Clear stale circuit-breaker keys only after provider health is confirmed.

### 8.6 Wrong answer reported

1. Capture the `request_id` and metric ID from the feedback record.
2. Reproduce with the same filters.
3. Compare to the public SQL view.
4. If the view is wrong, disable the metric and fix the view.
5. If the resolver is wrong, add a regression test and fix the alias/guard.
6. If the LLM prose is wrong, rely on deterministic fallback and fix the
   validator/prompt.
7. Reply to the reporter if contact is available.

### 8.7 Site down or Vercel failure

1. Check Vercel status and deployment logs.
2. Promote the previous deployment.
3. If the failure is only chat, set `PUBLIC_CHAT_ENABLED=false`; keep the
   terminal shell and status dot available.
4. Do not roll back Snowflake existing views.

### 8.8 Secret exposure

This is SEV-1.

1. Disable chat.
2. Revoke the exposed Snowflake key, Groq key, Gemini key and Upstash token as
   applicable.
3. Rotate all.
4. Remove the secret from the repository and history if committed.
5. Review logs for use.
6. Notify the owner.
7. Re-enable only after a clean audit.

### 8.9 Cost spike

1. Check resource monitor and provider dashboards.
2. Set `PUBLIC_CHAT_ENABLED=false` if spend is possible.
3. Confirm the zero-budget rule: no paid overage.
4. Reduce limits or cache TTLs.
5. Identify the traffic source without logging IPs.
6. Do not restore chat until the quota is understood.

---

## 9. Rollback

### Application

- Vercel: promote the last known-good deployment.
- Keep the database views unchanged.
- If a new UI build is bad, roll back the deployment, not the data.

### Snowflake

- The public views are additive.
- If a new view is bad, revoke its grant or drop/recreate only that
  `VW_PUBLIC_*` view.
- Never roll back or replace an existing reporting view.
- Never run a destructive operation against bronze/silver/staging/DW tables.

### Chat

- `PUBLIC_CHAT_ENABLED=false` is the first switch.
- `LLM_MODE=off` disables provider calls if the issue is LLM-specific.
- The terminal shell, status dot and inline methodology answers remain
  available.

---

## 10. Key rotation

### Snowflake

1. Generate a new key pair.
2. Set `RSA_PUBLIC_KEY_2` on the service user.
3. Update `SNOWFLAKE_PUBLIC_PRIVATE_KEY` in Vercel.
4. Redeploy.
5. Smoke-test a metric.
6. Unset the old `RSA_PUBLIC_KEY`.
7. Record the date and operator.

### Providers

1. Create a new Groq/Gemini/Upstash key.
2. Update Vercel.
3. Redeploy.
4. Smoke-test.
5. Revoke the old key.
6. Check no old key remains in local files.

Rotate immediately after any suspected exposure, regardless of schedule.

---

## 11. Post-launch maintenance

### Daily (first week)

- health and error rate
- p95 latency
- quota dashboards
- resource monitor
- 3 random questions
- feedback review

### Weekly

- review failed questions
- add regression cases
- check dependencies
- check PostHog for unexpected data
- confirm no secret in logs
- review cache hit rate

### Monthly

- run the 150-question eval
- review free-tier changes
- review resource usage
- update model IDs if retired
- review public grants
- review support themes

### Quarterly

- rotate Snowflake key
- re-run deny tests
- review CSP and dependency lockfile
- review taxonomy and aliases
- update this runbook

---

## 12. Support triage

Categories:

1. **Wrong number** — reproduce, compare to view, disable metric if needed.
2. **Wrong topic** — alias/resolver bug; add regression test.
3. **Missing data** — check publication status; explain coverage.
4. **Unsupported question** — add metric only if it fits the catalogue.
5. **Performance** — check cache, query plan, row count.
6. **Security/privacy** — follow SEV-1/2 runbook immediately.

Do not ask users for screenshots containing secrets. Do not request personal
data.

---

## 13. Final launch sign-off

- [ ] Snowflake public role verified and deny-tested.
- [ ] Vercel production deployed at `paper-sonar.vercel.app`.
- [ ] `/api/health` = `ok`.
- [ ] 150-question eval ≥ 95%.
- [ ] 20 manual data checks pass.
- [ ] Rate limits verified.
- [ ] Kill switches verified.
- [ ] Rollback deployment recorded.
- [ ] Support email monitored.
- [ ] No secrets in git, bundle or logs.
- [ ] Owner: **Team PaperSonar**
- [ ] Date: ____________________

> Launch only when every box is checked. A working static site with chat
> disabled is better than a public assistant that leaks data or invents numbers.
