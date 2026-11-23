# 05 — Frontend and Design System

**Read after:** `04_BACKEND_API_AND_LLM.md`  
**Read before:** `06_SECURITY_COST_AND_OPERATIONS.md`  
**Owner:** frontend / design workstream  
**Visual source of truth:** `PaperSonar.html` in the repository root

---

## 1. Scope change

The frontend is **a single PaperSonar Research Terminal**, not a multi-page
editorial website.

`PaperSonar.html` is the exact visual specification. The Next.js implementation
must reproduce that screen: dark monospace terminal, three-column desktop grid,
left workspace rail, centre chat, right activity rail, status bar and footer.

The backend stack is unchanged:

- Next.js App Router
- TypeScript
- route handlers under `src/app/api/*`
- Groq primary / Gemini fallback
- Snowflake SQL API
- Upstash cache/rate limits

Only the presentation layer changes. Do **not** add the previously planned
Home/Explore/Topic/Compare/Institutions/Methodology/Data-status pages.

Canonical product name remains **PaperSonar Research Assistant** for metadata
and support. The UI displays exactly:

```text
PaperSonar
RESEARCH INTELLIGENCE
```

---

## 2. Reference screen

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ [sonar icon] PaperSonar          ● READY      + New chat                │
│              RESEARCH INTELLIGENCE                                     │
├───────────────┬─────────────────────────────────────┬───────────────────┤
│ WORKSPACE     │ ~/papersonar/terminal               │ ACTIVITY          │
│ ◉ AI Terminal │ ┌─────────┬─────────┬─────────────┐ │ ● Interface loaded│
│               │ │ MODE    │ ENGINE  │ EVIDENCE    │ │ ● Chat initialized│
│ STATUS        │ │ Research│ Ready   │ Enabled     │ │ ● Waiting for API │
│ ● Active      │ └─────────┴─────────┴─────────────┘ │                   │
│ ● Temporary   │ Welcome! Your research workspace…  │ ANSWER INCLUDES   │
│               │ YOU: Which topics grew fastest…    │ Summary           │
│               │ PAPERSONAR: …                      │ Metrics           │
│               │ [prompt chips]                     │ Evidence          │
│               │ [ Ask about published research... ] [Send]             │
├───────────────┴─────────────────────────────────────┴───────────────────┤
│ PAPERSONAR // RESEARCH TERMINAL        EPHEMERAL CHAT ●                 │
└─────────────────────────────────────────────────────────────────────────┘
```

This is the whole public interface. There is no login, no account menu and no
marketing landing page.

---

## 3. Exact design tokens

Copy these tokens from `PaperSonar.html` into `src/app/globals.css`.

### Dark theme (default)

```css
:root {
  --bg: #111216;
  --panel: #151419;
  --bar: #1b171c;
  --card: #17171c;
  --line: #a63e49;
  --soft: #4c343a;
  --text: #eeeaee;
  --muted: #9a98a2;
  --red: #f16b75;
  --green: #82c99a;
  --user: #261b20;
  --bot: #19181d;
}
```

### Light theme

```css
@media (prefers-color-scheme: light) {
  :root {
    --bg: #faf7f8;
    --panel: #f3eff1;
    --bar: #fff;
    --card: #fff;
    --line: #c9525e;
    --soft: #e2cfd2;
    --text: #1d1a1e;
    --muted: #6b6670;
    --red: #c4303c;
    --green: #1f8a4c;
    --user: #fbe9eb;
    --bot: #f1eef0;
  }
}
```

### Typography

```css
body {
  font: 17px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace;
}
```

- No Google Fonts.
- No Fraunces, Manrope, Space Grotesk or Source Sans 3.
- No serif display type.
- Numbers, labels and prose all use the same monospace family.

### Base rules

- `html, body { height:100%; width:100%; margin:0; }`
- `body { background:var(--bg); color:var(--text); overflow:hidden; }`
- `*{ box-sizing:border-box }`
- `button { font:inherit; cursor:pointer }`
- `prefers-reduced-motion` disables transitions/scroll behaviour.

---

## 4. Layout grid

Use the exact CSS from the HTML.

```css
.app { display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; }
.body { flex:1; min-height:0; display:grid; grid-template-columns:200px 1fr 230px; }
aside { background:var(--panel); padding:16px; overflow:auto; }
.left { border-right:1px solid var(--line); }
.right { border-left:1px solid var(--line); }
main { display:flex; flex-direction:column; min-width:0; min-height:0; }
```

Breakpoints:

- `min-width:1500px`: columns become `240px 1fr 280px`.
- `max-width:1000px`: columns become `180px 1fr`; right rail hidden.
- `max-width:700px`: single column; left rail hidden; body font 16px.
- `max-width:380px`: smaller stat labels; Send padding reduced; footer last span hidden.
- `max-height:480px`: hide `.stats` and `.path`.

Do not replace this with a generic responsive framework grid.

---

## 5. Routes

| Route | UI |
|---|---|
| `/` | The entire research terminal |
| `/api/chat` | Chat answers |
| `/api/health` | Status probe |
| `/api/feedback` | Optional feedback counter |

`/api/metrics`, `/api/topics` and `/api/data-status` may remain as safe support
endpoints, but they must not produce separate visible pages in this UI.

There is no `/chat`, `/explore`, `/topics/[key]`, `/compare`, `/institutions`,
`/methodology`, `/data-status` or `/about` page in the terminal UI.

If legal/methodology text is required, render it as an inline bot answer when
the user asks “How was this calculated?” or “What are the limits?”. Do not add
a visible navigation item.

---

## 6. Component mapping

Replace the previously planned editorial components with these.

```text
src/app/
  layout.tsx                  metadata, globals.css
  page.tsx                    renders <TerminalShell />
  globals.css                 exact CSS from PaperSonar.html
  api/
    chat/route.ts
    health/route.ts
    feedback/route.ts

