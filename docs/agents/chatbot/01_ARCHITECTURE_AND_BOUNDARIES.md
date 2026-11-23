# 01 — Architecture and Boundaries

**Read after:** `00_README.md`  
**Read before:** `02_SNOWFLAKE_PUBLIC_LAYER.md`  
**Owner:** architecture / integration workstream

---

## 1. Goal

Add a public website and grounded research assistant without changing the
existing PaperSonar extraction, transformation, reporting or deployment
behaviour.

The assistant must answer analytical questions from the published Snowflake
warehouse. It must never expose raw records, secrets, unpublished batches or
arbitrary SQL.

---

## 2. System context

```text
┌──────────────────────────────────────────────────────────────┐
│ Vercel project: paper-sonar.vercel.app                        │
│                                                              │
│  Next.js public UI — PaperSonar Research Terminal            │
│  ├── Single route: /                                          │
│  ├── Left rail · terminal chat · right activity rail          │
│  └── /api/chat /api/health /api/feedback                      │
│                                                              │
│  Server modules (Node runtime)                               │
│  ├── env + secrets validation                                │
│  ├── rate limit + cache (Upstash)                            │
│  ├── LLM router (Groq primary, Gemini fallback)               │
│  ├── metric resolver + SQL compiler                           │
│  ├── Snowflake SQL API client                                 │
│  └── answer builder + response validation                     │
└───────────────┬───────────────────────────────┬───────────────┘
                │ HTTPS                         │ HTTPS
    ┌───────────▼────────────┐      ┌────────────▼──────────────┐
    │ Groq / Gemini          │      │ Snowflake SQL API         │
    │ intent + composition   │      │ public read-only role     │
    └────────────────────────┘      │ published views only      │
                                    └───────────────────────────┘
```

Optional observability:

- PostHog browser analytics (public project key only)
- Sentry frontend/server error reporting
- Vercel function logs

---

## 3. Component responsibilities

| Component | Owns | Must not own |
|---|---|---|
| Next.js terminal UI | Single research terminal, chat bubbles, inline evidence, status rails | SQL, secrets, provider keys, extra pages |
| `/api/chat` | Auth-less session, validation, rate limit, orchestration | UI layout |
| Metric resolver | Mapping language to metric + filters | SQL execution |
| SQL compiler | Building parameterised SQL from approved templates | LLM decisions |
| Snowflake client | JWT auth, SQL API call, timeout, row cap | Business metric definitions |
| LLM router | Groq-first planning/composition, Gemini fallback | Database credentials |
| Answer builder | Deterministic facts + optional phrasing | Inventing numbers |
| Upstash | Cache and rate limits | Source of truth |
| PostHog/Sentry | Observability | Personal data collection |

---

## 4. Request lifecycle

Every chat request follows this sequence.

```text
1. Browser sends POST /api/chat {message, session_id?}
2. Route validates body with Zod (max 500 chars)
3. Rate limit: 20/hour/IP and 50/day/IP
4. Kill switch check: PUBLIC_CHAT_ENABLED
5. Environment check: Snowflake, Groq, Redis; Gemini optional
6. Normalise message; resolve pronouns from last 3 intents
7. Resolver determines intent:
     metric | search | compare | clarify | refuse
8. If ambiguous: return clarification card, no SQL, no LLM composition
9. If metric: validate metric ID + filters against catalogue
10. Compile SQL from the approved template with bindings
11. Execute through Snowflake SQL API with:
      role=PAPERSONAR_PUBLIC_RO
      warehouse=WH_PAPERSONAR_PUBLIC
      timeout<=30s
      query tag=public-chatbot
      max rows=50
12. Validate result shape and numeric payload
13. Build deterministic answer facts + caveats + chart spec
14. Optional: LLM composes natural language from the facts
15. Validate every numeric token against the SQL result
16. Cache result; return JSON/stream to browser
17. Log query ID, metric, latency, row count, fallback used
```

### Latency budget

| Step | Target |
|---|---:|
| Request validation + rate limit | < 50 ms |
| Resolver/LLM plan | < 2.5 s |
| Snowflake query (pre-aggregated) | < 2 s |
| Answer composition | < 1.5 s |
| Total cached | < 2 s |
| Total uncached p95 | < 8 s |

