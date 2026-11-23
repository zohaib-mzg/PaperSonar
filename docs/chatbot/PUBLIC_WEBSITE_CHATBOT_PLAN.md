# PaperSonar Public Website + AI Research Assistant — Final Plan

**Status:** Planning only — no implementation started
**Date:** 2026-11-23
**Target:** Public-facing website with a grounded AI chatbot over the published
PaperSonar warehouse
**Constraint:** Additive only — do not disturb the existing extraction, SQL,
task graph, reporting views or GitHub workflows.

---

## 1. Executive decision

Build a public website with:

- a single-page **PaperSonar Research Terminal** frontend matching
  `PaperSonar.html` exactly
- a chat assistant that answers **150+ defined research questions**
- a controlled semantic layer over existing `PROJECT_REPORTING` views
- **Groq-hosted model as primary**, with **Gemini Flash-class model as the
  fallback**
- deterministic SQL templates — the LLM selects tools and parameters, it does
  **not** write arbitrary SQL
- clear “closest match”, “not reportable” and “not modelled” responses
- no direct browser access to Snowflake or API keys
- a separate read-only Snowflake role and public warehouse

This gives broad coverage without sacrificing the project’s core promise:
reproducible numbers, visible denominators and honest limitations.

---

## 2. Non-negotiable rules

1. **Existing features stay untouched.** New code lives in new directories. No
   edits to `src/extract`, `src/runner`, existing SQL objects, published views or
   the existing task graph.
2. **Snowflake only.** No PostgreSQL, SQLite or local-database fallback.
3. **No `ACCOUNTADMIN` for the application.** The public service uses a new
   read-only role; deployment uses the existing non-admin deployment role.
4. **No Snowflake credentials in the browser.** All database access goes through
   server-side route handlers.
5. **No arbitrary LLM-generated SQL.** The LLM selects an approved metric/tool
   and validated parameters; the server compiles parameterised SQL.
6. **Use published reporting views only.** No raw bronze, silver or staging
   tables are exposed.
7. **Every answer carries context:** metric definition, denominator, year or
   snapshot date, source, and a caveat when the result is suppressed.
8. **Never silently substitute one topic for another.** A closest-match answer
   must state the interpretation.
9. **Rate-limit, cache and timeout every public query.**
10. **No secrets, private keys or full env files in the repository or prompts.**

---

## 3. Product vision

### Name

**PaperSonar Research Assistant** — “Ask the research graph.”

### Promise

A visitor can ask a natural-language question about the published corpus and
receive:

- a direct answer
- the number and denominator
- a chart or ranked table
- the source and time window
- a plain-language caveat
- a “how was this calculated?” receipt
- follow-up questions they can ask next

### What it is not

- not a full-text search engine
- not a live citation tracker
- not a general-purpose chatbot
- not a prediction or causal-inference engine
- not a system that invents a topic when the taxonomy has no match

### Primary users

| User | Typical question |
|---|---|
| Research strategist | “Which topics grew fastest in 2025?” |
| Literature-review lead | “Which AI/ML papers have the most citations?” |
| Partnership/funding team | “Which institutions lead health sciences?” |
| Data steward | “Which sources have the weakest topic coverage?” |
| Evaluator | “How was this number calculated?” |

---

## 4. Site map

There is one public page: the **PaperSonar Research Terminal** at `/`.

| Region | Purpose |
|---|---|
| Header | Sonar mark, `PaperSonar / RESEARCH INTELLIGENCE`, ready status, `+ New chat` |
| Left rail | `WORKSPACE` (`AI Terminal`) and `STATUS` boxes |
| Main | Path bar, 3-box stats strip, chat messages, 3 prompt chips, composer |
| Right rail | `ACTIVITY` rows and `ANSWER INCLUDES` box |
| Footer | `PAPERSONAR // RESEARCH TERMINAL` and `EPHEMERAL CHAT ●` |

There is no multi-page navigation. Methodology, freshness and caveats are
rendered inline inside terminal answers when relevant. The route handlers
(`/api/chat`, `/api/health`, `/api/feedback`) remain server-only.

`PaperSonar.html` in the repository root is the visual source of truth.

---

## 5. Visual direction

### Concept

**“Research terminal.”**

A calm, monospace instrument panel: dark ink surfaces, red signal lines,
green/red status dots and compact evidence text. No marketing hero, editorial
magazine layout or SaaS dashboard chrome.

