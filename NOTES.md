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
