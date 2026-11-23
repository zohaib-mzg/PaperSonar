# PaperSonar Chatbot — Build Requirements and Access Checklist

**File:** `docs/agents/chatbot/chatbot_req.md`
**Status:** Implementation complete — deployment-ready
**Purpose:** Owner decisions, required access, and the exact deployment
procedure for the PaperSonar public research terminal and chat API.

> **Rule:** Do not paste secret values into this file, chat, GitHub issues or
> commits. Provide secret values only through the hosting/secret manager, or
> confirm that they are configured. Names and non-secret decisions can be
> written here.

---

## 1. What this file is for

The implementation is documented in **exactly 10 Markdown files** under
`docs/agents/chatbot/`. The code is additive and lives in `apps/web/`,
`config/public_metrics.yml` and `sql/11_public_api/`.

Before deployment, the following must be decided or available:

- public data scope
- Snowflake public role, warehouse and service user
- Groq primary / Gemini fallback API access
- Vercel project for the frontend and API routes
- domain and DNS
- branding and legal content
- rate limits and budget
- acceptance questions
- operational ownership

Once this checklist is complete, follow Section 22. No code change is required
for deployment; only infrastructure, secrets and DNS are outstanding.

---

## 2. Definition of ready

The build is ready to start when all of these are true:

- [ ] `PAPERSONAR_PUBLIC_RO`, `WH_PAPERSONAR_PUBLIC` and
      `SVC_PAPERSONAR_PUBLIC` exist.
- [ ] The public role can `SELECT` only the approved reporting views.
- [ ] The public service user authenticates with key-pair auth.
- [ ] Groq API key is configured in Vercel environment variables.
- [ ] Gemini API key is configured for fallback, or “Groq only” is approved.
- [ ] Vercel project is available for the frontend and API routes.
- [ ] Domain/subdomain is available and DNS access is confirmed.
- [ ] Redis/Upstash (or equivalent) is available for cache and rate limits.
- [ ] Public data scope and legal wording are approved.
- [ ] Visual direction and brand assets are approved.
- [ ] Budget and rate limits are approved.
- [ ] 150-question acceptance catalogue is approved.
- [ ] The “no existing feature changes” boundary is approved.

---

## 3. Required decisions

These are not credentials. They are product and policy decisions that must be
fixed before implementation docs are written.

| ID | Decision | Recommended default | Why it matters |
|---|---|---|---|
| D01 | Public site name | PaperSonar Research Assistant | Branding and copy |
| D02 | Public domain/subdomain | `research.papersonar.com` or similar | Cookies, canonical URLs, same-origin API |
| D03 | Frontend host | Vercel | Fast Next.js deployment |
| D04 | Backend host | Vercel Functions, same project | Single deploy, same-origin API, simple secrets |
| D05 | Login required? | No login for MVP | Lower friction; rate-limit by IP/session |
| D06 | Public data scope | All published `PROJECT_REPORTING` views | Legal and data exposure |
| D07 | Failed/unpublished batches visible? | No | Trust and publication contract |
| D08 | Citation freshness text | “As of latest snapshot” | Avoid implying live citations |
| D09 | Data freshness text | “Updated after the latest published batch” | Avoid implying real-time |
| D10 | Languages | English only for MVP | Prompt, UI and evaluation scope |
| D11 | Answer style | Direct answer + evidence + caveat | Trust and usability |
| D12 | Charts | Yes, for ranked/time-series answers | Modern UX |
| D13 | CSV export | Optional; no raw record export | Cost and data policy |
| D14 | Feedback mechanism | Thumbs + optional comment | Quality improvement |
| D15 | Analytics | PostHog free tier | No unnecessary cookies |
| D16 | Cookie banner | Only if analytics requires it | Legal compliance |
| D17 | Rate limit | 20 questions/hour/IP, 50/day/IP | Abuse and cost control |
| D18 | Monthly LLM budget | USD 0; free tiers only | Public traffic safety |
| D19 | Monthly Snowflake budget | USD 0; free/trial credits only | Trial credits are finite |
| D20 | Beta or public launch | Public launch with hard rate limits | Reduce risk |
| D21 | Support email | Provide address | Legal and UX |
| D22 | Uptime/error tracking | Sentry or equivalent | Operations |
| D23 | Kill switch | `PUBLIC_CHAT_ENABLED=false` | Stop spend instantly |
| D24 | Model routing | Groq primary; Gemini fallback | Cost/latency/resilience |
| D25 | “Closest match” policy | Show interpretation; ask if ambiguous | Avoid silent wrong answers |
| D26 | “Not reportable” policy | Explain threshold, do not guess | Project credibility |
| D27 | Search fallback | Title/keyword search only | Keep scope bounded |
| D28 | Public API docs | Internal only for MVP | Reduce attack surface |
| D29 | Accessibility target | WCAG AA | Public quality |
| D30 | Launch owner | Provide name/role | Operational accountability |

### Fill these in