### Palette

| Token | Dark (default) | Light |
|---|---|---|
| `--bg` | `#111216` | `#faf7f8` |
| `--panel` | `#151419` | `#f3eff1` |
| `--bar` | `#1b171c` | `#fff` |
| `--card` | `#17171c` | `#fff` |
| `--line` | `#a63e49` | `#c9525e` |
| `--soft` | `#4c343a` | `#e2cfd2` |
| `--text` | `#eeeaee` | `#1d1a1e` |
| `--muted` | `#9a98a2` | `#6b6670` |
| `--red` | `#f16b75` | `#c4303c` |
| `--green` | `#82c99a` | `#1f8a4c` |
| `--user` | `#261b20` | `#fbe9eb` |
| `--bot` | `#19181d` | `#f1eef0` |

Theme follows `prefers-color-scheme`. No gradients.

### Typography

System monospace only:

```text
ui-monospace, SFMono-Regular, Consolas, monospace
```

Body 17 px/1.55; 16 px on mobile. No Fraunces, Manrope or Google Fonts.

### Layout and motion

- Three-column grid: `200px 1fr 230px`; `240px 1fr 280px` at ≥1500 px.
- At ≤1000 px hide the right rail; at ≤700 px hide the left rail.
- Full-height `100dvh`, `overflow:hidden`, internal message scrolling.
- 1 px borders, 6–10 px radii, no shadows.
- Reduced motion only; no entrance animation.

### Key components

- Header with sonar SVG and `● READY / DEGRADED / OFFLINE`.
- Left rail with only `AI Terminal` nav and two status boxes.
- Main path bar `~/papersonar/terminal` and three static stats boxes.
- Chat bubbles labelled `YOU` and `PAPERSONAR`, `aria-live="polite"`.
- Three fixed prompt chips; hidden after first submit, restored by New chat.
- Right activity rail with green/amber/red dots and `ANSWER INCLUDES` box.
- Inline evidence text and optional inline terminal chart under bot answers;
  no drawer or separate panel.

### Accessibility

- WCAG AA contrast using the token pairs above.
- Full keyboard navigation and visible focus.
- `aria-live` on the message region.
- Status is never colour-only; dots are paired with text.
- 44 px mobile targets and 200% zoom without horizontal scroll.

---

## 6. Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Vercel project — public app                                 │
│ Next.js research terminal + server route handlers           │
│ Single route: /                                              │
│ /api/chat · /api/health · /api/feedback                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS
        ┌──────────────────────┴──────────────────────┐
        │                                             │
┌───────▼──────────────────────┐  ┌───────────────────▼──────┐
│ Groq primary / Gemini       │  │ Snowflake SQL API        │
│ intent + tool selection      │  │ PAPERSONAR_PUBLIC_RO     │
│ grounded answer composition  │  │ WH_PAPERSONAR_PUBLIC     │
└──────────────────────────────┘  │ PROJECT_REPORTING views  │
                                  └──────────────────────────┘
```

### Recommended stack

| Layer | Choice |
|---|---|
| Frontend | Next.js App Router + TypeScript |
| Styling | Plain CSS in `globals.css` copied from `PaperSonar.html` |
| Charts | Inline SVG/CSS terminal charts; no chart library |
| Motion | None beyond reduced-motion-safe status changes |
| Icons | Inline sonar SVG from the HTML |
| Backend | Next.js route handlers (TypeScript, Node runtime) |
| Snowflake client | Snowflake SQL API over HTTPS with key-pair JWT |
| LLM primary | Groq-hosted model |
| LLM fallback | Gemini Flash-class model |
| Cache/rate limit | Upstash Redis (REST) |
| Frontend + backend hosting | Vercel (same project, same origin) |
| Chat transport | JSON `POST /api/chat` for MVP |
| SQL deployment | Existing `deploy-ci` or a dedicated additive workflow |

Vercel Functions are short-lived. Use the stateless Snowflake SQL API rather
than a long-lived Python connector. Routes that sign Snowflake JWTs must use
the Node runtime, not the Edge runtime.

### Why server-side routes are mandatory

A public frontend cannot securely hold Snowflake keys or LLM API keys. Vercel
route handlers run server-side and enforce:

- metric allowlists
- parameter validation
- SQL compilation
- read-only execution
- row limits
- statement timeouts
- caching
- rate limits
- audit logging

---

## 7. Additive repository layout

No existing file needs to be modified for the first release. New code lives in:

```text
apps/
  web/                         # Next.js public website + server routes
    src/app/                   # pages and route handlers
    src/app/api/               # /chat, /health, /metrics, /data-status
    src/server/                # Snowflake, LLM, metrics, security
