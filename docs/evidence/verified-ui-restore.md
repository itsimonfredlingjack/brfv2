# Evidence — verified-UI restore, salvage-on-verified-data, and demo-tab dev-gating (2026-07-17)

Branch `cleanup/verified-ui` (off `feat/multispan-citation` @ `55c8aaa`). Context: an external
Gemini-based agent, believing this repo was a design mockup, three times attempted to wire the
chat/search UI to entirely fabricated data (invented pages, dates, quotes, relevance labels) via
`chatAdapter.js`/`searchAdapter.js`. All three attempts landed only in local git stashes, never in
committed history (verified below). This phase (a) proves the committed tree was never
compromised, (b) rebuilds the salvageable UX ideas strictly on real, verified pipeline data, (c)
hardens a tripwire so fabrication cannot silently return, and (d) — after a fresh-context
adversarial verifier found a *second*, unrelated source of the same class of risk — dev-gates
three pre-existing (non-Gemini) demo tabs that were still production-reachable.

No real BRF-document content appears anywhere below; only fabricated demo strings (already public
in this repo's own source, e.g. "SNÖRÖJNINGSAVTAL_2024.pdf") and suite counts.

## The invariant

No citation, source, page, quote, excerpt, relevance/score, or search count may render unless it
came 1:1 from the real retrieval/verification pipeline (`api.ask` → `AskResponse`:
`citations[]` verified by `resolve_citation`; `retrieval[]` real retrieval hits). Any adapter,
mock, fallback, or hardcoded payload that invents this data is forbidden — see
`.superpowers/sdd/cleanup-global-constraints.md`.

## Three-stash disposition (Simon decides final disposal — left untouched)

`git stash list` still shows all three, unmodified, exported read-only to
`.superpowers/quarantine/` (gitignored):

```
stash@{0}: On feat/model-free-completion: Third external intrusion: App.jsx/App.css chat-redesign edits (Gemini agent)
stash@{1}: On feat/model-free-completion: WIP unrelated to task-3: chat redesign (chatAdapter/searchAdapter) - stashed by task-3 agent to work from clean c6d5d47 baseline
stash@{2}: On feat/multispan-citation: WIP chat-UI refactor + chatAdapter (mock citations — predates model-free phase)
```

`.superpowers/quarantine/INVENTORY.md` found the three attempts are really **two lines of work**:
stash@{1} is a direct edit of stash@{2} (same fabrication shapes, stash@{1} additionally *removed*
the worst item — `_getMockFollowUpResponse` silently overriding real refusals — and added the
near-matches concept); stash@{0} is a separate, additive "Search" tab that depends on stash@{1}'s
`searchAdapter.js`. Nothing in any stash was ever committed to any branch (§4 below).

## Four lists

### 1. Quarantined (fabrication that never reached committed code, confirmed dead)

- `searchAdapter.js` (`stash-1-untracked/`): 100% hardcoded search results — invented pages,
  dates, verbatim "quotes", `scoreMeaning: 'Mest relevant'/'Relevant träff'/'Närliggande träff'`
  relevance labels, a fake 800 ms latency `setTimeout`, and a fallback branch whose own excerpt
  text admits `"...Denna träff är genererad som fallback."`. No backend `/search` endpoint exists
  to wire this to (confirmed: `src/api.js`'s full surface vs. `backend/app/main.py` routes).
- `chatAdapter.js` (`stash-1-untracked/`, `stash-2-untracked/`): fake multi-step pipeline-progress
  timing (`_simulatePipelineStep`, 600–1300 ms `setTimeout`s decoupled from real backend work); a
  `documentsSearched` "search count" `AskResponse` never reports; and — the single worst item in
  all three stashes — `_getMockFollowUpResponse()`, which on any refusal or empty-citation
  response **silently discarded the real refusal and substituted a fabricated confident answer**
  with a schema-shaped fake citation (`chunk_id: 'mock-chunk-1'`, invented `rects`, `score: 0.95`)
  — structurally indistinguishable from a verified `CitationOut`.

### 2. Restored (proven, not re-written — the committed tree was already clean)

- The real `askQuestion`/`api.ask` chat flow at `55c8aaa` was never touched by any stash's tracked
  diff reaching committed history. Task 1 turned that one-time manual verification into a
  permanent guarded property: the no-fabrication tripwire (below) plus render-path tests proving
  citations render exclusively from a mocked `api.ask()` response.

### 3. Salvaged (rebuilt on verified pipeline data only)

- **C2 — Dual-pane chat + source panel + clickable inline citations**: `CitationsPanel.jsx` lists,
  per AI message, exactly `msg.citations` (document_name/page/verified quote — multi-span keeps the
  `" […] "` marker, never joined seamlessly). `citationMarkers.js` linkifies only `[n]` tokens
  already present in the answer text that map to a real citation index; unmatched tokens and
  answers with no markers render exactly as returned. Every click opens the real page/rects
  verbatim via `openDocViewer`.
- **C3 — Considered no-answer state with real near-matches**: on refusal with non-empty
  `AskResponse.retrieval`, `ChatMessageList.jsx` renders a labeled "Hittade avsnitt — räckte inte
  för ett säkert svar" section using only real `RetrievalHit` fields
  (`backend/app/schemas.py`) — document name, page, text, score — explicitly captioned "inte
  använda för svaret" and visually distinct from citation chips (no `citation-chip` class
  anywhere). Opens the document at its page **without** rects (retrieval hits carry no verified
  geometry). Task 5 relabeled the score `Poäng:` → `Sökpoäng:` so it reads as a retrieval match
  score, never a verification confidence (`ChatMessageList.jsx:90`; test updated to assert the
  exact label).
- **C4 — Search: real path, not mock**: the committed UI's only search affordance is the
  Home/App-shell hero search box. It already routed to the real `askQuestion` flow with no new
  data claims — a one-liner handoff — so it was extracted to `HeroSearch.jsx` and kept, not
  rebuilt as a mock.

### 4. Deferred — not salvaged

- **Gemini's Search results view** (stash@{0}'s tab): depends entirely on `searchAdapter.js`
  fabrication with no backing backend endpoint. Not rebuilt; would require a real, verified
  `/search` endpoint first.
