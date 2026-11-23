# PaperSonar Public Website + Chatbot — Implementation Documentation

**Status:** Implementation docs v1.0 · documentation only  
**Date:** 2026-11-23  
**Owner:** Team PaperSonar  
**Public site:** `PaperSonar Research Assistant`  
**Domain:** `paper-sonar.vercel.app`

This folder is the build contract for the public PaperSonar website and its
grounded research assistant. An implementation model must read this file first,
then read the one file assigned to its workstream.

There are **10 files maximum** in this folder:

| # | File | Purpose |
|---:|---|---|
| 0 | `chatbot_req.md` | Inputs, access checklist and captured decisions |
| 1 | `00_README.md` | This file: rules, decisions, reading order |
| 2 | `01_ARCHITECTURE_AND_BOUNDARIES.md` | System architecture and additive boundary |
| 3 | `02_SNOWFLAKE_PUBLIC_LAYER.md` | Public role, views, grants, SQL contracts |
| 4 | `03_METRIC_CATALOGUE_AND_QUESTIONS.md` | Metrics, 150 questions, resolver rules |
| 5 | `04_BACKEND_API_AND_LLM.md` | API, Groq/Gemini, SQL compiler, answer builder |
| 6 | `05_FRONTEND_AND_DESIGN_SYSTEM.md` | Pages, visual system, components, UX |
| 7 | `06_SECURITY_COST_AND_OPERATIONS.md` | Security, rate limits, free-tier budgets, ops |
| 8 | `07_IMPLEMENTATION_PLAN_AND_TESTS.md` | Build order, test matrix, acceptance |
| 9 | `08_RUNBOOK_AND_LAUNCH.md` | Setup, deploy, smoke tests, launch, rollback |

Do not create additional implementation markdown files in this folder. If a
new decision is needed, update the existing file that owns it.

---

## 1. Captured product decisions

These are fixed unless the owner explicitly changes them.

| Decision | Value |
|---|---|
| Site name | PaperSonar Research Assistant |
| UI display | `PaperSonar` / `RESEARCH INTELLIGENCE` research terminal |
| Visual source of truth | `PaperSonar.html` in the repository root |
| Public domain | `paper-sonar.vercel.app` |
| Launch mode | Public launch, no login |
| Language | English only |
| Frontend and backend | One Vercel project, Next.js route handlers |
| Backend runtime | Node runtime, not Edge |
| Snowflake access | Snowflake SQL API over HTTPS, key-pair JWT |
| Public data scope | Published `PROJECT_REPORTING` views only |
| LLM primary | Groq |
| LLM fallback | Gemini Flash-class |
| LLM budget | USD 0; free tiers only |
| Snowflake budget | USD 0; free/trial credits only |
| Analytics | PostHog free tier |
| Rate limit | 20 questions/hour/IP, 50/day/IP |
| Data freshness | “Updated after the latest published batch” |
| Citation freshness | “As of latest snapshot” |
| Support email | `zohaib.mzg158@gmail.com` |
| Launch owner | Team PaperSonar |

Infrastructure is intentionally provisioned **after development**. The code must
compile without secrets, expose a health endpoint that reports missing config,
and fail closed with a useful message.

---

## 2. Non-negotiable rules

1. **Additive only.** Do not edit `src/extract`, `src/runner`, existing SQL,
   the task graph, existing reporting views, or existing GitHub workflows.
2. **New directories only.** The public app goes in `apps/web`; new SQL goes in
   `sql/11_public_api`; new tests go in `tests/public_web`.
3. **No `ACCOUNTADMIN` for the application.** Use
   `PAPERSONAR_PUBLIC_RO` and `SVC_PAPERSONAR_PUBLIC` only.
4. **Published data only.** The public role must never be able to read bronze,
   silver, staging or base DW tables.
5. **No LLM-generated SQL.** The LLM selects an approved metric and filters;
   the server compiles parameterised SQL from a closed template set.
6. **No silent substitution.** If a term is mapped to a broader category, the
   answer must say so. If data is below a threshold, say “not reportable”.
7. **Numbers come from SQL.** The LLM may phrase an answer; it may not invent or
   alter a number, date, source, category or denominator.
8. **One source per citation answer.** Citation snapshots are never summed
   across sources.
9. **Every answer carries a receipt:** metric ID, filters, denominator, as-of
   date and caveat.
10. **No secrets in the browser, repository, logs or prompts.**
11. **Cache and rate-limit every public request.**
12. **Do not add a separate FastAPI backend.** The backend is the Next.js app.

---

## 3. What exists and what is new

### Reuse without modification