config/
  public_metrics.yml           # metric catalogue and tool definitions
sql/
  11_public_api/               # new public views, grants, optional helper procs
docs/
  public_web/                  # design notes, runbook, decision log
tests/
  public_web/                  # API, resolver, SQL-contract and eval tests
```

### Existing objects reused, not edited

- `PROJECT_REPORTING.VW_TOPIC_GROWTH`
- `PROJECT_REPORTING.VW_OUTPUT_COVERAGE`
- `PROJECT_REPORTING.VW_CITATION_COHORTS`
- `PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS`
- `PROJECT_REPORTING.VW_RESEARCH_COMMUNITY`
- `PROJECT_REPORTING.VW_RESEARCH_OUTPUT`
- `PROJECT_REPORTING.VW_CITATION_SNAPSHOT`
- `config/taxonomy.yml`
- `config/quality_rules.yml`
- `sql/10_analytics/` reference queries
- `docs/phase3/METRIC_CATALOGUE.md`

### New Snowflake objects

One-time setup, additive and separate from the ELT path:

- role `PAPERSONAR_PUBLIC_RO`
- warehouse `WH_PAPERSONAR_PUBLIC` (X-Small, auto-suspend 60 s)
- resource monitor `RM_PAPERSONAR_PUBLIC`
- user `SVC_PAPERSONAR_PUBLIC` (key-pair only)
- grants: `USAGE` on database/schema/warehouse; `SELECT` only on public
  reporting views
- no grants on `PROJECT_STAGING`, `PROJECT_BRONZE`, `PROJECT_SILVER`,
  `PROJECT_DW` base tables, or unpublished data

The public API routes never use the ELT warehouse or the loader role.

---

## 8. Semantic layer and metric catalogue

The assistant is only as good as its metric definitions. Every supported
question maps to a metric family with:

- name and description
- allowed dimensions
- allowed filters
- SQL template ID
- denominator
- caveat
- minimum sample / suppression rule
- expected result schema

### Metric families

| # | Family | Example |
|---:|---|---|
| 1 | Topic growth | “Which topics grew fastest in 2025?” |
| 2 | Topic volume/share | “What share of the corpus is AI/ML?” |
| 3 | Citation impact | “What is the average citation count for AI/ML?” |
| 4 | Citation trends/cohorts | “How did citations change across snapshots?” |
| 5 | Topic intersections | “Which topic pairs co-occur most?” |
| 6 | Source coverage/metadata | “Which source has the weakest topic coverage?” |
| 7 | Institutions | “Which institutions lead health sciences?” |
| 8 | Authors/communities | “Who are the most prolific authors?” |
| 9 | Venues/output types | “Which venues have the highest citation impact?” |
| 10 | Open access/access status | “What share of outputs is open access?” |
| 11 | Time/period comparisons | “Compare 2024 and 2025 output counts.” |
| 12 | Cross-source/identity | “How many outputs appear in multiple sources?” |
| 13 | Search/discovery | “Find papers about retrieval-augmented generation.” |
| 14 | Rankings/comparisons | “Rank topics by citations per work.” |
| 15 | Data trust/freshness | “When was the data last updated?” |

### Coverage maths

With 15 metric families, 8–10 dimensions and 6 operations, the catalogue
supports:

- **150+ named question families**
- **1,000+ concrete parameter combinations**
- **67 taxonomy categories × 5 core metrics = 335 topic-specific variants**
- **5 sources × 8 metrics = 40 source-specific variants**
- **11 publication years × 14 metrics = 154 time variants**

The launch acceptance suite will contain **150 concrete questions**. Every
supported question must either return a grounded answer or a correct
clarification/refusal — never a silent guess.

---

## 9. 150-question launch catalogue

### 9.1 Topic growth and momentum

1. Which topics grew fastest in 2025?
2. Which topics declined in 2025?
3. Compare AI/ML growth in 2024 vs 2025.
4. Which topics grew fastest among Crossref outputs?
5. Which topics grew fastest among OpenAlex outputs?
6. What is the year-over-year growth of health sciences?
7. Which topics had the largest absolute increase in works?
8. Which topics had the largest relative increase?
9. Which topics are emerging but below the 30-work threshold?
10. Show the growth trend for physics from 2021 to 2025.

### 9.2 Topic volume and share

11. How many works are in AI/ML?
12. What share of the corpus is AI/ML?
13. Which topics have the most works?
14. Which topics have the fewest works?
15. How many classified vs unclassified works are there?
16. What is the topic coverage ratio by source?
17. Which topics appear in only one source?
18. How many works are unclassified?
19. What percentage of 2025 works are classified?
20. Show the top 10 topics by work count.

### 9.3 Citation impact

21. How many citations does AI/ML have?
22. What is the average citation count for AI/ML?
23. What is the median citation count for health sciences?
24. Which topics have the highest citation impact?
25. Which topics have the lowest citation impact?
26. How many citations does RAG have?
27. Compare citations for AI/ML and physics.
28. Which AI/ML outputs have the most citations?
29. What share of AI/ML outputs has zero citations?
30. What is the citation distribution for 2025 outputs?

### 9.4 Citation trends and cohorts

31. How have AI/ML citations changed across snapshots?
32. Which topics gained the most citations between snapshots?
33. Which topics lost citation rank?
34. Compare citation impact for 2024 and 2025 cohorts.
35. What is the citation trend for arXiv preprints?
36. Which source has the highest average citations?
37. Which output type has the highest citation impact?
38. How many citations per output by publication year?
39. Which topics have high citations but low volume?
40. Show citation gains for the top 10 outputs.

### 9.5 Topic intersections

41. Which topic pairs co-occur most?
42. Do AI/ML and health sciences intersect?
43. How many works combine AI/ML and physics?
44. Which topic pairs are reportable?
45. Which topic pairs are suppressed?
46. Compare intersections for 2024 and 2025.
47. Which topics bridge the most domains?
48. Which topic pairs grew fastest?
49. What share of AI/ML works also has health sciences?
50. Show top topic pairs by joint works.

### 9.6 Source coverage and metadata

51. Which source has the highest topic coverage?
52. Which source has the most works without a DOI?
53. Which source has the most works without a venue?
54. Compare coverage for OpenAlex and Crossref.
55. How many works have a missing publication year?
56. How many works have a missing author?
57. How many works have a language value?
58. Which topics are underrepresented in Crossref?
59. Which source contributes the most 2025 outputs?
60. Show metadata completeness by source and year.

### 9.7 Institutions

61. Which institutions have the most works?
62. Which institutions lead AI/ML?
63. Which institutions lead physics in 2025?
64. How concentrated is institutional credit?
65. Which countries have the most works?
66. Which institutions collaborate most?
67. Which institutions have the highest citation impact?
68. Which institutions are active in health sciences?
69. How many works have a resolved institution?
70. Show top institutions by topic.

### 9.8 Authors and communities

71. Who are the most prolific authors?
72. Which authors have the most citations?
73. Which authors work across multiple topics?
74. How many repeat authors are there?
75. Which authors are active in AI/ML?
76. Which authors publish across the most sources?
77. How many authors have an ORCID?
78. Which authors published in both 2024 and 2025?
79. What is the author-count-per-output distribution?
80. Show top authors for a topic.

### 9.9 Venues and output types

81. Which venues have the most works?
82. Which venues have the highest citation impact?
83. Which output types are most common?
84. How many datasets are in the corpus?
85. How many preprints are in the corpus?
86. Compare citation impact of articles vs preprints.
87. Which venues publish the most AI/ML work?
88. Which output types grew in 2025?
89. Which venues are associated with high-impact topics?
90. Show top venues by year.

### 9.10 Open access and access status

91. What share of outputs is open access?
92. How many outputs have unknown access status?
93. Which topics have the highest open-access share?
94. Compare open access by source.
95. Which institutions have the highest open-access share?
96. How has open access changed by year?
97. Which venues are most open access?
98. Do open-access works have more citations?
99. How many outputs are closed access?
100. Show open-access coverage by topic and year.

### 9.11 Time and period comparisons

101. How many works were published in 2024?
102. How many works were published in 2025?
103. Which year has the most works?
104. What is the publication-year distribution?
105. Compare 2020–2022 with 2023–2025.
106. Which topics grew most over the last five years?
107. Which topics declined over the last five years?
108. What is the partial-year effect for 2026?
109. Which years are under-represented in the corpus?
110. Show works by year and source.

### 9.12 Cross-source and identity

111. How many duplicate DOIs were removed?
112. How many outputs are observed by multiple sources?
113. Which outputs appear in both OpenAlex and Crossref?
114. Which source contributes the most canonical outputs?
115. How many source observations map to one output?
116. Which topics have the most cross-source agreement?
117. How many outputs have more than one source observation?
118. What share of outputs have a DOI?
119. How many outputs are source-only identities?
120. Show cross-source overlap by year.

### 9.13 Search and discovery

121. Find papers about retrieval-augmented generation.
122. Show recent papers on graph neural networks.
123. Find works by a specific author.
124. Find works from a specific institution.
125. Find papers in a specific venue.
126. Search titles containing “transformer”.
127. Find highly cited papers about climate.
128. Show papers with both AI/ML and health sciences categories.
129. Find datasets about genomics.
130. Search for a topic that is not in the taxonomy.

### 9.14 Rankings and comparisons

131. Compare AI/ML and physics.
132. Compare OpenAlex and Crossref coverage.
133. Compare 2024 and 2025 topic rankings.
134. Compare institutions in AI/ML.
135. Compare venues by citation impact.
136. Compare open access across sources.
137. Compare preprints and articles.
138. Compare topic growth across sources.
139. Rank topics by citations per work.
140. Rank institutions by output count.

### 9.15 Data trust and freshness

141. When was the data last updated?
142. Which batches are published?
143. How many DQ rules passed?
144. Which batch failed?
145. What is the current corpus size?
146. What is the topic coverage today?
147. Which sources are currently included?
148. How fresh are citation snapshots?
149. What data is not reportable?
150. Why is a topic missing from an answer?

---

## 10. How the assistant resolves a question

```text
1. Normalise the question
2. Classify into a metric family
3. Extract entities: topic, year, source, institution, author, venue, output type
4. Resolve aliases against config/taxonomy.yml and lookup tables
5. Check confidence
6. Select one or more approved tools
7. Validate parameters against the metric contract
8. Compile parameterised SQL
9. Execute as PAPERSONAR_PUBLIC_RO with timeout and row limit
10. Build the answer from the result rows
11. Attach denominator, caveat, metric ID and as-of date
12. Log the intent, query ID, latency and row count
```

### Closest-match rules

Use this order:

1. exact category or alias match
2. high-confidence semantic match
3. broader parent category
4. title/document search fallback
5. clarification question
6. polite refusal

Never silently swap a topic. Say:

> “I interpreted ‘RAG’ as AI/ML. Is that what you meant?”

or:

> “RAG is not a separate taxonomy category. Here is AI/ML citation data, and here are title matches for ‘RAG’.”

### Refusal vocabulary

| Situation | Response |
|---|---|
| Metric not defined | “I don’t have a defined metric for that yet.” |
| Metric defined but data absent | “That is not available in the current published corpus.” |
| Data present but under threshold | “Not reportable: one endpoint has fewer than 30 works.” |
| Outside scope | “That requires full-text or causal analysis, which this warehouse does not contain.” |
| Ambiguous term | “Do you mean AI/ML, or title matches containing ‘RAG’?” |

### Important data caveats the assistant must know

- The corpus is bimodal in time; 2025 is sparse.
- “Last year” means 2025 as of 2026.
- Citation counts are snapshots, not live counts.
- Topic coverage is a source property; Crossref and Zenodo have a lower ceiling.
- A sparse topic intersection is a signal, not proof of novelty.
- If either endpoint in a growth calculation has fewer than 30 works, suppress
  the ranking and show the counts.
- Institution credit is concentrated in one OpenAlex identifier; state that
  caveat when relevant.

---

## 11. LLM design and efficiency

### Recommended model split

| Task | Model | Why |
|---|---|---|
| Intent classification | Groq small/fast model | Primary, cheap, low latency |
| Entity extraction | Same Groq model as classifier | One call, JSON output |
| Complex multi-tool planning | Groq primary model; Gemini fallback | Strong structured reasoning with a safety net |
| Final answer composition | Groq primary model | Grounded, readable, controlled |
| Fallback when provider is down | Gemini Flash-class model | Availability |

**Start with Groq for the whole pipeline. Add Gemini as a fallback only when
Groq is unavailable or when a specific structured-planning task fails the
evaluation set. Do not run both models on every request by default.**

### Tool-calling contract

The LLM returns a structured plan, not SQL:

```json
{
  "metric": "topic_growth",
  "filters": {
    "category": "ai-ml",
    "start_year": 2024,
    "end_year": 2025,
    "source": null
  },
  "group_by": ["category"],
  "order_by": "growth_absolute",
  "limit": 10,
  "confidence": 0.94,
  "interpretation": "AI/ML category, 2024 to 2025, all sources"
}
```

The backend validates this against the metric contract, compiles SQL and
executes it.

### Token and cost efficiency

- Keep the system prompt compact: metric catalogue summaries, not the full
  schema.
- Use tool descriptions and 5–8 few-shot examples.
- Use JSON mode / structured output.
- Temperature 0.1–0.2.
- Max output tokens: 500–700.
- Stream only the final natural-language answer.
- Cache:
  - exact question → answer for 1 hour
  - metric + params → result for 15 minutes
  - taxonomy/aliases → in-process
- Use pre-aggregated reporting views; never scan raw facts for a public query.
- Route simple lookups to the cheap model; reserve the stronger model for
  multi-step comparisons.
- Cap follow-up context to the last 3 structured intents, not the full chat.
- Add a per-session question budget.

### Grounding rules

- The model may phrase the answer, but every number must come from SQL rows.
- The backend supplies a compact result table and caveats to the model.
- The model must not invent a number, year, source or category.
- If the result is empty or suppressed, the model must say so.
- The backend validates that all numeric tokens in the answer appear in the
  result payload; if not, fall back to a deterministic template.

---

## 12. Chat UX

The chat UX is the `PaperSonar.html` research terminal, not a two-panel
dashboard or a marketing page.

### Desktop

Three-column terminal grid:

- **Left:** `WORKSPACE` / `AI Terminal` and `STATUS` boxes.
- **Centre:** path bar, 3-box stats strip, messages, prompt chips, composer.
- **Right:** `ACTIVITY` rows and `ANSWER INCLUDES` box.

### Mobile

- Single column: only the centre terminal remains.
- No left or right rails.
- Composer stays at the bottom of the main column.
- No bottom sheet, no chart swipe and no separate evidence panel; inline charts
  stay inside the bot bubble.

### Answer anatomy inside a bot bubble

```text
PAPERSONAR
AI/ML grew from 1,240 works in 2024 to 1,560 works in 2025 (25.8%).