src/components/
  terminal-shell.tsx          .app wrapper
  terminal-header.tsx         header, brand, READY, New chat
  terminal-left-rail.tsx      aside.left
  terminal-main.tsx           main: path, stats, messages, chips, form
  terminal-message.tsx        .m.bot / .m.user
  terminal-evidence.tsx       inline evidence block inside bot messages
  terminal-chart.tsx          inline SVG/CSS chart inside bot messages
  terminal-right-rail.tsx     aside.right
  terminal-footer.tsx         footer
  prompt-chips.tsx            .chips buttons

src/lib/
  api-client.ts               POST /api/chat
  analytics.ts                optional, content-free events
  format.ts                   compact numbers/dates
```

Do not implement `SiteHeader`, `HeroAsk`, `AnswerCard`, `EvidenceDrawer`,
`ChartBlock`, `TopicCard`, `ComparisonPanel`, `NotReportableCard`,
`ClarificationCard` or `FollowupChips` as separate page-level UI components.
Their responsibilities are folded into the terminal components above.

---

## 7. Header specification

Exact visible content:

```text
[sonar svg] PaperSonar          ● READY      + New chat
            RESEARCH INTELLIGENCE
```

- `.icon`: 44×44, 1 px `var(--line)` border, radius 8.
- SVG: three red sonar circles and two short signal paths, as in the HTML.
- `.logo`: 22 px, weight 700; `Sonar` uses `var(--red)`.
- `.sub`: 12 px, `var(--muted)`, letter-spacing `.06em`.
- `.hr`: 14 px; green `● READY`; New chat button 15 px, red text, transparent
  background, 1 px line border, radius 6.
- Hidden on `≤700px`: `.sub` and `.hr .muted`.

Status adaptation:

- default: `● READY` in `var(--green)`.
- degraded: `● DEGRADED` in amber.
- unavailable: `● OFFLINE` in `var(--red)`.
- text comes from `/api/health`; never invent readiness from a local guess.

`+ New chat` resets the conversation, shows the three prompt chips again,
generates a new `session_id`, and focuses the textarea.

---

## 8. Left rail

Exact content:

```text
WORKSPACE
◉  AI Terminal

STATUS
┌────────────────┐
│ INTERFACE      │
│ ● Active       │
└────────────────┘
┌────────────────┐
│ CHAT MEMORY    │
│ ● Temporary    │
└────────────────┘
```

- `.tag`: 12 px, muted, letter-spacing `.08em`.
- `.nav`: full-width, left-aligned, 12 px padding, `var(--user)` background,
  red text, 1 px line border, radius 6.
- `.box`: 1 px `var(--soft)` border, `var(--card)` background, radius 8,
  12 px padding.
- STATUS boxes are illustrative: chat memory is ephemeral and the interface is
  active. Do not claim persistence.
- Hidden entirely on `≤700px`.

Do not add more nav items. `AI Terminal` is the only workspace item.

---

## 9. Main column

### 9.1 Path bar

Exact copy:

```text
~/papersonar/terminal
```

Render as `.path`; `terminal` is bold red with normal font weight. Hidden on
short viewports (`max-height:480px`).

### 9.2 Stats strip

Three boxes only:

| Label | Value |
|---|---|
| `MODE` | `Research` |
| `ENGINE` | `Ready` |
| `EVIDENCE` | `Enabled` |

Use `.stats` grid with `repeat(3,1fr)`, 10 px gap, 12 px/16 px padding and
1 px `var(--soft)` separators. Values are 16 px, reducing to 14 px on mobile.

Do not replace these with corpus counts, provider names, charts or extra KPIs.

### 9.3 Messages

- Container: `#msgs`, `flex:1`, scrollable, 16 px padding, 12 px gap.
- `aria-live="polite"` is required.
- Message bubble: `.m`, 12 px/15 px padding, radius 10, max-width 90% (96% on
  mobile), `white-space:pre-wrap`, word wrapping.
