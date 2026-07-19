# NOTES — lessons, one per entry

- **2026-07-16 — Isolate by giving each tenant its own object graph, not a WHERE clause.**
  The research report proposed per-tenant separation via metadata filtering in a shared vector
  store; the pilot brief demanded data-layer enforcement. A TenantRegistry that hands each brf_id
  its own Store (own filesystem dir, own chunks, own index) means there is *no code path* that can
  return another tenant's chunk — the retrieval function only ever sees one tenant's index. A
  forgotten `.filter(brf_id=...)` can leak; a separate object cannot. The adversarial suite (18
  attacks) and a fresh-context red-team both failed to cross the boundary. Why it mattered: with
  filtering, correctness depends on every query remembering the filter; with separation, it
  depends on nothing.

- **2026-07-16 — Return 404, not 403, for another tenant's resources.** A 403 confirms the
  resource exists; a 404 doesn't. Non-members of a BRF get 404 for every route, so tenant ids and
  document ids can't be probed for existence. Why it mattered: existence itself is information at
  a co-op's scale (who has documents, how many).

- **2026-07-16 — A meta-test guards the invariant the unit tests assume.** Eighteen isolation
  tests prove *today's* routes are guarded, but the real risk is a *future* route added without
  the auth dependency. A meta-test walks every `/api/brf/{brf_id}` route's dependency tree and
  fails if `tenant_store`/`require_admin` is absent. Why it mattered: it turns "we remembered to
  guard every route" from a review promise into a CI check.

- **2026-07-16 — Prove the negative with an egress audit, not an assertion.** "Zero external LLM
  calls" is unfalsifiable by inspection. Instrumenting socket.connect to hard-fail on any
  non-loopback/non-LLM connection turns the claim into a test that fails loudly if a future change
  reaches out. Why it mattered: the whole EU-data-residency promise rests on this negative, and a
  negative needs a tripwire, not a code read.

- **2026-07-16 — gemma4:e4b on an M4 is ~40–70 s/answer; parallelize evals and pin keep_alive.**
  A 4B local model is an order of magnitude slower than a hosted API per call. Eval wall-clock is
  dominated by model load/unload churn between requests. Why it mattered: budget ~20–30 min for a
  full local eval and keep the model warm, or the loop looks hung.

- **2026-07-16 — Verify recovered review findings against HEAD before re-fixing.** The prior
  adversarial review died at a session limit with 20 findings unverified; the recovered journal
  mixed already-fixed, real-but-unapplied, and refuted claims. Re-checking each against current
  code found five confirmed frontend bugs that were never applied — and avoided re-churning files
  whose fixes had already landed. Why it mattered: blind re-application would have both missed
  real bugs and reintroduced noise.

- **2026-07-16 — Equality-folding and merge-signaling are different concerns.** normalize folded
  em/en dashes to "-" for equality, and the hyphenation merge rule then glued "slutet—" + "Nästa"
  into "slutetnästa", making verbatim quotes unfindable. The fix keeps the fold for equality but
  triggers merges only on true hyphenation characters read from the raw token. Why it mattered:
  correct citations containing dashes were silently rejected as quote_not_found.

- **2026-07-16 — "Warn" must soften the refusal, not the verification.** The warn-mode
  insufficient-data path returned the LLM's prose without running citation verification at all,
  quietly bypassing requireSources. Behavior settings may choose how failures are presented —
  they must never skip the grounding checks themselves. Why it mattered: the one setting meant to
  trade strictness for helpfulness disabled the product's core guarantee.

