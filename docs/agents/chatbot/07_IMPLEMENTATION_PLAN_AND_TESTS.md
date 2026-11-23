# 07 — Implementation Plan and Tests

**Read after:** `06_SECURITY_COST_AND_OPERATIONS.md`  
**Read before:** `08_RUNBOOK_AND_LAUNCH.md`  
**Owner:** delivery / QA workstream

---

## 1. How to use this plan

Implement in the stage order below. Each stage has a hard acceptance gate. Do
not start the next stage while a gate is open.

Rules for implementation models:

- Work only inside the documented additive paths.
- Do not edit extraction, runner, existing SQL, existing views or workflows.
- Do not wait for real credentials to write code; use mocks and env validation.
- Do not commit secrets or generated keys.
- Do not mark a stage complete because the UI “looks right”; run the checks.
- Keep the existing Python test suite green.

---

## 2. Stage 0 — Preflight

### Tasks

1. Read `00_README.md`, `01_ARCHITECTURE_AND_BOUNDARIES.md` and this file.
2. Confirm the worktree is clean apart from documentation.
3. Confirm no existing `apps/web` or `sql/11_public_api` implementation exists.
4. Record the current `main` commit.
5. Confirm the existing baseline:

```powershell
pytest tests -q
ruff check src tests
```

Expected baseline: 270 tests passing, ruff clean. If the baseline differs, stop
and report before changing anything.

### Gate

- [ ] Existing tests pass.
- [ ] No pipeline file has been modified.
- [ ] The implementation plan has an owner for each stage.

---

## 3. Stage 1 — Scaffold the Next.js app

### Create

```text
apps/web/
  package.json
  next.config.ts
  tsconfig.json
  .env.example
  .gitignore
  vercel.json
  src/app/layout.tsx
  src/app/page.tsx
  src/app/globals.css
```

### Tasks

1. Use Next.js App Router + TypeScript strict.
2. Copy the CSS tokens and layout rules from `PaperSonar.html` into
   `globals.css`. Do not add Tailwind, PostCSS, shadcn, a component theme or
   Google Fonts.
3. Use the system monospace stack from the HTML.
4. Render a minimal placeholder terminal shell at `/`.
5. Add `.env.example` with names only.
6. Set the Vercel root directory to `apps/web` in the project settings, not by
   editing existing workflows.
7. Add `vercel.json` only if needed for function duration or headers.
8. Confirm the app builds without secrets.

### Commands

```powershell
cd apps/web
npm ci
npm run lint
npm run typecheck
npm run build
```

### Gate

- [ ] `npm run build` succeeds with no env vars.
- [ ] The placeholder page renders on desktop and mobile.
- [ ] No secret is present in the client bundle.
- [ ] The existing Python tests still pass.

---

## 4. Stage 2 — Public Snowflake layer

### Create

```text
sql/11_public_api/01_public_views.sql
sql/11_public_api/02_public_grants.sql
sql/11_public_api/03_public_verification.sql
```

### Tasks

1. Implement every view in `02_SNOWFLAKE_PUBLIC_LAYER.md`.
2. Keep all view names additive.
3. Do not alter existing reporting views.
4. Add grants only to approved views.
5. Run the verification script as `PAPERSONAR_PUBLIC_RO`.
6. Confirm base-table queries fail.
7. Record row counts for the first public data snapshot.

### Gate

- [ ] All public views return rows.
- [ ] No base-table access succeeds.
- [ ] No write privileges exist.
- [ ] Resource monitor and warehouse settings match the doc.
- [ ] The five Phase 3 views are unchanged.

---

## 5. Stage 3 — Server foundations

### Create

```text
src/server/env.ts
src/server/logger.ts
src/server/rate-limit.ts
src/server/cache.ts
src/server/snowflake/jwt.ts
src/server/snowflake/client.ts
src/server/snowflake/types.ts
```

### Tasks