Set the Vercel route `maxDuration` above the maximum Snowflake + LLM budget and
within the selected Vercel plan. The Snowflake SQL API timeout must be lower
than `maxDuration`.

---

## 5. Additive repository layout

Create only these new paths:

```text
apps/
  web/
    package.json
    next.config.ts
    tsconfig.json
    .env.example
    src/
      app/
        layout.tsx
        page.tsx                  # PaperSonar Research Terminal
        globals.css               # exact CSS from PaperSonar.html
        api/
          chat/route.ts
          health/route.ts
          feedback/route.ts
          metrics/route.ts        # support endpoint; no page
          topics/route.ts         # support endpoint; no page
          data-status/route.ts    # support endpoint; no page
      components/
        terminal-shell.tsx
        terminal-header.tsx
        terminal-left-rail.tsx
        terminal-main.tsx
        terminal-message.tsx
        terminal-evidence.tsx
        terminal-right-rail.tsx
        terminal-footer.tsx
        prompt-chips.tsx
      lib/
        api-client.ts
        analytics.ts
        format.ts
      server/
        env.ts
        logger.ts
        rate-limit.ts
        cache.ts
        snowflake/
          jwt.ts
          client.ts
          types.ts
        llm/
          types.ts
          groq.ts
          gemini.ts
          router.ts
          prompts.ts
          validate.ts
        metrics/
          catalogue.ts
          resolver.ts
          compiler.ts
          guards.ts
          sql/
            topic-growth.ts
            topic-share.ts
            topic-citations.ts
            topic-intersections.ts
            institutions.ts
            authors.ts
            venues.ts
            access.ts
            search.ts
            data-status.ts
        chat/
          service.ts
          answer.ts
          session.ts
          schema.ts
config/
  public_metrics.yml
sql/
  11_public_api/
    01_public_views.sql
    02_public_grants.sql
    03_public_verification.sql
tests/
  public_web/
    ...
```

### Do not create

- `services/public-api/`
- a Python FastAPI service
- a second Vercel project
- a new database
- a new extraction or transformation job
- a direct browser Snowflake client
- an LLM-generated SQL feature

### Do not modify

- `src/extract/**`
- `src/runner/**`
- `sql/00_*` through `sql/10_*`
- `PROJECT_REPORTING` existing view definitions
- `.github/workflows/extract-load.yml`
- existing reporting or deployment roles
- `PAPERSONAR_LOADER` credentials or warehouse

---

## 6. Data boundary

### Public API read surface

The Snowflake public role may read only:

- existing published reporting views approved in `02_SNOWFLAKE_PUBLIC_LAYER.md`
- new `VW_PUBLIC_*` views created under `sql/11_public_api/`

The public role must not read:

- `PROJECT_BRONZE`
- `PROJECT_SILVER`
- `PROJECT_STAGING`
- `PROJECT_DW` facts/dimensions
- `PROJECT_AUDIT` batch or DQ tables directly

New public views may read those objects internally, but the public role receives
`SELECT` on the view only.

### Publication contract

Every public view must satisfy one rule:

> A row is visible only when its originating batch is published.

For existing reporting views this is already true. New public views must repeat
the same `PUBLISHED_BATCH` filter or be derived from existing reporting views.

### What the browser may receive

Allowed:

- aggregate counts and rates
- category labels, years, source names, output types
- venue names and institution names
- author display names and ORCIDs for public research metadata
- titles and DOIs for title-search results
- citation counts with snapshot date
- data-status metadata

Not allowed:

- raw source payloads
- full text or abstracts beyond the public title
- unpublished or quarantined batch identifiers
- DQ internals
- credentials, private keys or connection strings
- private Snowflake object names in user-facing text

---

## 7. Runtime environments

| Environment | Purpose | Snowflake | LLM | Cache |
|---|---|---|---|---|
| Local | Development | Real read-only or mocks | Real keys or mocks | In-memory/Upstash |
| Preview | PR review | Public role | Free tier | Upstash preview namespace |
| Production | Public site | Public role | Groq primary, Gemini fallback | Upstash production namespace |