```text
PUBLIC_SITE_NAME=PaperSonar Research Assistant
PUBLIC_DOMAIN=paper-sonar.vercel.app
FRONTEND_HOST=vercel
BACKEND_HOST=vercel
BACKEND_RUNTIME=nextjs-route-handlers
LOGIN_REQUIRED=No
PUBLIC_DATA_SCOPE=All published PROJECT_REPORTING views
CITATION_FRESHNESS_TEXT=As of latest snapshot
DATA_FRESHNESS_TEXT=Updated after the latest published batch
LANGUAGES=English only
BETA_OR_PUBLIC=Public
SUPPORT_EMAIL=zohaib.mzg158@gmail.com
ANALYTICS_PROVIDER=PostHog (free tier)
MONTHLY_LLM_BUDGET_USD=0
MONTHLY_SNOWFLAKE_BUDGET_USD=0
RATE_LIMIT_PER_HOUR=20 per IP
RATE_LIMIT_PER_DAY=50 per IP
MODEL_ROUTING=groq-primary-gemini-fallback (free tiers only)
LAUNCH_OWNER=Team PaperSonar
```

**Infrastructure status:** the owner will provision Snowflake, Vercel, Groq,
Gemini, Upstash, PostHog and Sentry **after development**. The implementation
must be buildable without secrets and must expose a health check that clearly
reports missing configuration. No secret values belong in the repository.

---

## 4. Required accounts and secrets

### 4.1 Summary

| Item | Required? | Used by | Where it must live |
|---|---|---|---|
| Snowflake account identifier | Yes | API routes | Vercel secret |
| `SVC_PAPERSONAR_PUBLIC` user | Yes | API routes | Snowflake |
| Public private key (PEM) | Yes | API routes | Vercel secret |
| Public key registered on user | Yes | Snowflake | Snowflake |
| `PAPERSONAR_PUBLIC_RO` | Yes | Snowflake | Snowflake |
| `WH_PAPERSONAR_PUBLIC` | Yes | Snowflake | Snowflake |
| Groq API key | Yes | API routes | Vercel secret |
| Gemini API key | Optional/fallback | API routes | Vercel secret |
| Vercel project (frontend + API) | Yes | Deployment | Vercel |
| Upstash Redis REST URL + token | Yes | API routes | Vercel secret |
| Domain + DNS access | Yes | Launch | Registrar |
| Sentry DSN | Recommended | Frontend/API routes | Vercel secret |
| Analytics site ID | Optional | Frontend | Public env |
| GitHub repository access | Yes | Deployment | Existing |
| Source API keys (OpenAlex/Crossref) | No | Existing ELT only | Already configured |

> The public chatbot does **not** need source API keys. It reads only from
> Snowflake reporting views. The existing extraction workflow continues to own
> source credentials.

### 4.2 Secret names

Use these exact names so the implementation docs can reference them:

```text
NEXT_PUBLIC_SITE_URL
NEXT_PUBLIC_SITE_NAME
NEXT_PUBLIC_SUPPORT_EMAIL
PUBLIC_APP_ORIGIN
PUBLIC_CHAT_ENABLED

SNOWFLAKE_ACCOUNT_URL
SNOWFLAKE_ACCOUNT
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
LLM_MODE

UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
IP_HASH_SALT

NEXT_PUBLIC_POSTHOG_KEY
NEXT_PUBLIC_POSTHOG_HOST
SENTRY_DSN
```

Use these exact names in Vercel. `NEXT_PUBLIC_*` values are exposed to the
browser; all other values are server-only. Never put a real private key, token
or API key in a `NEXT_PUBLIC_*` variable.

`SNOWFLAKE_ACCOUNT_URL` is the HTTPS base used by the SQL API, for example
`https://<account-identifier>.snowflakecomputing.com`. Keep it server-side.

Because the frontend and API share the same Vercel origin, there is no
`PUBLIC_API_BASE_URL`; browser code calls `/api/*` relatively.

Do not put values for these in this file.

---

## 5. Snowflake public layer

### 5.1 Objects to create

| Object | Name | Notes |
|---|---|---|
| Role | `PAPERSONAR_PUBLIC_RO` | Read-only public role |
| Warehouse | `WH_PAPERSONAR_PUBLIC` | X-Small, auto-suspend 60 s |
| Resource monitor | `RM_PAPERSONAR_PUBLIC` | Credit cap and alerts |
| User | `SVC_PAPERSONAR_PUBLIC` | Key-pair only, no password |
| Database usage | `PAPERSONAR` | `USAGE` only |
| Schema usage | `PAPERSONAR.PROJECT_REPORTING` | `USAGE` only |
| View grants | Public reporting views | `SELECT` only |

### 5.2 Approved views

The public API routes may read only these views (or the final approved subset):

- `PROJECT_REPORTING.VW_RESEARCH_OUTPUT`
- `PROJECT_REPORTING.VW_SOURCE_OBSERVATION`
- `PROJECT_REPORTING.VW_CITATION_SNAPSHOT`
- `PROJECT_REPORTING.VW_CATEGORY_COVERAGE`
- `PROJECT_REPORTING.VW_PUBLISHED_BATCH`
- `PROJECT_REPORTING.VW_PIPELINE_HEALTH`
- `PROJECT_REPORTING.VW_TOPIC_GROWTH`
- `PROJECT_REPORTING.VW_OUTPUT_COVERAGE`
- `PROJECT_REPORTING.VW_CITATION_COHORTS`
- `PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS`
- `PROJECT_REPORTING.VW_RESEARCH_COMMUNITY`

New public helper views may be added under `sql/11_public_api/`; they must be
new names and must not replace existing views.

### 5.3 One-time setup method

The account owner must perform this one-time setup with an administrative role
that can create roles, warehouses, users and grants. Do **not** give that role
to the application. The application and CI must never use `ACCOUNTADMIN`.

1. Generate a new key pair on a trusted machine:

```powershell
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -outform pem > papersonar_public_key.p8
openssl rsa -in papersonar_public_key.p8 -pubout -out papersonar_public_key.pub
```