1. Parse env with Zod once per cold start.
2. Make the app build without secrets; fail at request time with
   `NOT_CONFIGURED`.
3. Implement RS256 JWT signing.
4. Implement SQL API submit/poll/timeout.
5. Add `GET /api/health` with cached Snowflake check.
6. Add structured logger with redaction.
7. Add Upstash rate limiter and cache wrappers.
8. Add local in-memory fallback only when `NODE_ENV=development`.
9. Add `IP_HASH_SALT` to env and `.env.example`.

### Gate

- [ ] `/api/health` returns `not_ready` with missing env and `ok` with test env.
- [ ] A `SELECT 1` succeeds through the public role.
- [ ] A base-table query is denied.
- [ ] A 31-second query times out cleanly.
- [ ] Rate limit returns 429 after the 21st request in an hour.
- [ ] Logs contain no secret or raw IP.

---

## 6. Stage 4 — Metric catalogue, compiler and resolver

### Create

```text
config/public_metrics.yml
src/server/metrics/catalogue.ts
src/server/metrics/resolver.ts
src/server/metrics/compiler.ts
src/server/metrics/guards.ts
src/server/metrics/sql/*.ts
```

### Tasks

1. Load the 24 metric IDs from `03_METRIC_CATALOGUE_AND_QUESTIONS.md`.
2. Implement the filter allowlist.
3. Implement one template per metric family.
4. Implement the deterministic resolver:
   - exact category key/label
   - taxonomy rule match
   - metric trigger phrase
   - year parsing
   - comparison detection
   - search detection
   - follow-up merge
5. Implement clarification when confidence is low.
6. Implement closest-match disclosure.
7. Implement thresholds in guards, not in prompts.
8. Add `GET /api/metrics` and `GET /api/topics`.

### Gate

- [ ] Every metric ID has a template and a test.
- [ ] No template accepts raw SQL or unknown filters.
- [ ] `RAG` resolves to `rag`, not AI/ML.
- [ ] “last year” resolves to the latest complete year.
- [ ] `unclassified` never appears as a topic ranking entry.
- [ ] Growth under 30 works is suppressed.
- [ ] Intersections follow `IS_REPORTABLE`.

---

## 7. Stage 5 — Groq/Gemini planning and composition

### Create

```text
src/server/llm/types.ts
src/server/llm/groq.ts
src/server/llm/gemini.ts
src/server/llm/router.ts
src/server/llm/prompts.ts
src/server/llm/validate.ts
```

### Tasks

1. Implement the provider interface.
2. Add strict planner JSON schema.
3. Add Groq primary with 8-second timeout.
4. Add Gemini fallback with 8-second timeout.
5. Add circuit breaker in Upstash.
6. Add numeric validation for composed prose.
7. Add deterministic fallback composition.
8. Add `LLM_MODE=auto|groq|gemini|off`.
9. Add tests with mocked provider responses, quota errors and invalid JSON.

### Gate

- [ ] Groq success path works with a mock.
- [ ] Groq 429 falls back to Gemini once.
- [ ] Both providers failing returns `PROVIDER_UNAVAILABLE`.
- [ ] Invalid JSON from a provider is rejected.
- [ ] An invented number is rejected and deterministic prose is used.
- [ ] No secret or SQL is present in prompts or logs.

---

## 8. Stage 6 — Chat service and API

### Create

```text
src/server/chat/schema.ts
src/server/chat/service.ts
src/server/chat/answer.ts
src/server/chat/session.ts
src/app/api/chat/route.ts
src/app/api/feedback/route.ts
src/app/api/data-status/route.ts
```

### Tasks

1. Implement the request/response envelope.
2. Enforce body size, origin, rate limit and kill switch.
3. Implement session storage with TTL.
4. Implement cache lookup before planning.
5. Implement comparison orchestration.
6. Implement all status variants: answered, clarify, not reportable,
   unsupported, refused, error.