- **The three pre-existing (non-Gemini) demo tabs** — Granskning (QA review), Bevakningar
  (timeline), and the Document Canvas they open. These are leftover design-template scaffolding
  from before this phase, not part of the Gemini incident, but a fresh-context adversarial
  verifier found them production-reachable and violating the same invariant (see next section).
  Not deleted and not salvaged onto real data (no backend page-level QA-review or timeline
  extraction exists); **dev-gated** instead — see below.

## Adversarial verifier: per-surface verdicts + the demo-tab finding

A fresh-context subagent (no design context, only the invariant statement and the source) was
dispatched with one job: find any path in the chat/search UI where unverified or fabricated data
can reach the user.

- **C1–C4 surfaces (chat, citations panel, near-matches, hero search): CLEAN.** No fabrication
  path found; citations/retrieval hits trace 1:1 to `AskResponse` fields at every render site.
- **Tripwire evasions identified** (none present in the committed tree at the time, but not yet
  guarded against): (a) an object literal combining a source-document-name-like key
  (`sourceDoc`/`doc`/`document_name`) holding a **literal string**, paired with a page-like key —
  a citation-lookalike with no `quote` key, invisible to the original quote+rects/page signature;
  (b) a literal multi-sentence Swedish text under an `extractedText`-like key, impersonating real
  OCR/parser output.
- **Finding: three PRE-EXISTING demo tabs were production-reachable.** Granskning
  (`qaDocuments`, formerly `App.jsx:291-443`, rendered `~:797-1056`), Bevakningar
  (`timelineData`, formerly `App.jsx:461-465`, rendered `~:1058-1097`), and the Document Canvas
  they open (`cardData`, `navigateToDoc`, `handleSearch`, `src/components/DocumentView.jsx`,
  `ContextCard.jsx`) rendered exactly the two evasion shapes above — hand-authored, hardcoded
  document names/pages/"extracted text" with no real extraction behind them, reachable by any
  logged-in user in a production build (no feature flag, no env gate existed before this task).