2. Keep the private key outside the repository.
3. Extract the public key body (between the BEGIN/END lines, newlines removed).
4. Ask the account owner/admin to run the setup SQL below.
5. Store the private key in the Vercel project environment variables.
6. Never commit either key.

### 5.4 Setup SQL template

The admin should adapt names and run this in a Snowflake worksheet. It is
additive and does not touch existing ELT objects.

```sql
-- 1. Role
CREATE ROLE IF NOT EXISTS PAPERSONAR_PUBLIC_RO
  COMMENT = 'Read-only role for the public PaperSonar chatbot';

-- 2. Warehouse
CREATE WAREHOUSE IF NOT EXISTS WH_PAPERSONAR_PUBLIC
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Public chatbot warehouse';

-- 3. Resource monitor
CREATE OR REPLACE RESOURCE MONITOR RM_PAPERSONAR_PUBLIC
  WITH CREDIT_QUOTA = 20
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 90 PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE WH_PAPERSONAR_PUBLIC
  SET RESOURCE_MONITOR = RM_PAPERSONAR_PUBLIC;

-- 4. Service user
CREATE USER IF NOT EXISTS SVC_PAPERSONAR_PUBLIC
  TYPE = SERVICE
  DEFAULT_ROLE = PAPERSONAR_PUBLIC_RO
  DEFAULT_WAREHOUSE = WH_PAPERSONAR_PUBLIC
  MUST_CHANGE_PASSWORD = FALSE
  COMMENT = 'Public chatbot read-only service user';

-- 5. Key-pair auth
ALTER USER SVC_PAPERSONAR_PUBLIC
  SET RSA_PUBLIC_KEY = '<PUBLIC_KEY_BODY_ONE_LINE>';

-- 6. Basic grants
GRANT USAGE ON DATABASE PAPERSONAR TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT USAGE ON SCHEMA PAPERSONAR.PROJECT_REPORTING TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT USAGE ON WAREHOUSE WH_PAPERSONAR_PUBLIC TO ROLE PAPERSONAR_PUBLIC_RO;

-- 7. View grants (run one per approved view)
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_GROWTH TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_OUTPUT_COVERAGE TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_CITATION_COHORTS TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_COMMUNITY TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_SOURCE_OBSERVATION TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_CATEGORY_COVERAGE TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_PUBLISHED_BATCH TO ROLE PAPERSONAR_PUBLIC_RO;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_PIPELINE_HEALTH TO ROLE PAPERSONAR_PUBLIC_RO;

-- 8. Role to service user
GRANT ROLE PAPERSONAR_PUBLIC_RO TO USER SVC_PAPERSONAR_PUBLIC;

-- 9. Verify
SHOW GRANTS TO ROLE PAPERSONAR_PUBLIC_RO;
DESC USER SVC_PAPERSONAR_PUBLIC;
```

### 5.5 Verification queries

Run these as the public role to prove least privilege:

```sql
USE ROLE PAPERSONAR_PUBLIC_RO;
USE WAREHOUSE WH_PAPERSONAR_PUBLIC;

SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_GROWTH;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_COHORTS;

-- These must fail:
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK;
```

Do not proceed if the base-table queries succeed.

---

## 6. Groq setup (primary)

Groq is the primary LLM provider. Use it for intent classification, entity
extraction, tool selection and answer composition.

1. Open `https://console.groq.com/`.
2. Sign in.
3. Open **API Keys**.
4. Create a key.
5. Store it in the Vercel project environment variables as `GROQ_API_KEY`.
6. Record the selected model in `GROQ_MODEL`.
7. Set a usage limit or budget alert if available.
8. Confirm the selected model supports JSON mode / tool calling.
9. Review the provider’s data-processing terms for public user prompts.

What to send back:

```text
GROQ_CONFIGURED=yes/no
GROQ_MODEL=
GROQ_USAGE_LIMIT=
```

---

## 7. Gemini setup (fallback)

Gemini Flash-class is the fallback provider. Configure it so a Groq outage or
rate limit does not take the chatbot down. It may also handle a specific task
if the 150-question evaluation shows Groq underperforms there.

### Recommended path

Use **Google AI Studio** for the first build:

1. Open `https://aistudio.google.com/`.
2. Sign in with the Google account that will own the project.
3. Create a new project or select an existing project.
4. Open **API keys**.
5. Create an API key for the project.
6. Copy the key directly into the Vercel project environment variables under
   `GEMINI_API_KEY`.
7. Enable billing/quota appropriate for fallback traffic.
8. Record the chosen model name in `GEMINI_MODEL`.
9. Review the provider’s data-processing terms for public user prompts.

### Production alternative

For stronger enterprise controls use **Vertex AI**:

1. Open Google Cloud Console.
2. Enable the Vertex AI API.
3. Create a service account for the API routes.
4. Grant only the Vertex AI user role.
5. Create a JSON key or workload identity.
6. Store credentials in the Vercel project environment variables.
7. Record the project, region and model.

### What to send back

Do not send the key. Send only:

```text
GEMINI_CONFIGURED=yes/no
GEMINI_PROVIDER=AI Studio or Vertex AI
GEMINI_MODEL=
GEMINI_PROJECT_ID=
GEMINI_REGION=
GEMINI_BILLING_ENABLED=yes/no
GEMINI_DATA_TERMS_APPROVED=yes/no
```

---

## 8. Vercel project (frontend + API)

### Recommended: one Vercel project, one origin