- **2026-07-16 — Extend what a citation IS without touching what verification IS.** Fragment-facts
  (org-nr, party name, amounts split across table cells) had no contiguous sentence to quote, so
  the model stitched a non-contiguous quote that the verifier rightly rejected → refusal. Fix: a
  citation became a SET of spans, each run through the SAME `resolve_quote` (verbatim, chunk-local,
  bbox-checked), accepted only if ALL verify — rects are their union. The invariant ("no unverified
  text reaches the user") is preserved because `Resolved` still requires every span normalized-
  verbatim at a chunk-local location; a single bad span rejects the whole citation. A fresh-context
  adversary threw 10 attack classes at it and found no hole. Why it mattered: the useful questions
  (who is the counterparty, what's the org-nr) are exactly the fragment-facts, and the safe way to
  answer them is more-granular verification, never looser verification.

- **2026-07-16 — A safe mechanism can still be blocked by model capability — report that, don't
  fake it.** The multi-span contract works and resolves the real org-nr fact (proven via
  `resolve_citation` on the real retrieved chunk), but `gemma4:e4b` emitted ZERO multi-span
  citations across default/raised budget, pointed questions, and three prompt variants incl. a
  worked example — it stitches instead. So on real docs with the 4B local model, fragment-facts
  still refuse. The honest deliverable is: mechanism built + invariant proven + the finding that
  realizing it needs a stronger offline model (a design fork for Simon), NOT a fabricated "it now
  answers." Why it mattered: the definition of done said a fragment answer only counts if every
  span verifies — so "the model won't produce verifiable spans" is a real, reportable outcome.

- **2026-07-16 — When truncation survives a bigger budget, suspect a hidden channel, not the
  budget.** On real contract content, 4 of 10 board questions died as "truncated at
  max_tokens" — and still died at 3× the budget. The model (gemma4 on Ollama, thinking-capable)
  was burning the entire budget in a hidden `reasoning` field and returning empty content; the
  provider's own error message pointed at the wrong knob. Fix: request `reasoning_effort: "none"`
  (degrade-once if the server rejects it) and make the empty-content case name the reasoning
  channel. Why it mattered: every synthetic eval was green — the failure only existed on real
  documents, and the error text actively misdirected the diagnosis.

- **2026-07-16 — Real contracts fail on fragments, not hyphens.** The synthetic corpus planted
  line-break hyphenations as the hard case; the real corpus has almost none (1 in 13 pages).
  Instead, 68% of a real contract's lines are ≤2-word table/label fragments, and key facts
  (parties, org numbers, who-does-what) live in cells and letterheads where no contiguous
  quotable sentence exists — the model then stitches a "natural" quote that exists word-by-word
  but not as a span, and the verifier rightly rejects it. Why it mattered: the citation contract
  itself, not OCR or retrieval, is what real layouts stress first.

- **2026-07-16 — Measure the scariest risk before building around it: OCR turned out mundane.**
  SPEC's #1 named risk (OCR coordinate fidelity on real Swedish scans) measured fine on a real
  corpus: conf 90–93, boxes-on-ink 0.93–1.0, drift p95 ≈ 0.24% of page height, quote
  verifiability ≥0.9 — a conditional GO with a confidence gate and blank-page tolerance. Why it
  mattered: the phase's build decision now rests on numbers from the actual documents, and the
  effort saved from the feared-hard problem can go to the actually-hard one (fragment facts).

- **2026-07-16 — Split the provider default by data, not by aspiration.** The EU-residency
  requirement is about *real member data*, which only exists in pilot mode. Dev and eval run on
  synthetic, fictional BRFs — no personal data, so no residency constraint applies there. An
  earlier pass made self-hosted Gemma the dev/eval default, spending ~55 min/run on a local 4B
  model to re-prove a citation contract that the hosted provider proves in ~2 min, and coupling
  everyday dev to a GPU-ish dependency for zero compliance gain. Fix: dev/eval default to the
  cheap hosted provider; `BRF_MODE=pilot` is the hard gate that forces the self-hosted,
  EU-resident path the moment real data is in play. Why it mattered: the constraint travels with
  the data, so the default should too — otherwise you pay production's costs in dev.

- **2026-07-18 — The user-facing "max response length" is an answer budget, not an envelope
  budget.** A quote-dense multi-span citation set could push the whole JSON envelope (answer text
  plus every citation's `quote`/`quotes`) past `max_tokens` even when the answer text itself was
  short, truncating mid-JSON and refusing with a generic provider error that blamed the wrong
  setting. Fix: send the provider `maxResponseLength` plus a separate, documented headroom
  constant as the real `max_tokens`, and reword the truncation error to name the envelope budget
  instead of the user-facing setting. Why it mattered: a setting's user-facing meaning ("how long
  should the answer be") has to stay true even though the wire-level budget the provider actually
  sees must be larger.

- **2026-07-18 — OCR ingestion is an adapter into the SAME verification chain, not a second
  path.** Scanned PDFs run through `app.ocr.ocr_pdf` into the identical `PageData`/`Word`
  structures `extract.extract_pdf` produces from a text layer, so chunking, indexing, citation
  resolution, and highlighting are all unmodified and unaware the source was ever a scan — the
  only OCR-specific concessions live upstream, at ingestion (the confidence gate, blank-page
  tolerance, and the `approximate` flag on `CitationOut`). Why it mattered: real scans measured
  clean end to end (49/49 payloads verified, 18/18 corruption probes rejected) precisely because
  verification itself never had to special-case OCR — the constraint against weakening
  verification for scanned text was met by construction, not by discipline.

- **2026-07-18 — A scripted provider can prove the whole pipeline up to the model boundary.**
  With `FakeLLM` standing in for generation, every other stage — real ingestion, real retrieval,
  real multi-span verification, real highlight resolution — was proven end to end on the real
  corpus across three distinct fragment-fact classes, with both a corruption probe and a
  cross-chunk provenance probe holding. The one thing a scripted provider cannot prove is whether
  a live model will spontaneously emit the `quotes[]` payload for these facts; that gap is now
  isolated to a single question, answerable in one command by pointing a candidate model at the
  model-readiness harness. Why it mattered: "not proven" shrank from "the mechanism, the
  retrieval, and the model are all unknowns" down to "everything works except one model
  capability" — a much smaller, much more honest gap to report.

- **2026-07-18 — Pattern sweeps alone don't prove no leak; check against the extracted corpus
  text.** An org-number/date regex sweep over the branch diff missed a verbatim appendix-table row
  that a human reviewer caught by eye — regexes only catch the SHAPES of PII, not arbitrary real
  prose. Fix: extract the full text of every corpus document (PyMuPDF for the born-digital PDF,
  the app's own OCR path for the scans) to a gitignored scratch location, and cross-check every
  ≥4-consecutive-word run added on the branch against it through the app's own normalizer (the
  same equality the citation verifier itself uses) — validated with an injected positive control
  before trusting a "zero hits" result. Why it mattered: a regex sweep proves the absence of known
  shapes; a corpus cross-check proves the absence of the actual text, which is the guarantee that
  was actually needed.

- **2026-07-18 — Adjudicate disagreeing analyses by re-derivation, never by confidence.** Two
  independent refusal diagnoses (a word-index script and an adversarial page-rank pass) disagreed
  on 4 of 13 cases — and BOTH were wrong, differently: the script counted prose digits, formula
  constants, and a flow-note row as "answer values" and missed a plural table-header form; the
  narrative pass conflated page rank with chunk containment. A per-case from-scratch
  reconciliation moved the distribution from 10/1/2 to 13/0/0. Why it mattered: the fix list
  hinged on that split — averaging or trusting the more confident layer would have ordered the
  next phase around a bucket that doesn't exist.

- **2026-07-18 — Before blaming model emission, measure evidence-type discrimination.** All 13
  annual-report refusals were retrieval-bounded (true rows ranked 4–37 under hashed+BM25; table
  rows lose to prose sharing their vocabulary). When retrieval was widened as a controlled
  experiment, the model answered every case where the TRUE row arrived (never citing an adjacent
  near-miss), and its persistent refusals were correct rejections of wrong-TYPE evidence (flow vs
  balance, accrual vs expense). The one genuine multi-span-requiring case (a transposed table,
  label and value 56 word-indices apart) it refused safely rather than stitch. Why it mattered:
  the honest ceiling is retrieval ranking — the citation contract, extraction order, and the
  model's judgment all held; a "make the model answer more" fix would have attacked the one part
  that was working.

- **2026-07-19 — A better ranker can break a guarantee the worse ranker kept.** The
  cross-encoder reranker fixed exactly what was diagnosed (11/13 true table rows into top-6,
  9/13 refusals recovered live with exact highlights) — and simultaneously produced the
  system's first wrong answers: 4 verbatim-exact citations on semantically wrong rows (fee
  definitions instead of fee values, a non-label page), where the weaker retrieval had
  produced honest refusals. Verbatim verification bounds fabrication, not relevance; a
  promoted plausible-but-wrong chunk sails through it. Why it mattered: recovery count alone
  would have called this a win and shipped it; measuring answer-QUALITY regressions
  (wrong-row count 0→4) is what showed rerankEnabled must stay off pending a rerank-score
  gate. The metric that guards a zero-false-answer product is wrong answers introduced, not
  questions answered.

- **2026-07-17 — Quarantine-then-salvage-on-verified-data, and dev-gate what can't be salvaged
  yet.** An external Gemini-based agent, believing the repo was a mockup, three times tried to
  wire the chat/search UI to entirely fabricated citations and search results (invented pages,
  dates, quotes, relevance labels) via `chatAdapter.js`/`searchAdapter.js`. All three attempts
  landed only in git stashes, never committed — but proving that by eye once isn't durable. Fix:
  a tripwire test (`src/no-fabrication.test.js`) that scans product source for the fabrication's
  structural signatures (adapter module names, mock ids, and — critically — a *literal* object
  shape like `quote` co-occurring with `rects`/`page` in one literal, not just the incident's
  exact strings) plus render-path tests proving citations trace 1:1 to a mocked `api.ask()`
  response, so only the ideas that trace to real verified data got rebuilt. A later fresh-context
  adversarial verifier then found a *second*, unrelated source of the same risk class: three
  pre-existing (non-Gemini) demo tabs (Granskning, Bevakningar, a Document Canvas) still shipped
  hardcoded, pipeline-shaped data to every production user, and used a shape (a literal
  `sourceDoc`/`document_name` + `page`, no `quote` key) the original tripwire signature didn't
  cover. Rather than delete real design work or fake a backend that doesn't exist yet, the data
  moved to one allowlisted module (`src/demoData.js`) and the tabs were dev-gated: a pure helper
  (`demoTabsEnabled(isDev)`) controls every render site, and a *literal* `import.meta.env.DEV`
  check (not routed through the helper) guards the one dynamic `import()` that reaches the demo
  component — verified by grepping a real `npm run build`'s `dist/` output for the demo strings
  and finding none, not by trusting the pattern. Why it mattered: "no fabrication in committed
  code" and "no fabrication reachable in production" are different claims: the first was already
  true, the second needed its own proof, gate, and tripwire hardening.

- **2026-07-19 — Enrichment that adds non-discriminating tokens can't re-rank; prove it offline
  before spending a live model.** To recover annual-report table rows that lose to prose, we
  embedded an enriched representation (document year + section heading) per chunk, kept for
  search only (frozen text still cited — invariant proven). It recovered **0 of the refusals**:
  ranks were byte-identical to baseline on the hashed embedder, −1 on model2vec. The reason is
  structural, not a bug — the year is *constant across every chunk in a document*, and the
  section heading is *orthogonal to the query vocabulary* ("räntekostnader" never matches
  "Resultaträkning") and *shared across a section's chunks*; none of that separates the true row
  from the prose competing for the same query terms. A deterministic retrieval-recovery harness
  (true-row-into-topK via the authoritative word-index locator, no LLM) showed this in seconds
  and made the planned live 12B pass logically redundant: enrichment provably doesn't change the
  retrieved top-6, and the model is shown only the frozen excerpt, so both arms send byte-
  identical prompts → identical answers. Why it mattered: "enrich what gets embedded" sounds
  right, but retrieval only moves when the added signal *discriminates* the target from its
  competitors for *that query* — and when it doesn't, an offline rank check proves the null
  without burning a GPU hour confirming a foregone conclusion.

- **2026-07-19 — A "blocking" license is worth re-testing directly before building around it.**
  The reranker that recovers annual-report rows was blocked only by its CC-BY-NC license, so a
  whole enrichment phase was spent trying to avoid it (and failed). Testing licensable drop-ins
  through the same offline recovery harness took an afternoon and cleared the blocker:
  `cross-encoder/mmarco-mMiniLMv2` (Apache-2.0, Meta/XLM-R base, non-Chinese) recovers **14/17**
  vs the unlicensable jina's 16/17 and a no-rerank 10/17; `bge-reranker-v2-m3` (Apache-2.0, but
  Chinese-origin) recovers **17/17**. Two concrete traps surfaced: (1) the model id was a
  hardcoded literal — made it an env (`BRF_RERANK_MODEL`) so candidates swap with zero code
  churn; (2) `max_length` was hardcoded at 1024, but XLM-R-based cross-encoders cap at 512
  positions and *crash* (`tensor 520 vs 514`) above it, so the clean candidate had to run at 512
  and lost exactly the large-chunk cases where the answer row got truncated away. Why it
  mattered: the alternative-lever detour (enrichment) cost far more than the direct license
  re-test would have — when a lever is blocked *only* by license, price the licensable
  substitute first, and keep model id + context length configurable so that pricing is a
  one-command measurement, not a rebuild.