7. Implement safe error mapping.
8. Add request ID and structured logs.
9. Add feedback aggregation without PII.

### Gate

- [ ] A known question returns an answer with metric, filters, denominator,
  as-of date and caveat.
- [ ] A low-confidence question returns clarification, not SQL.
- [ ] A below-threshold question returns not-reportable.
- [ ] A prompt-injection request is refused.
- [ ] Rate limiting and kill switch work.
- [ ] Cache reduces repeated latency.
- [ ] No partial numbers on error.

---

## 9. Stage 7 — Research terminal shell

### Create

```text
src/components/terminal-shell.tsx
src/components/terminal-header.tsx
src/components/terminal-left-rail.tsx
src/components/terminal-main.tsx
src/components/terminal-message.tsx
src/components/terminal-evidence.tsx
src/components/terminal-chart.tsx
src/components/terminal-right-rail.tsx
src/components/terminal-footer.tsx
src/components/prompt-chips.tsx
src/app/layout.tsx
src/app/page.tsx
src/app/globals.css
```

### Tasks

1. Copy the exact CSS tokens, layout, typography and media queries from
   `PaperSonar.html` and `05_FRONTEND_AND_DESIGN_SYSTEM.md`.
2. Render the single route `/` as the research terminal.
3. Reproduce header, left rail, path bar, 3-box stats strip, messages area,
   chips, composer, right rail and footer exactly.
4. Use the exact copy: `PaperSonar`, `RESEARCH INTELLIGENCE`, `● READY`,
   `+ New chat`, `~/papersonar/terminal`, `MODE/Research`, `ENGINE/Ready`,
   `EVIDENCE/Enabled`, the three chips, placeholder and footer.
5. Render the sonar SVG from the HTML.
6. Add accessible labels and focus states.
7. Do not add Tailwind, shadcn, Google Fonts, Recharts or extra pages.

### Gate

- [ ] The screen matches `PaperSonar.html` at 1440 px.
- [ ] Right rail hides at ≤1000 px; left rail hides at ≤700 px.
- [ ] Path and stats hide at max-height 480 px.
- [ ] Dark and light `prefers-color-scheme` match the HTML tokens.
- [ ] No extra navigation or marketing sections exist.
- [ ] Lighthouse accessibility ≥ 95.

---

## 10. Stage 8 — Terminal chat behaviour

### Create

```text
src/lib/api-client.ts
src/lib/analytics.ts
src/lib/format.ts
```

### Tasks

1. Implement the welcome message exactly as in the HTML.
2. Send chip clicks, Enter and Send through `POST /api/chat`.
3. Hide chips after first submit; restore them on `+ New chat`.
4. Implement Enter submits / Shift+Enter newline.
5. Append `YOU` and `PAPERSONAR` bubbles with the exact labels.
6. Replace the HTML demo reply with the real API response.
7. Render answer, inline evidence, caveats and table as terminal text.
8. Render compact inline SVG/CSS charts from the validated `chart` field when
   series data is available; no chart library.
9. Handle every status: answered, clarify, not reportable, unsupported,
   refused, error, rate limited.
10. Update the right rail activity rows with green/amber/red dots.
11. Store `session_id` in `sessionStorage` only; clear it on New chat.
12. Add content-free analytics events.
13. Never render HTML from the LLM or the API; build SVG from numbers only.

### Gate

- [ ] The demo reply is absent in production.
- [ ] Enter submits; Shift+Enter inserts a newline.
- [ ] New chat clears messages and restores chips.
- [ ] Every `/api/chat` status has a terminal-readable state.
- [ ] Evidence is inline using `.box`, not a drawer or separate panel.
- [ ] Inline terminal charts render for series answers with table fallbacks.
- [ ] No chart renders for suppressed, single-value or search answers.
- [ ] No answer text is sent to analytics.
- [ ] A failed request never shows a stale answer.

---