- Bot: `.bot`, left aligned, `var(--bot)` background, `var(--soft)` border.
- User: `.user`, right aligned, `var(--user)` background, `var(--line)` border.
- Label: `<small>` in red, 12 px, letter-spacing `.06em`, uppercase.
- Bot label: `PAPERSONAR`.
- User label: `YOU`.

Welcome message on first load must be exactly:

```text
Welcome! Your research workspace is ready. Ask a question about published research.
```

The HTML demo reply (`This is a demo reply…`) must **not** appear in the
production app. Replace it with the real `/api/chat` result.

### 9.4 Prompt chips

Exact initial chips:

1. `Which topics grew fastest in 2025?`
2. `How many citations does RAG have?`
3. `Compare OpenAlex and Crossref coverage.`

- `.chips`: flex wrap, 8 px gap, 16 px horizontal padding, 10 px bottom padding.
- Buttons: 15 px, 8 px/14 px padding, 1 px line border, transparent background,
  red text, radius 18.
- Clicking a chip sends that exact question.
- Hide chips after the first submission (`display:none`), matching the HTML.
- `+ New chat` restores them (`display:flex`).
- On mobile, chip min-height 44 px.

### 9.5 Composer

- `form`: flex, 10 px gap, 12 px/16 px padding, top `var(--line)` border,
  `var(--bar)` background.
- `textarea`: flex:1, `rows=2`, no resize, 17 px, 10 px/12 px padding,
  radius 8, `var(--line)` border, `var(--bg)` background.
- Placeholder exactly: `Ask about published research...`
- Send button: 17 px, 0/20 px padding, no border, red background, white text,
  weight 700, radius 8.
- Enter submits; Shift+Enter inserts a newline.
- Empty submission does nothing.
- Clear the textarea immediately after submit.

The composer stays at the bottom of the main column. On mobile it sits above
the safe-area inset.

---

## 10. Right rail

Exact content:

```text
ACTIVITY
● Interface loaded
● Chat initialized
● Waiting for API

ANSWER INCLUDES
Summary
Metrics
Evidence
Caveats
```

- Dots: first two `var(--green)`, third amber (`#e0b24a` in dark mode).
- `.row`: flex, 10 px gap, 12 px font.
- The `ANSWER INCLUDES` box is a `.box` with line breaks, as in the HTML.
- Hidden at `≤1000px`.
- Activity updates with the same visual language:
  - initial rows stay until the first request
  - then append/replace with `Resolving question…`, `Querying published data…`,
    `Checking numbers…`, `Answer received`
  - use green for completed, amber for pending, red for failed.
- Do not turn the right rail into a chart or table panel.

---

## 11. Footer

Exact copy:

```text
PAPERSONAR // RESEARCH TERMINAL        EPHEMERAL CHAT ●
```

- 12 px, muted, 8 px/16 px padding, top line border, bar background.
- The final dot uses `var(--red)`.
- On `≤380px`, hide the last span.

No links, newsletter, social icons or legal nav in the footer.

---

## 12. Answer rendering inside the terminal

The `/api/chat` envelope from `04_BACKEND_API_AND_LLM.md` is still used. Render
it as terminal text, not as a card-based dashboard.

Bot message order:

```text
PAPERSONAR
[answer prose]

[compact inline evidence box when status=answered]
METRIC        M01 · Topic growth
FILTERS       ai-ml · 2024–2025
DENOMINATOR   distinct published outputs
AS OF         22 Nov 2026
SNAPSHOT      — or 21 Nov 2026
SOURCE        all primary sources
CAVEAT        Growth describes the retained published corpus.

[compact inline chart when chart data is available]
2024  ██████████ 1,240
2025  ████████████ 1,560

[compact table fallback / accessible rows]
YEAR   WORKS
2024   1240
2025   1560
```

Implementation rules:

- Use `.box` styling for inline evidence; do not add a drawer.
- Use `white-space:pre-wrap` for answer text.
- Render a chart when all are true: `status=answered`, `chart` is present,
  `rows.length >= 2`, values are numeric, nothing is suppressed.
- Supported chart types: `bar`, `hbar`, `line`. Use inline SVG or CSS bars only.
- No Recharts, Chart.js, canvas, Framer Motion or external chart library.
- Chart colours: primary `var(--red)`, positive `var(--green)`, grid/labels
  `var(--muted)`; no gradients and no multi-colour series soup.
- Keep the chart inside the bot bubble (`max-width:90%`, 96% mobile), max
  height 120 px desktop / 90 px mobile.
- Always render an accessible `<table>` with the same rows. It may sit inside
  the evidence box, but it must exist for screen readers and no-JS fallback.
