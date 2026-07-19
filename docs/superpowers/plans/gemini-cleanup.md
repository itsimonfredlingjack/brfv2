# Plan — quarantine fabricated UI, restore verified state, salvage on verified data only

Branch: `cleanup/verified-ui` off `feat/multispan-citation` (55c8aaa). Don't push.
Context: an external Gemini-based agent edited this repo believing it was a mockup, adding
client-side adapters (`chatAdapter.js`, `searchAdapter.js`) and Home/Search + chat rewrites
that FABRICATE citations and search results (hardcoded pages, dates, quotes, relevance labels).
All intrusions are preserved in three stashes and exported to `.superpowers/quarantine/`
(gitignored); the committed history is verified intrusion-free (see
`.superpowers/quarantine/INVENTORY.md`). This phase proves the restore, adds a tripwire so
fabrication cannot silently return, and rebuilds ONLY the approved UX ideas on real verified
pipeline data.

## Global Constraints (binding for every task)

1. **The invariant, extended to the UI:** no citation, source, page, quote, excerpt,
   relevance/score, or search count may be rendered unless it came from the real
   retrieval+verification pipeline (`api.ask` → `AskResponse`: `citations[]` are verified by
   `resolve_citation`; `retrieval[]` are real retrieval hits; everything else on screen must be
   derived 1:1 from these). Any adapter, mock, fallback, or hardcoded payload that invents this
   data is forbidden. If a UI feature cannot be backed by verified data, it is left clearly
   disabled/empty — exactly like the refusal path — never faked.
2. **Presentation may not imply more than verification proved.** Multi-span display strings
   keep the `" […] "` discontinuity marker; fragments are never joined into a seamless
   sentence. Inline citation markers may be rendered only where they map 1:1 to a verified
   citation in `citations[]`; never invent an in-text position the response did not contain.
   Retrieval hits shown in a no-answer state must be labeled as not-used-for-an-answer.
3. **Zero live-model dependencies; zero fabrication in tests' product code.** Tests mock the
   HTTP layer (test scaffolding), never add mock data paths to product code. No real-document
   content in committed files (metrics only).
4. **Suites green:** backend offline `cd backend && uv run pytest -q` (baseline at 55c8aaa:
   197 passed, 1 skipped) and isolation (47) untouched and green; frontend `npm test`,
   `npm run lint`, `npm run build` green. This branch has NO vitest infra at its base — Task 1
   bootstraps it identically to the config on `feat/model-free-completion` (vitest,
   @testing-library/react, @testing-library/jest-dom, jsdom; `vitest.config.js`,
   `src/test-setup.js`, script `"test": "vitest run"`) so the eventual merge is a trivial dedup.
5. **Git:** commit on `cleanup/verified-ui`; never push; never commit `.superpowers/`,
   `backend/out/`, `backend/data/`, corpus folders. The three stashes must remain untouched
   (Simon decides their final disposal).
6. **Style:** user-facing strings Swedish; code/comments English; match existing conventions.
7. **Scope:** cleanup + salvage-on-verified-data only. No local/12B model work, no
   scanned-ingestion work (that lives on `feat/model-free-completion`), no new features beyond
   the approved salvage list.

## Task 1 — Prove the restore + fabrication tripwire (test infra bootstrap)

The committed tree at 55c8aaa is already free of the fabricating code (inventory-verified);
this task turns that state into a proven, guarded property.

- Bootstrap the frontend test infra per Global Constraint 4.
- **Tripwire test** (`src/no-fabrication.test.js` or similar): scans `src/` product sources
  (not test files) and fails if fabrication signatures reappear: any `searchAdapter` /
  `chatAdapter` module, `getMockFollowUpResponse`/`_getMockFollowUpResponse`, `mock-chunk`
  chunk ids, or any literal object/array assigning BOTH `quote`-like and `rects`/`page`-like
  keys outside a test file (tune the signature list from
  `.superpowers/quarantine/INVENTORY.md`'s fabrication catalog; keep it precise enough to have
  zero false positives on the committed tree — document each signature with one line on what
  incident it guards against). This mirrors the repo's "prove the negative with a tripwire"
  lesson (NOTES.md egress audit).
- **Render-path test**: component tests proving the chat flow renders citations exclusively
  from the `api.ask` response: (a) a mocked HTTP `ask` returning a refusal with zero citations
  renders zero citation chips and no source metadata; (b) a mocked response with N citations
  renders exactly N chips whose page/document text match the response fields verbatim; (c) an
  `api.ask` network error renders the error state with zero citations.