## 11. Stage 9 — Terminal status and responsive polish

### Tasks

1. Wire `● READY / DEGRADED / OFFLINE` to `/api/health`.
2. Disable Send with a clear bot message when health is not ready or
   `PUBLIC_CHAT_ENABLED=false`.
3. Verify left/right rail visibility at all breakpoints from the HTML.
4. Verify 44 px mobile targets and 200% zoom without horizontal scroll.
5. Add maintenance and rate-limit messages inside bot bubbles.
6. Add a minimal 404 for unknown URLs; do not link to it from the terminal.
7. Confirm `robots.txt` disallows `/api/*`.
8. Confirm canonical URL is `/`.

### Gate

- [ ] Status dot reflects health.
- [ ] Maintenance mode renders in the terminal, not a separate page.
- [ ] All breakpoints match the HTML.
- [ ] No layout overflow at 320 px or 200% zoom.
- [ ] No raw table names, secrets or SQL appear in the UI.

---

## 12. Stage 10 — Security, analytics and polish

### Tasks

1. Add CSP and security headers.
2. Add PostHog with no autocapture/session replay.
3. Add Sentry optional with scrubbing.
4. Add a minimal 404 for unknown URLs and the terminal error state on `/`.
5. Add the maintenance state when `PUBLIC_CHAT_ENABLED=false`.
6. Add the feedback route.
7. Add secret scanning to the repo workflow.
8. Add dependency review.
9. Tune cache TTLs and rate-limit copy.
10. Add loading skeletons and empty states.

### Gate

- [ ] CSP passes on the deployed site.
- [ ] No secret appears in the bundle, HTML, source maps or logs.
- [ ] PostHog events contain no question/answer text.
- [ ] Kill switch shows the maintenance card.
- [ ] 404 and error pages are branded and useful.
- [ ] Security headers verified with `curl -I`.

---

## 13. Stage 11 — Test and evaluation suite

### Test layout

```text
tests/public_web/
  unit/
    resolver.test.ts
    guards.test.ts
    numeric-validation.test.ts
    compiler.test.ts
    sessions.test.ts
  api/
    chat.test.ts
    health.test.ts
    data-status.test.ts
    feedback.test.ts
    rate-limit.test.ts
  sql/
    contract.test.ts
    public-role-deny.test.ts
  e2e/
    terminal-layout.spec.ts
    terminal-chat.spec.ts
    terminal-statuses.spec.ts
    terminal-mobile.spec.ts
    terminal-accessibility.spec.ts
  eval/
    questions.json
    expected.json
    run-eval.ts
    README.md
```

### Unit tests

- Every metric ID resolves from at least one phrasing.
- Every template produces `SELECT`/`WITH` only.
- Unknown filters are rejected.
- Category aliases work.
- `RAG` is distinct from AI/ML.
- Year parsing and “last year” are deterministic.
- Suppression thresholds fire.
- Numeric validator rejects invented numbers.
- Session follow-up merges correctly.
- Rate-limit keys are hashed.

### API tests

Use mocked Snowflake and LLM adapters. Assert:

- 200 answered envelope with receipt.
- 200 clarify envelope with no SQL call.
- 200 not-reportable envelope.
- 429 after limit.
- 503 when disabled or unconfigured.
- 504 on Snowflake timeout.
- 400 on invalid body.
- No secret in any response body.
- No raw SQL in any response.
- Origin rejection.

### SQL contract tests

Run only when `PUBLIC_SQL_TESTS=1` and test credentials exist.

- Every public view is selectable by the public role.
- Every base table is denied.
- View columns match the documented contract.
- Citation view has one row per output/snapshot after dedupe.
- Growth threshold values are present.
- `IS_REPORTABLE` matches the intersection threshold.

### End-to-end tests