1. Create or sign in to a Vercel account.
2. Import the GitHub repository.
3. Set the project root to `apps/web` after it exists.
4. Set the framework preset to Next.js.
5. Keep the production branch as `main`.
6. Add the environment variables from section 4.2.
7. Add the custom domain.
8. Enable preview deployments for pull requests.
9. Confirm API routes use the Node runtime, not Edge.
10. Set each API route's `maxDuration` within your plan limit; keep the
    Snowflake SQL API timeout below that value.
11. Choose the Vercel region closest to the main users and the Snowflake
    account.
12. After the first deploy, call `/api/health` and confirm Snowflake, Redis and
    LLM connectivity.

No separate backend host or CORS setup is needed while the frontend and API
share the same origin.

What to send back:

```text
FRONTEND_HOST=vercel
VERCEL_PROJECT_READY=yes/no
VERCEL_PROJECT_ROOT=apps/web
VERCEL_PLAN=hobby/pro/enterprise
VERCEL_REGION=
VERCEL_DOMAIN=
VERCEL_FUNCTION_MAX_DURATION_SECONDS=
```

---

## 9. Backend on Vercel

### Recommended: Next.js route handlers + Snowflake SQL API

The backend is not a separate service. It lives inside the same Next.js
project:

```text
apps/web/src/app/api/chat/route.ts
apps/web/src/app/api/health/route.ts
apps/web/src/app/api/metrics/route.ts
apps/web/src/app/api/topics/route.ts
apps/web/src/app/api/data-status/route.ts
apps/web/src/app/api/feedback/route.ts
apps/web/src/app/robots.ts
apps/web/src/app/sitemap.ts

apps/web/src/server/snowflake/jwt.ts
apps/web/src/server/snowflake/client.ts
apps/web/src/server/snowflake/types.ts
apps/web/src/server/llm/
apps/web/src/server/metrics/
apps/web/src/server/chat/
config/public_metrics.yml
config/taxonomy.yml
sql/11_public_api/
```

Requirements:

- Use the **Node runtime** for routes that sign Snowflake JWTs. Do not use Edge.
- Use the stateless **Snowflake SQL API over HTTPS**; do not keep a long-lived
  `snowflake-connector-python` connection inside a serverless function.
- Load the private key from Vercel environment variables only.
- Set a short statement timeout (30 seconds or lower) and a route
  `maxDuration` above it.
- Use Upstash Redis over REST for cache and rate limiting.
- Stream only the final natural-language answer.
- Keep the API same-origin. Add CORS only if a separate frontend is introduced
  later.
- Use Vercel logs plus a request ID for every chat request.
- If a future feature needs long-running Python or background jobs, add a
  separate backend then. Do not add one for this MVP.
- Check the Vercel plan's function duration, concurrency and response-size
  limits. Use Pro if Hobby limits are too tight for Snowflake + LLM latency.

What to send back:

```text
BACKEND_HOST=vercel
BACKEND_RUNTIME=nextjs-route-handlers
BACKEND_SAME_ORIGIN=yes/no
SNOWFLAKE_SQL_API_TESTED=yes/no
VERCEL_FUNCTION_MAX_DURATION_SECONDS=
```

---

## 10. Redis / rate limiting

Use Upstash Redis or an equivalent managed Redis.

1. Create a Redis database.
2. Copy the REST URL and token.
3. Store them as `UPSTASH_REDIS_REST_URL` and
   `UPSTASH_REDIS_REST_TOKEN` in the Vercel project environment variables.
4. Set an eviction policy suitable for cache + rate-limit keys.
5. Confirm the region matches the Vercel function region.

What to send back:

```text
REDIS_CONFIGURED=yes/no
REDIS_PROVIDER=upstash
REDIS_REGION=
```

---

## 11. Domain and DNS

1. Choose the public domain or subdomain.
2. Confirm registrar access.
3. Point the frontend host to the domain.
4. Create `www` or apex redirect if needed.
5. Add TLS.
6. Set the canonical URL.
7. Add the domain to Vercel and analytics settings. No CORS setup is needed
   while the API stays on the same origin.

What to send back:

```text
DOMAIN=
DNS_ACCESS=yes/no
CANONICAL_URL=
```

---

## 12. Branding and visual assets

Required:

- [ ] Site name
- [ ] Tagline
- [ ] Logo (SVG preferred)
- [ ] Favicon
- [ ] Social preview image (1200×630)
- [ ] Preferred accent color, if any
- [ ] Tone: professional / editorial / energetic / academic
- [ ] Any colors to avoid
- [ ] Any typography constraints

Approved direction — see `PaperSonar.html` and
`05_FRONTEND_AND_DESIGN_SYSTEM.md`:

- single-page PaperSonar Research Terminal, not a multi-page editorial site
- dark monospace interface with light-theme support via `prefers-color-scheme`
- ink/graphite surfaces, red signal lines, green/red status dots
- inline sonar SVG mark; no mascot or robot avatar
- no Fraunces, Manrope, Google Fonts, gradients or generic SaaS theme

What to send back:

```text
SITE_NAME=
TAGLINE=
LOGO_PATH_OR_ATTACHMENT=
FAVICON_PATH_OR_ATTACHMENT=
SOCIAL_IMAGE_PATH_OR_ATTACHMENT=
COLOR_PREFERENCES=
COLOR_AVOID=
TONE=
```

---

## 13. Legal and attribution

Required before public launch:

- [ ] Privacy policy
- [ ] Terms of use
- [ ] Cookie policy, if analytics/cookies are used
- [ ] Source attribution and metadata licensing statement
- [ ] Disclaimer that citation counts are snapshots and do not measure quality
- [ ] Contact email
- [ ] Data controller/owner name
- [ ] Jurisdiction

Suggested wording points:

- PaperSonar stores metadata, not full text.
- Citation counts are observations, not live values.
- The corpus is not the whole of research.
- Sparse intersections are signals, not proof of novelty.
- Source licences and terms are respected.
- Users should not treat answers as investment, funding or policy advice.

What to send back:

```text
PRIVACY_POLICY_READY=yes/no
TERMS_READY=yes/no
COOKIE_POLICY_READY=yes/no
ATTRIBUTION_TEXT_READY=yes/no
CONTACT_EMAIL=
LEGAL_OWNER=
JURISDICTION=
```

---

## 14. Data and publication policy

Confirm:

- [ ] Only published batches are visible.
- [ ] Failed/unpublished batches are hidden.
- [ ] The public role cannot read bronze/silver/staging/base DW tables.
- [ ] Citation snapshots are labelled with `SNAPSHOT_DATE`.
- [ ] Data freshness is shown on every answer.
- [ ] “Not reportable” is a valid answer and must not be replaced by a guess.
- [ ] Topic aliases are approved; `rag` is a real category and is not silently
  mapped to AI/ML.
- [ ] Public answers may include aggregate counts, compact ranked text and
  inline terminal-style charts with accessible table fallbacks.
- [ ] Public answers may not include raw records, payloads or full text.
- [ ] CSV export, if enabled, contains only aggregate results.

What to send back:

```text
PUBLISHED_ONLY=yes/no
FAILED_BATCHES_HIDDEN=yes/no
PUBLIC_ROLE_VERIFIED=yes/no
CITATION_SNAPSHOT_LABEL=
TOPIC_ALIAS_POLICY=
AGGREGATE_ONLY=yes/no
CSV_EXPORT=yes/no
```

---

## 15. Budget and rate limits

Provide hard numbers:

```text
LLM_MONTHLY_BUDGET_USD=
LLM_DAILY_REQUEST_CAP=
SNOWFLAKE_MONTHLY_CREDIT_CAP=
SNOWFLAKE_WAREHOUSE_SIZE=
SNOWFLAKE_AUTO_SUSPEND_SECONDS=
MAX_QUESTIONS_PER_IP_PER_HOUR=
MAX_QUESTIONS_PER_SESSION_PER_DAY=
MAX_QUESTION_LENGTH_CHARS=
MAX_RESULT_ROWS=
QUERY_TIMEOUT_SECONDS=
VERCEL_FUNCTION_MAX_DURATION_SECONDS=
```

Recommended defaults:

- LLM budget: start small and measure
- Snowflake: X-Small, auto-suspend 60 s, resource monitor
- 20 questions/hour/IP
- 50 questions/day/IP
- 500 characters per question
- 200 result rows
- 30-second Snowflake SQL API timeout
- Vercel function duration above the query timeout and within plan limits
- kill switch `PUBLIC_CHAT_ENABLED=false`

---

## 16. Analytics, monitoring and operations

Recommended:

- privacy-friendly analytics (Plausible or PostHog)
- Sentry for frontend/backend errors
- uptime monitor on `/api/health`
- daily spend check
- weekly review of unanswered questions
- feedback review queue

What to send back:

```text
ANALYTICS_PROVIDER=
NEXT_PUBLIC_POSTHOG_KEY_CONFIGURED=yes/no
SENTRY_CONFIGURED=yes/no
UPTIME_MONITOR_CONFIGURED=yes/no
ALERT_EMAIL=
ONCALL_OWNER=
```

---

## 17. Acceptance catalogue

Provide or approve:

- [ ] The 150-question catalogue in
      `docs/chatbot/PUBLIC_WEBSITE_CHATBOT_PLAN.md`.
- [ ] 5–10 real questions from intended users.
- [ ] The “not reportable” behaviour.
- [ ] The “closest match” behaviour.
- [ ] The refusal wording.
- [ ] The definition of a successful answer.

Suggested acceptance rule:

> Every supported question returns a grounded answer or a correct
> clarification/refusal. No answer silently substitutes a topic, uses an
> unpublished batch, or invents a number.

What to send back:

```text
ACCEPTANCE_CATALOGUE_APPROVED=yes/no
REAL_USER_QUESTIONS_ATTACHED=yes/no
NOT_REPORTABLE_BEHAVIOUR_APPROVED=yes/no
CLOSEST_MATCH_BEHAVIOUR_APPROVED=yes/no
```

---

## 18. Required from you — final checklist

### P0 — blocks implementation docs

- [ ] Approve additive-only scope.
- [ ] Provide `PUBLIC_SITE_NAME` and `PUBLIC_DOMAIN`.
- [ ] Confirm the single Vercel project for frontend + API.
- [ ] Confirm API routes use the Node runtime.
- [ ] Create Snowflake public role/warehouse/user and grants.
- [ ] Register public key on `SVC_PAPERSONAR_PUBLIC`.
- [ ] Store private key in Vercel environment variables.
- [ ] Configure Groq API key.
- [ ] Confirm whether Gemini fallback is configured.
- [ ] Configure Redis/Upstash.
- [ ] Confirm public data scope.
- [ ] Approve visual direction.
- [ ] Approve legal/attribution plan.
- [ ] Approve budget and rate limits.

