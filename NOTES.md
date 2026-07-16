# NOTES — lessons, one per entry

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