**Resolution (Simon's decision): dev-gate the demo tabs** — hidden in production builds, intact
for dev-server demos — rather than delete or attempt to salvage them onto real data that doesn't
exist yet (no backend page-level QA/OCR-review or timeline-extraction endpoint).

## How the dev-gate works (Task 5)

- **`src/demoData.js`** — the single product module allowed to contain pipeline-class data shapes
  (a literal source-document name + page, "extracted" body text, a quote+rects pair). Header
  comment states it is fabricated demo scaffolding, dev-only. Exports the former `qaDocuments`
  seed, `timelineData`, `cardData` (all previously in `App.jsx`), and `documentData` (previously
  in `DocumentView.jsx`).
- **`src/components/DemoWorkspace.jsx`** — a new component holding *all* Granskning/Bevakningar/
  Document-Canvas state and rendering (moved verbatim out of `App.jsx`: `qaDocuments` state,
  page-review handlers, timeline rendering, canvas navigation/search/activation). Imports
  `demoData.js` and `DocumentView.jsx`/`ContextCard.jsx`. Adds a small `"Demo — exempeldata"`
  badge (`.demo-badge` in `App.css`) to each of the three surfaces' headers.
- **`src/appModes.js`** exports the pure helper `demoTabsEnabled(isDev) => Boolean(isDev)`. Every
  *rendering* decision in `App.jsx` (sidebar nav items for Granskning/Bevakningar, the tab-body
  switch, the Document Canvas branch) is gated on `demoTabsEnabled(import.meta.env.DEV)`.
- **The production-bundle guarantee** is a second, separate mechanism from the rendering gate:
  `App.jsx` reaches `DemoWorkspace` only via
  `import.meta.env.DEV ? React.lazy(() => import('./components/DemoWorkspace')) : null` — a
  *literal* `import.meta.env.DEV` check (not routed through `demoTabsEnabled()`), which is what
  lets Vite/esbuild fold the whole ternary and eliminate the `import()` call from the production
  module graph, not just skip rendering its result. `navigateToDoc`'s only effect
  (`setActiveDocument('snorojning')`) now lives inside `DemoWorkspace` itself, called via a prop —
  in production, `DemoWorkspace` never mounts, so `activeDocument` can never become truthy and the
  Document Canvas branch is unreachable by construction, not just visually hidden.

### Prod-surface proof: `npm run build` + `dist/` grep

```
rm -rf dist && npm run build
grep -rl "SNÖRÖJNINGSAVTAL\|Chunking-karta\|STYRELSEPROTOKOLL_MARS\|STADGAR_BRF_LAPPEN\|Global Tidslinje\|Granskning (QA)\|exempeldata" dist/
# exit 1 — no matches
grep -rl "DemoWorkspace\|demoData" dist/
# exit 1 — no matches
```

Result: **zero demo markers in `dist/`.** The build emitted a single JS chunk
(`dist/assets/index-*.js`, ~658 kB) — no separate `DemoWorkspace`/`demoData` chunk was even
created, confirming Vite/Rollup eliminated the guarded `import()` call before chunk-graph
construction, not merely at the minification stage. (If this result had gone the other way — the
chunk present but unfetched at runtime — the plan was to report it honestly as a finding and fix
it, not explain it away; that fallback was not needed.) Dev-server behavior verified unchanged:
`vite dev` serves `DemoWorkspace.jsx`/`demoData.js` on request (HTTP 200, transformed correctly)
regardless of the production-build outcome, since Vite's dev server does no bundling.

## Tripwire (`src/no-fabrication.test.js`)

Scans all `src/` product files (excluding `*.test.jsx?`, `test-setup.js`, and — new in Task 5 —
`src/demoData.js`, the single allowlisted file) for seven signatures:

1. `searchAdapter` module reference (stash@{0}, catalog #1-4).
2. `chatAdapter` module reference (stash@{1}/{2}, catalog #5-7).
3. `getMockFollowUpResponse`/`_getMockFollowUpResponse` (stash@{2}, catalog #7).
4. `mock-chunk` chunk ids (stash@{2}, catalog #8).
5. A `quote:` key co-occurring with `rects:`/`page:` in the same object literal (stash@{2},
   catalog #9-10) — brace-balanced enclosing-literal check, not just same-file co-occurrence.
6. **New (Task 5)**: a `sourceDoc`/`doc`/`document_name` key holding a **literal string value**
   co-occurring with a `page:` key in the same object literal — the citation-lookalike-without-a-
   `quote`-key evasion. Scoped to literal string values specifically so legitimate reads like
   `c.document_name` (a variable holding real response data, used throughout the render path)
   never false-positive.
7. **New (Task 5)**: a literal string longer than 40 characters under an `extractedText`-like key
   — the fabricated-OCR-text evasion.

A separate "demoData allowlist" describe block (also in `no-fabrication.test.js`) keeps the
`demoData.js` exclusion honest by parsing every product file's static/dynamic import statements:

- `demoData.js` is imported by exactly `DemoWorkspace.jsx` and `DocumentView.jsx` — nothing else,
  including `App.jsx`.
- `DemoWorkspace.jsx` is never statically imported by anything (only dynamically, from `App.jsx`,
  behind the `import.meta.env.DEV` literal); `DocumentView.jsx` is never statically imported by
  anything other than `DemoWorkspace.jsx` itself.
- `App.jsx` reaches `DemoWorkspace` only via the exact dead-code-eliminable pattern above.

### RED/GREEN proof (temporary plants, never committed)

Both new signatures, planted then removed in the same session:

```
# Planted src/_tripwire_plant.js:
#   export const plantA = { sourceDoc: 'PLANTAD_FIL.pdf', page: 3, title: 'plant' };
#   export const plantB = { extractedText: `<48-char Swedish sentence>` };
npx vitest run src/no-fabrication.test.js
#   FAIL × source-document-name literal + page-like key ...
#   FAIL × extractedText-shaped literal ...
#   Tests  2 failed | 10 passed (12)   <- RED, both new signatures fire
rm src/_tripwire_plant.js
npx vitest run src/no-fabrication.test.js
#   Tests  12 passed (12)              <- GREEN
```

The demoData-allowlist boundary was proven the same way (planted a stray
`import { qaDocuments } from './demoData'` inside `src/api.js`, confirmed the allowlist test fails
naming `src/api.js` as the unexpected importer, reverted, confirmed green).

Zero false positives on the current tree confirmed (all 12 `no-fabrication.test.js` tests green
on the final committed state).

## Presentation note resolved

`ChatMessageList.jsx:90`'s near-match score label changed `Poäng:` → `Sökpoäng:` (the raw score
value is unchanged) so it reads as a retrieval match score, not a verification confidence that
could be confused with a citation panel's certainty. `ChatMessageList.test.jsx`'s near-matches
test now asserts the exact label text (`` `Sökpoäng: ${hit.score}` ``), not just score-value
containment.

## Pre-existing items left for triage (not in scope this phase)

- Dead Documents-toolbar search input (`App.jsx:457`, placeholder "Sök dokumentnamn...") — no
  `onChange`/filtering wired.
- Dead QA "Test-sök" subtab input (`DemoWorkspace.jsx`, formerly `App.jsx:1041-1051`) — inside the
  now dev-gated Granskning tab; still a non-functional input, unchanged behavior.
- Documents-table `status-badge` always renders `"Klar"` (`App.jsx:502`) regardless of actual
  processing state — no backend status field is read.
- ~~Near-match score label ambiguity~~ — **resolved this task** (see above).

## Suite counts (reproduce commands)

```
cd backend && uv run pytest -q
# 197 passed, 1 skipped, 6 warnings   (baseline at 55c8aaa — unchanged; backend untouched all phase)

cd backend && uv run pytest tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py -q
# 47 passed, 6 warnings               (unchanged)

npm test
# 8 test files, 56 tests passed
#   (47 pre-Task-5 baseline + appModes.test.js's 3 new tests + no-fabrication.test.js growing
#    from 6 to 12 tests [+2 new signatures, +4 demoData-allowlist] = 47 + 3 + 6 = 56)

npm run lint
# oxlint, exit 0 — 5 warnings, all pre-existing (unused-var/param, confirmed against the
# pre-Task-5 tree via `git stash` diff — none introduced by this task)

rm -rf dist && npm run build
# vite build, single JS chunk (~658 kB) + CSS + pdf.worker — no separate demo chunk
grep -rl "SNÖRÖJNINGSAVTAL\|Chunking-karta\|exempeldata\|DemoWorkspace\|demoData" dist/
# exit 1 (no matches) — see "Prod-surface proof" above
```