### P1 — blocks launch, not docs

- [ ] Gemini key, if used as fallback.
- [ ] Vercel preview and production environment variables.
- [ ] Logo/favicon/social image.
- [ ] Analytics provider.
- [ ] Sentry/uptime monitor.
- [ ] Support email.
- [ ] Real user questions.
- [ ] 150-question acceptance approval.
- [ ] Beta launch date.

### P2 — post-launch

- [ ] Login/accounts.
- [ ] CSV export.
- [ ] Saved questions.
- [ ] Email reports.
- [ ] Additional languages.
- [ ] More metrics beyond the initial catalogue.

---

## 19. What to send back to me

You can reply with this template. Do not include secret values.

```text
SITE_NAME=PaperSonar Research Assistant
DOMAIN=paper-sonar.vercel.app
FRONTEND_HOST=vercel
BACKEND_HOST=vercel
BACKEND_RUNTIME=nextjs-route-handlers
PUBLIC_DATA_SCOPE=All published PROJECT_REPORTING views
PUBLISHED_ONLY=yes
FAILED_BATCHES_HIDDEN=yes

SNOWFLAKE_PUBLIC_ROLE_CREATED=yes/no
SNOWFLAKE_PUBLIC_WAREHOUSE_CREATED=yes/no
SNOWFLAKE_PUBLIC_USER_CREATED=yes/no
SNOWFLAKE_PUBLIC_KEY_REGISTERED=yes/no
SNOWFLAKE_PUBLIC_KEY_STORED=yes/no
SNOWFLAKE_CONNECTION_TESTED=yes/no

GROQ_CONFIGURED=yes/no
GROQ_MODEL=
GROQ_USAGE_LIMIT=
GEMINI_CONFIGURED=yes/no
GEMINI_PROVIDER=AI Studio/Vertex
GEMINI_MODEL=
GEMINI_PROJECT_ID=
GEMINI_REGION=
GEMINI_BILLING_ENABLED=no
GEMINI_DATA_TERMS_APPROVED=pending
MODEL_ROUTING=groq-primary-gemini-fallback-free-tiers-only

REDIS_CONFIGURED=yes/no
REDIS_PROVIDER=upstash
REDIS_REGION=

VERCEL_PROJECT_READY=yes/no
VERCEL_REGION=
DNS_ACCESS=yes/no

BRAND_ASSETS_READY=yes/no
LEGAL_READY=yes/no
ANALYTICS_PROVIDER=PostHog (free tier)
ANALYTICS_READY=pending
SENTRY_READY=pending

LLM_MONTHLY_BUDGET_USD=0
SNOWFLAKE_MONTHLY_CREDIT_CAP=0 (free/trial credits only; resource monitor)
RATE_LIMIT_PER_HOUR=20
RATE_LIMIT_PER_DAY=50
MAX_RESULT_ROWS=50
QUERY_TIMEOUT_SECONDS=30
VERCEL_FUNCTION_MAX_DURATION_SECONDS=pending

ACCEPTANCE_CATALOGUE_APPROVED=yes
CLOSEST_MATCH_POLICY_APPROVED=yes
NOT_REPORTABLE_POLICY_APPROVED=yes

LAUNCH_OWNER=Team PaperSonar
SUPPORT_EMAIL=zohaib.mzg158@gmail.com
BETA_OR_PUBLIC=Public
```

---

## 20. Planned implementation documentation

This folder now contains **exactly 10 files** under `docs/agents/chatbot/`:

| # | File | Purpose |
|---:|---|---|
| 1 | `00_README.md` | Scope, reading order, non-negotiable rules |
| 2 | `01_ARCHITECTURE_AND_BOUNDARIES.md` | System architecture, additive boundaries |
| 3 | `02_SNOWFLAKE_PUBLIC_LAYER.md` | Role, warehouse, views, grants, SQL contracts |
| 4 | `03_METRIC_CATALOGUE_AND_QUESTIONS.md` | 150+ questions, metric contracts, resolver rules |
| 5 | `04_BACKEND_API_AND_LLM.md` | Next.js route handlers, Snowflake SQL API, Groq-primary/Gemini-fallback routing, LLM tools, validation, answer composition |
| 6 | `05_FRONTEND_AND_DESIGN_SYSTEM.md` | Next.js research terminal matching `PaperSonar.html`, tokens, components, UX |
| 7 | `06_SECURITY_COST_AND_OPERATIONS.md` | Rate limits, caching, budgets, monitoring |
| 8 | `07_IMPLEMENTATION_PLAN_AND_TESTS.md` | Step-by-step build order, tests, acceptance |
| 9 | `08_RUNBOOK_AND_LAUNCH.md` | Deploy, smoke test, rollback, launch checklist |
| 10 | `chatbot_req.md` | Owner requirements, access checklist, deployment runbook |

Ten files maximum; do not add another Markdown file here. Each model reads
`00_README.md` first, then its assigned file.

---

## 21. Deployment go/no-go

The code is already implemented and these local gates are green:

```text
pytest tests -q             270 passed
ruff check src tests        clean
npm ci                      install ok
npm run lint                clean
npm run typecheck           clean
npm test                    29 passed, including the 150-question eval
npm run build               passes on Next.js 16.4.6 / Turbopack
npm run test:e2e            3 passed
npm audit --omit=dev        0 vulnerabilities
```

Do not deploy until these are true:

- [ ] Snowflake role, warehouse, user, key pair and grants exist.
- [ ] `01_public_views.sql` and `02_public_grants.sql` were run by an admin.
- [ ] `03_public_verification.sql` succeeded as `PAPERSONAR_PUBLIC_RO`.
- [ ] Base-table SELECTs as the public role fail.
- [ ] Groq key and model ID are set.
- [ ] Gemini key and model ID are set, or `LLM_MODE=groq` is explicitly approved.
- [ ] Upstash REST URL and token are set.
- [ ] `IP_HASH_SALT` is set.
- [ ] Vercel root directory is `apps/web`.
- [ ] Domain and DNS are ready.
- [ ] No secret value has been pasted into Git, chat or a screenshot.

---

## 22. Deployment runbook — exact actions

### 22.1 What comes from where, and where it goes

| Item | Get it from | Put it in | Notes |
|---|---|---|---|
| Source code | This repository | Vercel import | Root directory must be `apps/web` |
| Site URL | Your chosen Vercel/domain URL | `NEXT_PUBLIC_SITE_URL`, `PUBLIC_APP_ORIGIN` | Same origin for API calls |
| Site name | Decision in Section 3 | `NEXT_PUBLIC_SITE_NAME` | Public value |
| Support email | Decision in Section 3 | `NEXT_PUBLIC_SUPPORT_EMAIL` | Public value |
| Chat switch | Decision in Section 3 | `PUBLIC_CHAT_ENABLED` | `true` to launch, `false` for kill switch |
| Snowflake account | Snowflake → Admin → Accounts | `SNOWFLAKE_ACCOUNT` | Account locator, no `https://`, no domain suffix |
| Snowflake SQL API URL | Snowflake account connection URL | `SNOWFLAKE_ACCOUNT_URL` | `https://<account>.<region>.snowflakecomputing.com` |
| Public user/role/warehouse | Section 5.4 setup | `SNOWFLAKE_PUBLIC_USER`, `SNOWFLAKE_PUBLIC_ROLE`, `SNOWFLAKE_PUBLIC_WAREHOUSE` | Use the names created in Snowflake |
| Database/schema | Existing project | `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA` | `PAPERSONAR`, `PROJECT_REPORTING` |
| Private key | Generated locally in 22.2 | `SNOWFLAKE_PUBLIC_PRIVATE_KEY` | Store base64 single-line; never commit |
| Key passphrase | Only if key is encrypted | `SNOWFLAKE_PUBLIC_PRIVATE_KEY_PASSPHRASE` | Leave blank for the unencrypted key below |
| Groq key | `https://console.groq.com` → API Keys | `GROQ_API_KEY` | Server-only |
| Groq model | Groq model list, free tier only | `GROQ_MODEL` | Use exact model ID |
| Gemini key | `https://aistudio.google.com` → API keys | `GEMINI_API_KEY` | Server-only |
| Gemini model | AI Studio model list, free tier only | `GEMINI_MODEL` | Use exact model ID |
| Routing mode | Decision in Section 3 | `LLM_MODE` | `auto`, `groq`, `gemini` or `off` |
| Upstash REST URL | Upstash console → database | `UPSTASH_REDIS_REST_URL` | Server-only |
| Upstash token | Upstash console → database | `UPSTASH_REDIS_REST_TOKEN` | Server-only |
| Hash salt | Generate locally in 22.2 | `IP_HASH_SALT` | At least 16 characters |
| PostHog key | PostHog → Project settings | `NEXT_PUBLIC_POSTHOG_KEY` | Public value |
| PostHog host | PostHog → Project settings | `NEXT_PUBLIC_POSTHOG_HOST` | Usually `https://us.i.posthog.com` or `https://eu.i.posthog.com` |
| Sentry DSN | Sentry → Project → DSN | `SENTRY_DSN` | Optional, server/client safe as configured |
| Domain | Registrar + Vercel → Domains | Vercel domain settings | TLS is issued by Vercel |

### 22.2 One-time local preparation

From `D:\PaperSonar\apps\web`, verify the code still passes:

```powershell
Set-Location 'D:\PaperSonar\apps\web'
node -v
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Node 20.9+ is required. The current machine has Node 24.15.0.

Generate the Snowflake key pair and a hash salt **outside the repository**:

```powershell
$keyDir = Join-Path $env:TEMP 'papersonar-keys'
New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
Set-Location $keyDir

openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -outform pem > papersonar_public_key.p8
openssl rsa -in papersonar_public_key.p8 -pubout -out papersonar_public_key.pub

# Public key body for Snowflake:
$pub = (Get-Content .\papersonar_public_key.pub | Where-Object { $_ -notmatch 'BEGIN|END' }) -join ''
$pub | Set-Clipboard

# Private key base64 for Vercel:
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes('.\papersonar_public_key.p8'))
$b64 | Set-Clipboard