- Confirm `npm run build` output contains no `searchAdapter`/fabrication code (trivially true;
  assert via the tripwire, not the bundle).
- Backend suites untouched and green.

## Task 2 — Dual-pane chat with source panel + clickable inline citations (verified data only)

Rebuild the two approved UX ideas on the committed verified flow (`askQuestion`,
`src/App.jsx:209`; chips at `App.jsx:1312-1326`; `PdfViewer` already renders multi-rect
highlights):

- **Dual-pane layout:** chat pane + collapsible source panel. The panel lists, per AI message,
  its verified citations: `document_name`, `page`, and the verified excerpt — `quote` display
  string exactly as returned (multi-span keeps `" […] "`; optionally render `quotes[]` as
  separate fragment lines, never joined seamlessly). Panel entries and chips come only from
  `msg.citations` (the `AskResponse.citations` array). Rejected citations stay what they are
  today (a count notice) — never displayed as sources.
- **Clickable citations:** each panel entry / chip opens the real source via the existing
  `openDocViewer(c, { page: c.page, rects: c.rects, highlightPage: c.page })` — correct page,
  verified highlight rects. Inline `[n]` markers in the answer text: render a linkified marker
  ONLY for explicit `[K<n>]`/`[<n>]` tokens already present in the answer string that map to
  citation n in `citations[]`; unmatched tokens render as plain text; when the answer has no
  markers, chips/panel are the affordance — do NOT inject markers into the text.
- Component tests (mocked HTTP layer only): panel renders exactly the response's citations;
  click payload carries the response's page/rects verbatim; multi-span excerpt keeps the
  marker; no-marker answers get no injected markers.
- Keep `npm run lint`/`build` green; no backend changes.

## Task 3 — Considered no-answer state with real near-matches

On refusal (`refusal: true`), today the UI shows the refusal text. Extend, on verified data
only:

- If `AskResponse.retrieval` is non-empty, show a clearly-labeled near-matches section
  ("Hittade avsnitt — räckte inte för ett säkert svar" or similar Swedish): per hit, the real
  `RetrievalHit` fields only (document name/page/score/preview as the schema provides — check
  `backend/app/schemas.py` `RetrievalHit` for the exact fields; render nothing the schema
  doesn't carry). Each entry opens the document at its page via `openDocViewer` WITHOUT
  highlight rects (retrieval hits have no verified rects — passing none is the honest state).
- If `retrieval` is empty → current behavior (refusal text alone).
- These entries must be visually distinct from verified citations (no citation-chip styling;
  explicit "inte använda för svaret" label) so near-matches can never be mistaken for sources.
- Component tests: refusal+hits renders the labeled section with exactly the hits' fields;
  refusal+no-hits renders none; a normal answered response does NOT render near-matches.

## Task 4 — Search: real path or clearly unavailable (no mock search)

- Establish the fact: the backend exposes no search endpoint (`src/api.js` surface;
  `backend/app/main.py` routes) — verify and state it in the report.
- Decision rule from the brief: do NOT ship mock search. If the committed UI at 55c8aaa has a
  search affordance anywhere (check Home/App shell), make it clearly unavailable ("Sök kommer
  senare" state) or route it to the real ask flow (the chat pipeline) — choose routing only if
  it is a one-liner handoff to the existing `askQuestion` flow with no new data claims;
  otherwise the unavailable state. If the committed UI has NO search affordance, build nothing
  and record that Gemini's search view had no real backend and was therefore not salvaged.
- Test whichever state ships (unavailable state renders no results/counts; or routed input
  lands in the chat flow verbatim).

## Task 5 — Adversarial verification, suites, NOTES.md, evidence

1. Controller dispatches a FRESH-CONTEXT adversarial verifier subagent (no design context,
   only the invariant statement and the source): sole job — find ANY path in chat/search UI
   where unverified or fabricated data (citation, source, page, quote, excerpt, score, count)
   can reach the user. Its findings gate the phase.
2. Full suites: backend offline + isolation, `npm test`, lint, build — all green, counts
   recorded.
3. Evidence: `docs/evidence/verified-ui-restore.md` — quarantined vs restored vs salvaged vs
   deferred (the four lists), tripwire description, verifier verdict, suite counts. No real
   document content.
4. NOTES.md: one entry on the incident+lesson (external agent fabricating UI data; tripwire +
   render-path proof; salvage-on-verified-data-only rule), matching the existing entry style.
