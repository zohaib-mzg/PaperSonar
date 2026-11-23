# 06 — Security, Cost and Operations

**Read after:** `05_FRONTEND_AND_DESIGN_SYSTEM.md`  
**Read before:** `07_IMPLEMENTATION_PLAN_AND_TESTS.md`  
**Owner:** security / operations workstream

---

## 1. Security objective

Expose a useful public research assistant without exposing the warehouse,
credentials, unpublished data or unbounded compute.

Primary invariants:

1. The public role can read only approved reporting views.
2. The browser never receives a secret or a direct Snowflake credential.
3. The LLM never produces executable SQL.
4. Every request is bounded by validation, rate limit, timeout and row cap.
5. A free-tier exhaustion produces a clean refusal, not a paid overage.
6. No personal data is required to use the site.

---

## 2. Trust boundaries

```text
Browser
  │ untrusted input, public network
  ▼
Next.js route handler
  │ validation, rate limit, orchestration
  ├──────────────► Upstash (cache, limits, session)
  ├──────────────► Groq / Gemini (question + public metadata only)
  └──────────────► Snowflake SQL API (public role, SELECT only)
                         │
                         ▼
                 PROJECT_REPORTING views
```

Trust rules:

- Treat every user string as hostile.
- Treat every LLM output as untrusted.
- Treat every Snowflake/provider error body as sensitive.
- Trust only server-side allowlists and validated result shapes.

---

## 3. Threat model and controls

| Threat | Impact | Control |
|---|---|---|
| SQL injection | data exfiltration | closed templates; bindings; no LLM SQL; filter allowlists |
| Prompt injection | policy bypass, data leak | system prompt; no tools with side effects; output schema; refusal rules |
| Unauthorized table read | raw data exposure | public role; view-only grants; verification queries |
| Secret leakage | full compromise | server-only env; no `NEXT_PUBLIC_` secrets; log redaction |
| Cost abuse | quota exhaustion | 20/hour, 50/day, cache, token caps, circuit breaker |
| Scraping | quota/latency | rate limits, no bulk export endpoint, row caps |
| XSS in answers | session compromise | plain text rendering; no `dangerouslySetInnerHTML` |
| CSRF | unwanted chat calls | JSON content type; same-origin check; no cookies |
| SSRF | internal access | no user-supplied URLs; provider endpoints hardcoded |
| Dependency compromise | supply chain | lockfile, audit, pinned versions |
| DDoS | availability | Vercel edge, rate limits, kill switch |
| Model hallucination | wrong claims | numeric validation; deterministic fallback |
| Data poisoning | misleading answers | published-only views; existing DQ gates; caveats |
| PII in prompts | privacy | no accounts; no raw question logging; public-data scope |
| Re-identification via analytics | privacy | no question/answer tracking; hashed IPs; no session recording |

---

## 4. Snowflake controls

### 4.1 Least privilege

- Application role: `PAPERSONAR_PUBLIC_RO`.
- Service user: `SVC_PAPERSONAR_PUBLIC`.
- Warehouse: `WH_PAPERSONAR_PUBLIC`.
- No `ACCOUNTADMIN`, `SECURITYADMIN`, `SYSADMIN` or `PAPERSONAR_LOADER`.
- No `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` or `OWNERSHIP`.
- No grants on bronze, silver, staging, DW or audit schemas.
- No `FUTURE TABLES` grants.
- No `GRANT ALL`.

### 4.2 Authentication

- Key-pair JWT only.
- 2048-bit RSA minimum.
- 60-second token lifetime.
- Private key only in Vercel’s encrypted environment variables.
- Rotate every 90 days or immediately after suspected exposure.
- Use `RSA_PUBLIC_KEY_2` for overlap during rotation.
- Never commit `.p8`, `.pub`, `.env`, or base64 key material.
- `.gitignore` must include `.env*`, keys and local Snowflake config.

### 4.3 Network and query limits

- Statement timeout: 30 seconds.
- Query tag: `public-chatbot`.
- Maximum result rows: 200 in SQL, 50 to the client.
- Warehouse auto-suspend: 60 seconds.
- Resource monitor: notify 75%, notify 90%, suspend 100%.
- No `COPY`, `PUT`, `GET`, `CALL`, `EXECUTE`, `UNDROP` or DDL from the app.
- Query only `SELECT`/`WITH` templates.
- Use the warehouse only for public API queries.

### 4.4 Verification

Run as the public role:

```sql
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_YEAR;
```

These must fail:

```sql
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH;
```

If any base-table query succeeds, stop the launch and revoke the grant.

---

## 5. API and application controls

### 5.1 Input