METRIC        M01 · Topic growth
FILTERS       ai-ml · 2024–2025
DENOMINATOR   distinct published outputs
AS OF         22 Nov 2026
SOURCE        all primary sources
CAVEAT        Growth describes the retained published corpus.
```

Evidence is rendered as compact text using the existing `.box` style. Series
answers may add a compact inline SVG/CSS chart above the table fallback. There
is no drawer, chart panel, headline-number card or feedback toolbar.

Chart rules: draw only for `answered`, non-suppressed results with at least two
numeric points; use `var(--red)` for the primary mark, `var(--green)` for
positive deltas and `var(--muted)` for labels/grid; keep height ≤120 px desktop
and ≤90 px mobile; always include the equivalent table for accessibility. No
chart for single values, title search, data status or suppressed results.

### Fixed prompt chips

- “Which topics grew fastest in 2025?”
- “How many citations does RAG have?”
- “Compare OpenAlex and Crossref coverage.”

### Multi-turn behaviour

- Store the last 3 structured intents, not raw SQL.
- Follow-ups reuse filters unless the user changes them.
- Always restate the interpretation when a filter is inherited.
- “Compare that with physics” should preserve the year and source.

---

## 13. API contract

All endpoints are Next.js route handlers in the same Vercel project and share
the public site origin.

### `POST /api/chat`

Request:

```json
{
  "session_id": "optional-uuid",
  "message": "Which topics grew fastest in 2025?"
}
```

Response:

```json
{
  "answer": "AI/ML grew ...",
  "metric": "topic_growth",
  "filters": {"year": 2025},
  "data": [],
  "chart": {"type": "bar", "series": []},
  "caveats": ["..."],
  "query_id": "PUBLIC_...",
  "as_of": "2026-11-22",
  "followups": ["..."]
}
```

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API routes and Snowflake readiness |
| `GET /api/metrics` | Public metric catalogue |
| `GET /api/topics` | Topic list and aliases |
| `GET /api/topics/{key}` | Topic detail |
| `GET /api/compare` | Comparison data |
| `GET /api/data-status` | Freshness, batches, coverage |
| `POST /api/feedback` | Answer quality feedback |

---

## 14. Security, privacy and cost controls

### Snowflake

- separate read-only role and warehouse
- `SELECT` only on public reporting views
- no grants on base tables or unpublished batches
- `STATEMENT_TIMEOUT_IN_SECONDS = 30`
- `QUERY_TAG = 'public-chatbot'`
- max 200 result rows
- resource monitor attached
- auto-suspend 60 seconds
- optional network policy for Vercel function egress

### Application

- API keys only in server-side Vercel environment variables
- same-origin API by default; no separate CORS surface
- allowlist a cross-origin only if a separate frontend is added later
- rate limit per IP/session (e.g. 20 questions/hour)
- max question length
- prompt-injection filtering
- no user-supplied SQL
- no secrets or stack traces in public errors
- structured audit log: timestamp, intent, metric, query ID, latency, row count
- privacy-friendly analytics; no unnecessary cookies
- clear attribution and source licensing

### Cost guardrails

- cache common questions
- pre-aggregate before exposing a metric
- avoid full scans
- cap output rows
- cap LLM output tokens
- disable expensive metrics by default
- monitor daily Snowflake and LLM spend
- kill switch: `PUBLIC_CHAT_ENABLED=false`

---

## 15. Testing and acceptance

### Functional

- 150/150 launch questions return a grounded answer or correct refusal.
- Every answer includes metric, denominator, as-of date and caveat.
- Closest-match questions state the interpretation.
- Unknown topics do not silently map.
- Multi-turn follow-ups preserve filters correctly.

### Contract

- Every metric has a SQL template and expected result schema.
- Every public view is covered by a SQL contract test.
- No public role can read a non-public table.
- No answer uses an unpublished batch.

### Security

- Prompt injection attempts cannot execute SQL.
- SQL injection strings are rejected as parameters.
- Rate limits work.
- Secrets never appear in client bundles or logs.
- Query timeouts and row limits work.

### Performance

- p95 cached response < 2 s.
- p95 uncached response < 8 s.
- Lighthouse performance/accessibility ≥ 90.
- Mobile layout verified at 360 px, 768 px, 1440 px.

### Visual

- Palette and typography approved.
- No generic black/blue-only theme.
- Charts accessible and readable in light/dark modes.
- Reduced-motion mode works.

---

## 16. Delivery plan — one integrated release

The work is sequenced internally but delivered as one coordinated feature, with
no changes to existing pipeline behaviour.

### Stage 0 — approvals and access

- approve this plan
- provide API keys and hosting access
- run one-time Snowflake public-role/warehouse setup
- confirm public data scope and legal text

### Stage 1 — semantic layer

- metric catalogue (`config/public_metrics.yml`)
- public views/grants in `sql/11_public_api/`
- SQL templates and contract tests

### Stage 2 — public API

- Vercel route handlers in the same Next.js project
- resolver, validator, SQL compiler, Snowflake SQL API client
- LLM tool calling and grounded answer builder
- cache, rate limit, logging
- same-origin deployment; no separate backend host

### Stage 3 — frontend

- Next.js app with a single terminal route `/`
- exact `PaperSonar.html` tokens, copy, grid and breakpoints
- terminal chat behaviour, inline evidence and status rails
- accessibility and responsive QA

### Stage 4 — evaluation

- 150-question acceptance suite
- security and performance tests
- accessibility and visual QA
- cost measurement

### Stage 5 — launch

- domain, TLS, analytics, legal pages
- staging smoke test
- production launch
- monitor errors, latency, spend and question quality

---

## 17. What I need from you

### Blocking — required before implementation

- [ ] Approve this plan and the additive-only boundary.
- [ ] Provide a **Groq API key** (and optionally a Gemini API key for fallback).
- [ ] Run or authorize the one-time Snowflake setup:
  - [ ] create `PAPERSONAR_PUBLIC_RO`
  - [ ] create `WH_PAPERSONAR_PUBLIC`
  - [ ] create `SVC_PAPERSONAR_PUBLIC`
  - [ ] grant `SELECT` on public reporting views only
- [ ] Confirm one Vercel project for the frontend and API route handlers.
- [ ] Provide the public domain/subdomain.
- [ ] Confirm that the published reporting views may be exposed publicly.
- [ ] Approve the visual direction and palette.
- [ ] Provide or approve legal copy:
  - privacy policy
  - terms of use
  - source attribution/licensing
  - contact email

### Important — needed before launch

- [ ] Gemini key, set up after development (fallback only).
- [ ] Logo: use the inline sonar SVG from `PaperSonar.html`.
- [ ] Analytics: PostHog free tier, no session replay or text capture.
- [ ] Rate limits: 20/hour and 50/day per IP; monthly budget USD 0.
- [ ] 5–10 real questions from intended users.
- [ ] Login: no login for MVP.
- [ ] Charts: inline terminal-style charts approved; no downloadable CSVs.
- [ ] Freshness wording: “As of latest snapshot” / “Updated after the latest
  published batch”.

### Nice to have

- [ ] Custom domain email for contact.
- [ ] Social preview image.
- [ ] External chart library preference — not needed; use inline SVG/CSS.
- [ ] Launch date and review process.
- [ ] Accessibility or branding guidelines.

---

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM gives a plausible wrong number | Deterministic SQL templates; numeric validation; no raw SQL |
| Ambiguous topic mapping | Alias resolver; confidence threshold; ask or show both |
| Public traffic burns Snowflake credits | Separate warehouse; cache; timeouts; rate limits; pre-aggregation |
| Prompt injection | No SQL execution from text; tool allowlist; read-only role |
| Provider outage | Groq primary with Gemini fallback; graceful error message |
| Data freshness confusion | “As of” and snapshot lines in every inline terminal receipt |
| Suppression rules ignored | Enforce thresholds in SQL, not in the prompt |
| Scope creep | 150-question catalogue and explicit unsupported behaviour |
| Existing pipeline disturbed | New directories only; no edits to existing objects/workflows |

---

## 19. Launch definition of done

- [ ] 150+ questions in the acceptance catalogue.
- [ ] 150/150 pass or return a correct clarification/refusal.
- [ ] Public role cannot access non-public tables.
- [ ] No secrets in frontend bundles.
- [ ] Rate limits and query timeouts verified.
- [ ] p95 latency targets met.
- [ ] Mobile and desktop visual QA passed.
- [ ] Accessibility checks passed.
- [ ] Required caveats and support contact available in terminal answers/metadata.
- [ ] Existing extraction, SQL and reporting features unchanged.
- [ ] Runbook, architecture note and metric catalogue committed.

---

## 20. Appendix A — metric catalogue shape

```yaml
version: 1