- Do not chart single values, title search, data status, authorship lists or
  suppressed/not-reportable results.
- Do not put charts in the header, stats strip or right rail.
- No separate “Evidence” button; evidence and chart are inline under the answer.
- No `dangerouslySetInnerHTML`; build SVG from validated numeric values only.
- For `clarify`, render options as plain numbered lines inside the bot message
  and accept the option text as the next question.
- For `not_reportable`, use the same bot bubble with a red first line:
  `NOT REPORTABLE: …`
- For `unsupported` / `refused`, use plain bot text and offer a supported
  alternative in one short line.
- For `error` / rate limit, use bot text with the exact API message and a
  `Try again` chip-style button.
- Follow-up suggestions, if any, are plain text lines, not new component types.

This preserves the HTML’s sparse terminal feel while keeping every answer
grounded and receipt-bearing.

---

## 13. Behaviour state machine

```text
idle
  -> submit (chip/Enter/Send)
  -> pending: append YOU bubble; hide chips; activity = Resolving question…
  -> pending: activity = Querying published data…
  -> pending: activity = Checking numbers…
  -> answered/clarify/not_reportable/unsupported/refused/error
  -> append PAPERSONAR bubble; activity = Answer received or Failed
  -> idle
```

Rules:

- Disable Send while a request is in flight; re-enable on settle.
- Allow scrolling during pending; never force-scroll repeatedly.
- Store `session_id` in `sessionStorage` only.
- `+ New chat` clears `sessionStorage` and resets activity to the three
  initial rows.
- Do not store raw questions in analytics, localStorage or logs.
- If `/api/health` fails on load, show `● OFFLINE` and disable Send with the
  placeholder unchanged.

---

## 14. Accessibility

- Keep `aria-live="polite"` on `#msgs`.
- Add `aria-label` to the textarea, Send button, New chat button and chip
  buttons.
- Focus ring: 1 px `var(--red)` plus 2 px outline offset; visible on all
  controls.
- Colour is never the only signal: pair `●` with `READY`, `DEGRADED`, `OFFLINE`,
  `Active`, `Temporary`.
- `prefers-reduced-motion` is already in the reference CSS; keep it.
- Minimum target size 44×44 px on mobile for buttons and chips.
- Body text at 200% zoom must not require horizontal page scroll.
- The right rail is decorative/status; its text must still be readable by
  screen readers when visible.

---

## 15. Analytics

If PostHog is configured, send only:

```text
terminal_loaded
question_submitted        // no text
answer_received           // status only, no text
answer_failed             // error_code only
new_chat_clicked
prompt_chip_clicked       // chip index only, 1–3
```

Never send question text, answer text, session ID, IP or email.

---

## 16. SEO and metadata

- `title`: `PaperSonar — Research Intelligence`.
- Description: `A research terminal for published PaperSonar evidence.`
- `robots`: noindex not required; `/api/*` disallowed.
- Open Graph: use the sonar icon and title; no invented metrics.
- Canonical: `https://paper-sonar.vercel.app/`.

There is only one public page, so no sitemap of topic pages is needed.

---

## 17. Visual QA checklist

- [ ] Screen matches `PaperSonar.html` at 1440 px with all three columns.
- [ ] At 1200 px the right rail is hidden and left rail is 180 px.
- [ ] At 700 px and below only the main column is visible.
- [ ] At 380 px stat labels and footer adapt without overflow.
- [ ] At max-height 480 px path and stats are hidden.
- [ ] Dark and light `prefers-color-scheme` both match the HTML tokens.
- [ ] Welcome copy, chips, placeholder, footer and path copy are exact.
- [ ] Demo reply never appears.
- [ ] Enter submits and Shift+Enter makes a newline.
- [ ] New chat restores chips and clears messages.
- [ ] Evidence is inline, not a drawer or separate panel.
- [ ] Inline terminal charts render for series answers and have table fallbacks.
- [ ] No chart appears for suppressed, single-value or search answers.
- [ ] READY/DEGRADED/OFFLINE reflect `/api/health`.
- [ ] No Google Fonts, Tailwind theme, shadcn, Recharts or Framer Motion.
- [ ] Focus rings and 44 px mobile targets pass.

---

## 18. Acceptance for this document

- [ ] The public UI is a single research terminal at `/`.
- [ ] `PaperSonar.html` is the visual source of truth.
- [ ] Next.js route handlers remain the backend.
- [ ] All exact copy and tokens are reproduced.
- [ ] Real `/api/chat` answers replace the HTML demo reply.
- [ ] Charts are inline, terminal-styled and accessible; no chart library.
- [ ] No multi-page website components are implemented.
- [ ] `07_IMPLEMENTATION_PLAN_AND_TESTS.md` stages match this terminal spec.
