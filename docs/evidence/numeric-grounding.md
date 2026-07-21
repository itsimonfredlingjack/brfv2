# Evidence — numeric grounding gate (SPEC §2.10) closes a confirmed production defect (2026-07-21)

Branch `fix/numeric-grounding-gate` (off `fix/seed-reset-memberships` @ 50314d9). Self-hosted
**Gemma 4 12B** on agenntserver (Ubuntu, RTX 4070), reached via SSH tunnel
`http://127.0.0.1:8000/v1`, `BRF_MODE=pilot`.

## The confirmed defect

A real uploaded maintenance plan (`[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf`, BRF Eken
Göteborg, 36 pages) contains the verified source text `Total utgift 15 659 566 kr` on page 33.
The citation quote verified correctly — every §2.1–§2.9 check passed. Gemma 4 12B nevertheless
generated an answer containing `1 565 956 kr` (a transposed-digit fabrication), and the pipeline
returned it with `refusal=false` alongside the (accurate) citation.

**Root cause, precisely stated:**
- **Model generation error:** Gemma 4 12B paraphrased/transposed the digits when composing the
  free-text `answer` field, instead of copying the number verbatim from the excerpt it had just
  quoted correctly.
- **Backend validation gap:** `app/citations.py` verifies that a citation's `quote` string is
  verbatim-present in the source at the claimed location. It has **no visibility into the
  free-text `answer` field at all** — a quote can be 100% real while the prose built around it
  asserts something else entirely. No existing gate (§2.1–§2.9) was ever positioned to catch this,
  because none of them read `answer`.
- **Final enforced guarantee (this fix):** every material number in `answer` must equal, after
  normalization, a number found in the ACCEPTED citations' verified quote text. If not: one
  repair regeneration with the specific mismatch named, then a safe refusal
  (`numeric_grounding_failed`) — never the unsupported answer.

## Deterministic proof (required before implementing the fix)

`tests/test_answer.py::TestNumericGroundingGate` (15 tests) was written first and run against the
**unfixed** `app/answer.py` (via `git stash` of the fix, fix restored after). Result: **8 of 15
failed**, including the exact reported defect —

```
FAILED test_transposed_digits_refused_not_silently_accepted
  AssertionError: assert '15 659 566' in 'Den totala utgiften är 1 565 956 kr.'
  ...AskResponse(answer='Den totala utgiften är 1 565 956 kr.', refusal=False, refusal_reason=None,
     citations=[CitationOut(..., quote='Total utgift 15 659 566 kr', ...)], ...)
```

This is the unfixed pipeline accepting the fabricated number as a normal, non-refused answer
alongside its own correctly-verified citation — conclusive proof of the gap. After implementing
`app/numeric_grounding.py` and wiring it into `app/answer.py`, all 15 pass; the full suite
(459 tests, +40 from baseline 419) passes with zero regressions.

## Real-runtime verification (live Gemma 4 12B, real re-uploaded document)

The Eken PDF had been deleted during frontend verification in an earlier session; re-uploaded via
`POST /api/brf/gjutformen-12/documents` for this check (not committed, per instructions).

| Question | Answer | Citation quote | Match |
|---|---|---|---|
| Vad är den totala utgiften enligt underhållsplanens ekonomiska analys? | "Den totala utgiften är 15 659 566 kr." | "Total utgift 15 659 566 kr" | exact |
| Vilket år har de högsta planerade utgifterna och hur mycket är det? | Honest refusal (`insufficient_data`) — the per-year breakdown lives only in bar/pie charts (images), not extractable text | — | n/a, correctly declined |
| Hur stor är den rekommenderade årliga avsättningen? | "Den rekommenderade årliga avsättningen till fond för underhåll är 138 000 kr." | "...138 000 kr" | exact |

No fabricated number reached the client in this run — the model, given the new prompt rule 8
("copy numbers exactly, never recalculate"), reproduced every figure verbatim. **This alone does
not prove the gate works** — a live model can simply get today's questions right. Two additional,
deterministic checks were run directly against the pipeline with the REAL uploaded document's
actual chunk data (not a synthetic fixture), using a scripted `FakeLLM` to force the exact
adversarial case:

```
Found real chunk: c6ca32e64122:p33:0-70 (page 33)
Real chunk text: UNDERHÅLLSPLAN BRF Eken Göteborg ... Total utgift 15 659 566 kr Investering ...

refusal=True refusal_reason=numeric_grounding_failed
answer='Jag kunde inte bekräfta att alla siffror i svaret stämmer exakt med källorna, ...'
LLM calls made: 2
✅ real pilot data + adversarial scripted mismatch → correctly refused, bounded to one repair attempt.

refusal=False answer='Den totala utgiften är 15 659 566 kr.'
✅ real pilot data + exact correct number → accepted, no repair triggered.
```

## A genuine conservative-refusal finding (live, not hypothetical)

Asking `"Vad är underhållsplanen baserad på enligt dokumentet?"` against the live model produced a
**refusal** (`numeric_grounding_failed`) for an answer that was actually fully accurate:

> "...För BRF Eken Göteborg är underhållsplanen baserad på inskickat material från styrelsen...
> För BRF GJUTFORMEN 12 bygger planen på okulär besiktning av fastigheten genomförd i januari
> 2026 samt på leverantörernas serviceprotokoll."

Both citations verified correctly, and every number matched — **except** `12`, which came from
`"BRF GJUTFORMEN 12"`, the tenant's own registered name, not a financial/factual claim. `2026`
(the actual date claim in the same sentence) matched its citation correctly; only the
name-embedded digit tripped the gate. This is the MVP's conservative bias working exactly as
specified ("prefer false refusal over an unsupported numeric answer") at a real cost: a true,
non-fabricated answer was refused because the gate has no notion of "this number is part of a
proper name, not a claim." See the final report's limitations section — deliberately not fixed
here (would require entity-recognition machinery, out of scope for "do not build a general
mathematical reasoning engine").

## What this does not change

Tenant isolation, document provenance, quote verification, rectangle resolution, rejected-citation
handling, provider abstraction, and every existing public `AskResponse` field are untouched. The
one addition is `RefusalReason` gaining `"numeric_grounding_failed"` (additive) and `GROUNDING_CONTRACT`
gaining one new numbered rule (8) — no existing rule text changed, confirmed by every pre-existing
prompt-content test (`"ORDAGRANT" in system`, etc.) still passing unmodified.