metrics:
  topic_growth:
    label: "Topic growth"
    description: "Change in published works per category between two years."
    tool: get_topic_growth
    sql: sql/11_public_api/metrics/topic_growth.sql
    dimensions: [category, year, source]
    filters:
      category: {type: category}
      start_year: {type: year}
      end_year: {type: year}
      source: {type: source, optional: true}
    defaults:
      min_works: 30
      limit: 10
    caveats:
      - "A growth ranking is suppressed when either endpoint has fewer than 30 works."
      - "The corpus is bimodal in time; 2025 is sparse."
    result_schema:
      - category
      - category_label
      - works_start
      - works_end
      - growth_absolute
      - growth_ratio
      - reportable
```

## Appendix B — public SQL principles

- `SELECT` only.
- Read from `PROJECT_REPORTING` views only.
- No `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` or DDL.
- Every metric has explicit `LIMIT`.
- Every query sets a statement timeout.
- Every query is tagged `public-chatbot`.
- Suppression is implemented in SQL, not in the LLM prompt.
- Published-batch filtering is inherited from the reporting views.

## Appendix C — example grounded answer

```json
{
  "answer": "AI/ML grew by 18.4% from 2,340 works in 2024 to 2,771 works in 2025. The ranking is reportable because both years exceed the 30-work threshold.",
  "metric": "topic_growth",
  "filters": {"category": "ai-ml", "start_year": 2024, "end_year": 2025},
  "caveats": [
    "Counts are distinct published outputs, not raw source rows.",
    "2025 is sparse in the current corpus."
  ],
  "as_of": "2026-11-22",
  "query_id": "PUBLIC_GROWTH_20241122_001",
  "followups": [
    "Compare AI/ML with health sciences.",
    "Show AI/ML citation impact.",
    "Which institutions lead AI/ML?"
  ]
}
```

---

**End of plan.** Approval of this document is the only action required before
implementation begins.