- Terminal loads with exact welcome copy, three chips and footer.
- Chip click → `YOU` bubble → `PAPERSONAR` answer with inline evidence.
- Series answer renders inline terminal chart plus accessible table fallback.
- Suppressed/single-value/search answer renders no chart.
- Enter submits; Shift+Enter inserts newline; empty submit is ignored.
- `+ New chat` clears bubbles and restores chips.
- Clarification option → answer.
- Not-reportable → terminal text with threshold.
- Rate limit → bot message, no retry loop.
- Right rail active rows change with request state.
- Three-column desktop, two-column tablet, single-column mobile.
- Dark/light `prefers-color-scheme` tokens match the HTML.
- Keyboard-only flow and focus rings.
- Axe accessibility scan on `/`.
- No console errors and no demo reply text.

### Evaluation harness

`questions.json` contains all 150 questions:

```json
[
  {
    "id": "Q001",
    "question": "Which topics grew fastest in 2025?",
    "expected_status": "answered",
    "expected_metric": "M01",
    "expected_category": null,
    "notes": "ranking; must disclose threshold"
  }
]
```

`expected.json` may be merged into the same file. The runner:

1. Sends each question through the service with test doubles.
2. Records status, metric, filters, latency and validation flags.
3. Scores:
   - status correct (40%)
   - metric family correct (25%)
   - category/filter correct (20%)
   - receipt complete (10%)
   - no hallucinated number (5%)
4. Fails the build below **95%** for launch. A single data-exposure or
   hallucination failure is always fatal.

Do not call paid providers during CI. Use recorded/mock planner outputs for the
deterministic suite, and run a small live smoke set manually before launch.

---

## 14. Regression and quality gates

### Existing project

```powershell
pytest tests -q
ruff check src tests
```

### Web app

```powershell
cd apps/web
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

### Security

```powershell
npm audit --omit=dev
git grep -n -E "(SNOWFLAKE|GROQ|GEMINI|UPSTASH).*=" -- . ':!*.example'
```

The secret scan must return only names in `.env.example`, never values.

### Accessibility and performance

- Lighthouse performance ≥ 85 on mobile for the terminal route.
- Lighthouse accessibility ≥ 95 on `/`.
- No layout shift from the chat answer.
- Chat p95 ≤ 8 s uncached, ≤ 2 s cached.

### Gate

- [ ] Existing Python suite unchanged and green.
- [ ] Web lint, typecheck, unit, e2e and build pass.
- [ ] No high-severity dependency vuln without a documented exception.
- [ ] Secret scan clean.
- [ ] 150-question eval ≥ 95%.
- [ ] No base-table access in SQL tests.

---

## 15. Release checklist

- [ ] Stage 0–11 gates closed.
- [ ] Vercel preview deployed and smoke-tested.
- [ ] Production env set by owner.
- [ ] Snowflake public role verified.
- [ ] Groq and Gemini keys verified.
- [ ] Upstash verified.
- [ ] `/api/health` is `ok`.
- [ ] 20 questions manually checked against SQL.
- [ ] PostHog events verified.
- [ ] Rate limits verified from two networks.
- [ ] Data-status page matches Snowflake.
- [ ] Support email works.
- [ ] Rollback deployment identified.
- [ ] Owner sign-off: Team PaperSonar.

---

## 16. Explicit non-goals for implementation

- No arbitrary SQL console.
- No full-text or PDF search.
- No user accounts.
- No saved dashboards.
- No paid LLM fallback.
- No changes to extraction or the task graph.
- No new reporting view that replaces an existing one.
- No “AI-generated insight” without a metric receipt.
- No hidden approximations; disclose every broader match.

---

## 17. Handoff artifacts

At the end of implementation, hand over:

- this documentation folder
- `apps/web` with a passing build
- `sql/11_public_api` scripts
- test and eval reports
- `.env.example`
- deployed preview URL
- list of open risks
- the exact release commit

The release is not done until `08_RUNBOOK_AND_LAUNCH.md` has been executed.