### Environment rules

- `.env.local` is ignored by git.
- `.env.example` contains names, never values.
- Preview and production use different PostHog environments if available.
- If `PUBLIC_CHAT_ENABLED=false`, `/api/chat` returns 503 and the UI shows a
  maintenance state. `/api/health` still works.
- Missing optional keys (Sentry, PostHog) do not block the app.
- Missing required keys (Snowflake, Groq, Redis) make `/api/health` report
  `degraded` or `not_ready`; `/api/chat` returns a clear configuration error.

---

## 8. Failure behaviour

| Failure | Behaviour |
|---|---|
| Snowflake timeout | Return “query took too long”; no partial number |
| Snowflake auth failure | Log error; return “assistant is unavailable” |
| Groq 429/quota | Try Gemini once; if unavailable, return quota message |
| Groq 5xx | Try Gemini once |
| Gemini 429/quota | Return quota message; no paid fallback |
| Redis unavailable | Fail closed for rate limit? Allow a small in-memory fallback only in local; production returns 503 |
| Resolver confidence low | Ask one clarification; do not guess |
| Metric not found | Offer closest supported metric or title search |
| Result below threshold | Return “not reportable” with the threshold |
| Answer number validation fails | Discard LLM prose, return deterministic answer |
| Prompt injection | Treat as unsupported question; do not expose system prompt |
| `PUBLIC_CHAT_ENABLED=false` | 503 maintenance state |

---

## 9. Architectural decisions

### ADR-001 — One Vercel project

**Decision:** frontend and API route handlers live in `apps/web` and deploy
together.

**Why:** same-origin API, one secret store, no CORS, lower operational load.

**Consequence:** use serverless-compatible Snowflake access; no long-lived
connections.

### ADR-002 — Snowflake SQL API over HTTPS

**Decision:** use the stateless SQL API with key-pair JWT.

**Why:** Vercel Functions are short-lived; a connector pool is not reliable.

**Consequence:** implement JWT signing, statement polling and timeout handling.

### ADR-003 — Groq primary, Gemini fallback

**Decision:** Groq handles planning and composition. Gemini handles fallback.

**Why:** free-tier operating mode; Groq is the primary free provider.

**Consequence:** provider adapter interface and circuit breaker are required.

### ADR-004 — Deterministic SQL, LLM selects tools

**Decision:** LLM returns a structured plan; server compiles SQL.

**Why:** prevent injection and hallucinated numbers.

**Consequence:** every supported question maps to a metric ID and template.

### ADR-005 — Published data only

**Decision:** public role reads only reporting views.

**Why:** preserve the existing fail-closed publication contract.

**Consequence:** new views must join `VW_RESEARCH_OUTPUT` or repeat the
`PUBLISHED_BATCH` filter.

### ADR-006 — No login for MVP

**Decision:** anonymous sessions with rate limits.

**Why:** lower friction and less personal data.

**Consequence:** session state is short-lived and non-personal.

---

## 10. Integration contract with existing pipeline

The existing pipeline owns extraction, identity, publication and reporting. The
public app is a consumer only.

- No change to the root task.
- No change to batch status semantics.
- No change to `PROJECT_AUDIT.PUBLISHED_BATCH`.
- No change to existing reporting view columns.
- New public views are additive and can be dropped without affecting the ELT.
- The public warehouse is separate from `WH_PAPERSONAR_ELT`.
- Public queries use `PAPERSONAR_PUBLIC_RO`, never `PAPERSONAR_LOADER` or
  `PAPERSONAR_ADMIN`.

If a metric requires data that is not in a published view, the correct action is
to add a new `VW_PUBLIC_*` view in `sql/11_public_api/` and grant it, not to
broaden access to an existing table.

---

## 11. Acceptance for this document

- [ ] A reviewer can explain the frontend → API → LLM → SQL → answer flow.
- [ ] No proposed file changes existing pipeline files.
- [ ] The public data surface is limited to reporting views.
- [ ] The architecture uses one Vercel project.
- [ ] The failure table is implemented as user-visible states.
- [ ] The next document, `02_SNOWFLAKE_PUBLIC_LAYER.md`, can be implemented
      without reopening this one.