- `PROJECT_REPORTING.VW_RESEARCH_OUTPUT`
- `PROJECT_REPORTING.VW_CITATION_SNAPSHOT`
- `PROJECT_REPORTING.VW_SOURCE_OBSERVATION`
- `PROJECT_REPORTING.VW_CATEGORY_COVERAGE`
- `PROJECT_REPORTING.VW_PUBLISHED_BATCH`
- `PROJECT_REPORTING.VW_PIPELINE_HEALTH`
- `PROJECT_REPORTING.VW_CATEGORY_LABEL`
- `PROJECT_REPORTING.VW_TOPIC_GROWTH`
- `PROJECT_REPORTING.VW_OUTPUT_COVERAGE`
- `PROJECT_REPORTING.VW_CITATION_COHORTS`
- `PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS`
- `PROJECT_REPORTING.VW_RESEARCH_COMMUNITY`
- `config/taxonomy.yml`
- `config/quality_rules.yml`
- `docs/phase3/METRIC_CATALOGUE.md`
- `sql/10_analytics/` as the reference for metric definitions

### New code and assets

```text
apps/web/                         Next.js app + route handlers + server modules
config/public_metrics.yml         public metric catalogue
sql/11_public_api/                additive public views and grants
tests/public_web/                 unit, contract, API and eval tests
docs/agents/chatbot/              these implementation docs
```

No existing workflow file needs to change. If a deployment workflow is needed
for the new SQL directory, add a new workflow; do not edit the existing
extraction or deployment flow unless the owner explicitly approves it.

---

## 4. Reading order for implementation models

Read in order. Do not jump ahead unless the prior file's acceptance checks pass.

1. `00_README.md` — rules and decisions (this file)
2. `01_ARCHITECTURE_AND_BOUNDARIES.md` — system shape and boundaries
3. `02_SNOWFLAKE_PUBLIC_LAYER.md` — public views and grants
4. `03_METRIC_CATALOGUE_AND_QUESTIONS.md` — what the bot may answer
5. `04_BACKEND_API_AND_LLM.md` — API, routing, SQL compiler, answer builder
6. `05_FRONTEND_AND_DESIGN_SYSTEM.md` — pages, visual language, components
7. `06_SECURITY_COST_AND_OPERATIONS.md` — controls, limits, observability
8. `07_IMPLEMENTATION_PLAN_AND_TESTS.md` — build order and acceptance tests
9. `08_RUNBOOK_AND_LAUNCH.md` — provisioning, deploy, launch and rollback

The implementation order is **not** the same as the reading order. Follow the
staged build order in `07_IMPLEMENTATION_PLAN_AND_TESTS.md`.

---

## 5. Required environment variable names

Only server-side variables are secrets. Never prefix a secret with
`NEXT_PUBLIC_`.

### Public/browser-safe

```text
NEXT_PUBLIC_SITE_URL
NEXT_PUBLIC_POSTHOG_KEY
NEXT_PUBLIC_POSTHOG_HOST
```

### Server-only

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

Defaults:

- `SNOWFLAKE_DATABASE=PAPERSONAR`
- `SNOWFLAKE_SCHEMA=PROJECT_REPORTING`
- `SNOWFLAKE_PUBLIC_ROLE=PAPERSONAR_PUBLIC_RO`
- `SNOWFLAKE_PUBLIC_WAREHOUSE=WH_PAPERSONAR_PUBLIC`
- `PUBLIC_CHAT_ENABLED=true`
- `LLM_MODE=auto` (`auto` = Groq first, Gemini fallback)

---

## 6. Free-tier operating mode

The launch budget is **USD 0**. That has product consequences:

- Groq is primary because its free tier is the expected daily driver.
- Gemini is fallback; it is not called on every request.
- Requests are cached aggressively.
- The app must stop cleanly when a free quota is exhausted.
- No paid overage path exists. A quota error is a user-visible
  “temporarily unavailable” state, not a silent paid upgrade.
- Snowflake trial credits are finite. The public warehouse is X-Small,
  auto-suspends after 60 seconds, and has a resource monitor.
- PostHog and Sentry are optional at first; the app must run if their keys are
  absent.

If the free-tier quota is exhausted, the correct behaviour is:

```text
The research assistant is temporarily unavailable because its free usage
limit has been reached. Please try again later.
```

No fabricated answer, no fallback to a paid provider, no SQL fallback without
the LLM.

---

## 7. Definition of done

The release is done when:

- [ ] The site is deployed at `paper-sonar.vercel.app`.
- [ ] `/api/health` reports Snowflake, Redis, Groq and Gemini status.
- [ ] The public role cannot read any non-public table.
- [ ] 150/150 acceptance questions return a grounded answer, clarification or
      refusal.
- [ ] Every answer includes metric, filters, denominator, as-of date and caveat.
- [ ] No secret appears in client bundles or logs.
- [ ] Rate limits and statement timeouts are enforced.
- [ ] Mobile and desktop visual QA pass.
- [ ] Existing extraction, SQL and reporting features are unchanged.
- [ ] The launch runbook has been executed.

---

## 8. What is deliberately out of scope

- User accounts or saved workspaces
- A multi-page editorial website or separate chat/explore pages
- Full-text PDF search
- Live citation tracking
- Uploading datasets
- Arbitrary SQL or notebook access
- Email reports
- Non-English prompts
- Causal or predictive modelling
- Paid LLM overage
- Editing the existing extraction or reporting pipeline

If a user asks for one of these, the assistant should say it is not supported
and offer the closest supported metric or a title search.