- `message`: 2–500 chars, trimmed.
- Body: max 8 KB.
- JSON content type only.
- Reject non-string fields and unknown top-level keys.
- Reject control characters and null bytes.
- Search term: 2–100 chars; escape `%`, `_`, `\`.
- Category/source/type values: allowlists only.
- Year: integer within 1900–current year.
- Limit: 1–50.
- Session ID: UUID format only.

### 5.2 Output

- JSON only.
- `Content-Type: application/json; charset=utf-8`.
- `Cache-Control: no-store` for chat.
- No SQL, stack traces, provider errors or internal identifiers.
- Answer text is rendered as text, never HTML.
- Numeric validation before any LLM prose is shown.
- All quoted category labels come from the catalogue or Snowflake, not the LLM.

### 5.3 HTTP security headers

Set in `next.config.ts`:

```text
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'
  https://*.posthog.com; connect-src 'self' https://*.posthog.com;
  img-src 'self' data:; style-src 'self' 'unsafe-inline';
  font-src 'self'; frame-ancestors 'none'; base-uri 'self';
  form-action 'self'
```

Adjust the PostHog host to the configured region. Do not add wildcard script
sources for convenience.

### 5.4 Origin and CORS

- No CORS headers; browser access is same-origin only.
- On `POST`, if `Origin` exists it must equal `PUBLIC_APP_ORIGIN`.
- Reject cross-origin form posts.
- No cookies means classic CSRF risk is low, but keep the origin check.

### 5.5 Rate limiting

- 20/hour/IP and 50/day/IP.
- Hash IP with `IP_HASH_SALT` using SHA-256 before Redis keys.
- Use `x-forwarded-for` first value, then `x-real-ip`.
- Do not log the raw IP.
- Return 429 with `Retry-After`.
- Feedback: 5/minute/IP.
- Add a global circuit breaker for provider quota exhaustion.

### 5.6 Failure behaviour

| Failure | Required behaviour |
|---|---|
| Redis down in production | 503, no unprotected chat |
| Snowflake auth failure | 503, alert owner |
| Snowflake timeout | 504, suggest a narrower question |
| Groq quota | one Gemini fallback, then 503 |
| Gemini quota | 503, no paid fallback |
| Both providers down | 503, deterministic refusal; do not query without a validated plan |
| Unknown exception | 500 with request ID, log internal detail |
| Prompt injection | safe refusal, no system prompt |

---

## 6. LLM security

- The planner gets a compact metric/category catalogue, not SQL, not secrets.
- The planner cannot call tools, browse the web or execute code.
- Only a strict JSON schema is accepted.
- Unknown metric IDs are rejected.
- Unknown filters are rejected.
- Confidence below 0.65 forces clarification.
- The composer gets facts, not the raw warehouse.
- Numbers in prose are checked against facts.
- If composition fails validation, show the deterministic answer.
- The system prompt is never returned to the user.
- User text is never interpolated into the system prompt.
- Do not send unpublished data, credentials, internal table names or DQ
  payloads to a provider.
- Free-tier provider terms may allow data use; only send the public question and
  public aggregate facts. Do not send PII.

---

## 7. Privacy

- No login, no accounts, no email collection.
- Session ID is random and expires after 1 hour.
- Do not store raw questions or answers.
- Analytics events exclude question and answer text.
- Do not enable PostHog autocapture on form values, session recording or
  heatmaps.
- IPs are hashed for rate limiting and not logged.
- Feedback is aggregate only; no free-text PII retention beyond a bounded
  comment if explicitly enabled.
- Inline terminal status/evidence text exposes publication metadata, not
  internal errors.

---

## 8. Free-tier cost model

The monthly budget is **USD 0**. The app must not have a paid overage path.

### 8.1 LLM

| Control | Value |
|---|---|
| Primary | Groq free tier |
| Fallback | Gemini free tier |
| Planner tokens | max 800 output |
| Composer tokens | max 350 output |
| Temperature | 0 |
| Retries | one fallback, no retry storm |
| Cache | 15 min per answer |
| Rate limit | 20/hour, 50/day/IP |
| Circuit breaker | 3 failures / 60 s |
| Kill switch | `LLM_MODE=off` |

Expected effect:

- Repeated questions hit cache.
- Simple exact matches skip the planner.
- Composition is capped and validated.
- A provider quota error becomes a 503, not a paid upgrade.

### 8.2 Snowflake

| Control | Value |
|---|---|
| Warehouse | X-Small |
| Auto-suspend | 60 s |
| Auto-resume | true |
| Statement timeout | 30 s |
| Result cap | 200 rows |
| Resource monitor | 10 credits/month recommended |
| Query patterns | pre-aggregated views, filters, limit |
| Cache | 10 min metric, 15 min answer |

Set the credit quota to the owner’s actual free/trial allowance. A resource
monitor is a safety valve, not a budget guarantee. Monitor it daily during
launch week.

### 8.3 Vercel

- One project.
- Static assets and server components cached.
- Chat route `maxDuration` within the plan limit.
- No image optimization of arbitrary remote URLs.
- No cron jobs unless required.
- Set a spend/usage notification even if the plan is free.

### 8.4 Upstash

- Use REST and pipelining.
- TTL every key.
- Do not store large payloads.
- Cache only validated results.
- Free-tier request limits are a hard constraint; reduce cache writes.

### 8.5 PostHog / Sentry

- PostHog free tier, optional.
- Sentry free tier, optional.
- No session replay.
- Sample errors if volume is high.
- The app must work with both keys absent.

### 8.6 Cost guardrails

- `PUBLIC_CHAT_ENABLED=false` is the global kill switch.
- `LLM_MODE=off` disables composition and provider calls; exact resolver paths
  may still answer deterministic metrics if designed, otherwise refuse.
- A provider quota error opens the circuit breaker.
- A Snowflake resource-monitor suspension must make `/api/health` report
  `not_ready`.
- Never add an automatic paid fallback “to keep the demo working”.

---

## 9. Observability

### 9.1 Metrics

Track:

- request count by status
- p50/p95 latency
- cache hit rate
- rate-limited count
- provider used and fallback rate
- LLM validation failure rate
- Snowflake query failures/timeouts
- row counts
- `/api/health` status
- PostHog page views

Do not track raw questions, answers, IPs or session IDs.

### 9.2 Alerts

| Signal | Threshold | Action |
|---|---|---|
| 5xx rate | > 5% for 10 min | inspect health, provider, Snowflake |
| p95 latency | > 8 s for 10 min | inspect queries/cache |
| rate-limited | > 30% of requests | review abuse or limits |
| provider failures | > 10% for 10 min | open breaker, check quotas |
| Snowflake failures | > 5 in 10 min | check role/key/warehouse |
| resource monitor | 75% / 90% | notify owner; 100% suspends |
| health | `not_ready` | page owner |
| cache errors | > 5% | check Upstash |

### 9.3 Logs

- JSON structured.
- One line per request.
- `request_id`, status, metric, provider, latency, row count, error code.
- No raw message, answer, SQL bindings, IP, session ID, JWT or API key.
- Retention: Vercel plan default; export only if needed.
- Sentry scrub list: `message`, `query`, `authorization`, `cookie`, `ip`,
  `session_id`, `private_key`.

---

## 10. Incident response

### Severity

| Level | Example | Response |
|---|---|---|
| SEV-1 | public role can read base tables; secret leaked | disable chat, revoke role/key, rotate, investigate |
| SEV-2 | wrong data exposed; site down; quota exhausted | disable chat or degrade, notify owner, fix |
| SEV-3 | single metric wrong; slow query; UI bug | fix in next deploy, add test |
| SEV-4 | cosmetic/analytics issue | backlog |

### First response

1. Set `PUBLIC_CHAT_ENABLED=false` if data or cost risk exists.
2. Confirm whether secrets or unpublished data were exposed.
3. Rotate Snowflake key or provider key if needed.
4. Check `/api/health`, Vercel logs, Snowflake resource monitor.
5. Preserve safe logs (no secrets) for review.
6. Communicate status on the site (maintenance card).
7. Fix, test, redeploy, re-enable gradually.

### Rollback

- Vercel: promote the previous deployment.
- Snowflake: public views are additive; drop/recreate only the new
  `VW_PUBLIC_*` views if needed.
- Do not roll back existing reporting views or the extraction pipeline.
- If a view is wrong, revoke its grant and deploy a corrected view.

---

## 11. Maintenance schedule

### Daily during launch week

- `/api/health`
- error rate and latency
- provider quota dashboards
- Snowflake resource monitor
- rate-limit counts
- spot-check 3 questions

### Weekly

- Review feedback aggregates.
- Check failed questions and add tests.
- Check dependency alerts.
- Check PostHog for unexpected events.
- Confirm no secret in logs.

### Monthly

- Rotate review of public grants.
- Review resource monitor usage.
- Review provider free-tier changes.
- Run the 150-question eval.
- Update model IDs if a free model is retired.
- Review cache hit rate and cost per request.

### Quarterly

- Rotate Snowflake key pair.
- Re-run deny tests for base tables.
- Review CSP and dependency lockfile.
- Review taxonomy changes and aliases.

---

## 12. Security acceptance checklist

- [ ] Public role has no base-table grants.
- [ ] Service user has key-pair auth only.
- [ ] Private key is only in Vercel.
- [ ] `ACCOUNTADMIN` is never used by the app.
- [ ] SQL templates are SELECT-only and bound.
- [ ] LLM output is schema-validated.
- [ ] Numeric prose validation is enabled.
- [ ] Rate limits are enforced and tested.
- [ ] 429/503 states are user-visible.
- [ ] No raw question or answer is logged.
- [ ] CSP and security headers are set.
- [ ] PostHog has no session replay/autocapture of text.
- [ ] Kill switches work.
- [ ] Resource monitor is attached.
- [ ] Incident runbook is current.