# IP hash salt for Vercel:
openssl rand -hex 32
```

Rules:

- Paste the clipboard value from `$pub` into Snowflake `RSA_PUBLIC_KEY`.
- Paste the clipboard value from `$b64` into Vercel `SNOWFLAKE_PUBLIC_PRIVATE_KEY`.
- Paste the salt output into Vercel `IP_HASH_SALT`.
- Do not paste any of those values into this file, chat, GitHub or a ticket.
- The loader accepts either base64-encoded PEM or PEM with literal `\n`.

### 22.3 Snowflake setup order

1. As a human admin, run the role/warehouse/user/key/grant template in Section 5.4.
2. As the same admin, run, in order:

```text
sql/11_public_api/01_public_views.sql
sql/11_public_api/02_public_grants.sql
```

3. As `PAPERSONAR_PUBLIC_RO`, run:

```text
sql/11_public_api/03_public_verification.sql
```

4. Confirm base-table queries fail. Do not continue if they succeed.
5. Set the resource monitor credit quota to the approved cap. The template uses
   20 credits as a safety example; the approved LLM/Snowflake budget is USD 0,
   meaning free/trial credits only.

Never give `ACCOUNTADMIN` to the app, CI, Vercel or the public role.

### 22.4 Vercel dashboard deployment

1. Open `https://vercel.com/new` and import the GitHub repository.
2. Set **Root Directory** to `apps/web`.
3. Framework preset: **Next.js**. Next.js 16.4.6 is already in `package.json`.
4. Node version: 20.9+; choose Node 22 or 24 if prompted.
5. Leave install command as `npm ci`.
6. Leave build command as `npm run build`.
7. Add the variables from Section 4.2 to **Production** and **Preview**.
8. Add the same values to your local `.env.local` if you want parity.
9. Deploy.
10. Add the domain under **Project → Settings → Domains**.
11. Confirm `https://<domain>/api/health` returns `ok`.

CLI alternative after the variables are set in the dashboard:

```powershell
npm i -g vercel
vercel login
Set-Location 'D:\PaperSonar\apps\web'
vercel link
vercel env pull .env.local
vercel --prod
```

Do not commit the pulled `.env.local`.

### 22.5 Non-secret value examples

Use these as shape references only:

```text
NEXT_PUBLIC_SITE_URL=https://paper-sonar.vercel.app
NEXT_PUBLIC_SITE_NAME=PaperSonar Research Assistant
NEXT_PUBLIC_SUPPORT_EMAIL=zohaib.mzg158@gmail.com
PUBLIC_APP_ORIGIN=https://paper-sonar.vercel.app
PUBLIC_CHAT_ENABLED=true

SNOWFLAKE_ACCOUNT_URL=https://example_account.us-east-1.snowflakecomputing.com
SNOWFLAKE_ACCOUNT=example_account
SNOWFLAKE_PUBLIC_USER=SVC_PAPERSONAR_PUBLIC
SNOWFLAKE_PUBLIC_ROLE=PAPERSONAR_PUBLIC_RO
SNOWFLAKE_PUBLIC_WAREHOUSE=WH_PAPERSONAR_PUBLIC
SNOWFLAKE_DATABASE=PAPERSONAR
SNOWFLAKE_SCHEMA=PROJECT_REPORTING

LLM_MODE=auto
RATE_LIMIT_PER_HOUR=20
RATE_LIMIT_PER_DAY=50
```

If Gemini is not configured, set `LLM_MODE=groq`; health will show `degraded`
with `LLM_MODE=auto` and no Gemini fallback.

### 22.6 Post-deployment smoke test

Run these from PowerShell, replacing the domain:

```powershell
Invoke-RestMethod 'https://paper-sonar.vercel.app/api/health' | ConvertTo-Json -Depth 5
Invoke-RestMethod 'https://paper-sonar.vercel.app/api/topics' | ConvertTo-Json -Depth 5
Invoke-RestMethod 'https://paper-sonar.vercel.app/api/data-status' | ConvertTo-Json -Depth 5
```

Expected:

- `/api/health`: `status: ok`; env ok, Snowflake ok, Redis ok, provider checks configured.
- `/api/topics`: taxonomy and 24 metric definitions; no secrets.
- `/api/data-status`: published batch rows or a clear not-ready reason.

Then ask these in the terminal and verify denominator, caveat, as-of context and
source scope are present:

```text
Which topics grew fastest in 2024 vs 2025?
How many citations does RAG have?
Compare OpenAlex and Crossref coverage.
Which batches are published for each source?
What is RAG?
```

Reject any answer that invents a number, exposes a raw/base table name, ignores
suppression, or silently substitutes a topic.

### 22.7 Kill switch and rollback

To stop chat spend without removing the site:

1. Vercel → Project → Settings → Environment Variables.
2. Set `PUBLIC_CHAT_ENABLED=false` for Production.
3. Redeploy.
4. The terminal shows the maintenance state; data routes remain available.

To roll back a bad deploy:

1. Vercel → Deployments.
2. Choose the last healthy deployment.
3. Click **Rollback**.
4. Recheck `/api/health`.

Never roll back by editing extraction, SQL in `sql/00_*`–`sql/10_*`, workflows
or existing reporting views.

### 22.8 Common deployment failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `ENOENT ... D:\PaperSonar\package.json` | npm run from repo root | `Set-Location 'D:\PaperSonar\apps\web'` first |
| `/api/health` `not_ready` | Missing env or failed Snowflake/Redis check | Read `checks` and fill the missing variable |
| Snowflake JWT/auth failure | Wrong `SNOWFLAKE_ACCOUNT` or key format | Recheck account locator and base64 PEM |
| `429 RATE_LIMITED` | 20/hour or 50/day IP limit reached | Expected behaviour; wait or use another IP |
| Floating **N** on screen | Next.js dev indicator | Development only; absent on Vercel |
| No chart in answer | Suppressed, single-value or search answer | Expected; table fallback is used |
| Base-table query succeeds as public role | Grants are too broad | Stop deployment and fix grants |

The generated `apps/web/AGENTS.md` block is managed by Next.js. Keep it in the
commit; do not delete it.

---

**End of requirements and deployment runbook.**
