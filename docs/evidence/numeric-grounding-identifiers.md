# Evidence — numeric grounding identifier exemption (SPEC §2.11) closes a confirmed false refusal (2026-07-21)

Branch `fix/numeric-grounding-identifiers` (off `fix/numeric-grounding-gate` @ f6d7b97). Self-hosted
**Gemma 4 12B** on agenntserver (Ubuntu, RTX 4070), reached via SSH tunnel `http://127.0.0.1:8000/v1`,
`BRF_MODE=pilot`.

## The confirmed defect

SPEC §2.10's numeric grounding gate (`app/numeric_grounding.py`) checks every number-shaped
token in the answer against the accepted citations' verified quotes, with no notion of what a
number *means*. The tenant `Brf Gjutformen 12` — a real registered name — contains a digit that
is an **identifier**, not a factual claim. Live testing against the real pilot stack reproduced a
genuine false refusal: asking `"Vad är underhållsplanen baserad på enligt dokumentet?"` produced
an accurate answer mentioning `"BRF GJUTFORMEN 12"`, refused with `numeric_grounding_failed`
solely because `12` had no citation support — even though `2026` (the actual factual claim in the
same sentence) matched its citation correctly. See `docs/evidence/numeric-grounding.md`'s own
"genuine conservative-refusal finding" section, which first surfaced this.

**Root cause, precisely stated:**
- **Backend validation gap:** `check_numeric_grounding` treated every number-shaped token as a
  factual claim requiring citation support, with no way to distinguish an identifier embedded in
  a verified entity name from an assertion about a quantity.
- **Final enforced guarantee (this fix):** a number is exempt from the support requirement only
  when it falls inside a COMPLETE, exact, word-boundary-anchored span of a server-trusted entity
  name — the tenant's own registered name (from `auth.get_tenant()`, never client-supplied) or the
  exact `document_name` of a citation the response actually verified. Everything else — a bare
  digit, a partial name, a wrong identifier, question text, a rejected citation's content — still
  requires citation support exactly as before.

## Deterministic proof (required before implementing the fix)

The full new test suite (29 unit tests in `tests/test_numeric_grounding.py`, 16 pipeline tests in
`tests/test_answer.py::TestNumericIdentifierExemption`/`TestAcceptedCitationTitleAsTrustedSpan`, 2
API tests in `tests/test_api.py::TestAskTenantNamePropagation`) was written first and run against
the **unfixed** `app/answer.py` / `app/main.py` / `app/numeric_grounding.py` (via `git stash` of
the fix files, restored after). Result: **15 failed, 1 collection error** — 13 `TypeError: ask()
got an unexpected keyword argument 'trusted_names'` (the parameter didn't exist yet), 1
`ImportError` for `mask_trusted_spans` (module didn't exist yet), and — most tellingly — 2 genuine
semantic failures showing the defect mechanism directly in the logs:

```
WARNING brf.answer:answer.py:341 Numerisk grundningskontroll misslyckades, försöker reparera: 12
...
FAILED tests/test_api.py::TestAskTenantNamePropagation::test_tenant_name_digit_does_not_trigger_refusal_via_the_real_route
  AssertionError: {'answer': 'Tekniskt fel vid svarsgenerering...', 'refusal': True, 'refusal_reason': 'provider_error', ...}
```

(`provider_error` here because the scripted `FakeLLM` had only one response queued; the unfixed
gate consumed it on a doomed repair attempt for `"12"` and had nothing left for the second call —
itself a symptom of the false refusal.) After implementing the fix, all tests pass; the full suite
(506 tests, +47 from baseline 459) passes with zero regressions.

## Real-runtime verification (live Gemma 4 12B, real tenant data)

The exact question that first surfaced the defect, re-asked against the live model on this branch:

| Question | Answer | Refusal (before fix) | Refusal (after fix) |
|---|---|---|---|
| Vad är underhållsplanen baserad på enligt dokumentet? | "...För BRF GJUTFORMEN 12 bygger planen på okulär besiktning av fastigheten genomförd i januari 2026 samt på leverantörernas serviceprotokoll." | `numeric_grounding_failed` (12 unsupported) | **none** — both `12` (tenant identifier, exempted) and `2026` (genuine claim, quote-supported) resolve correctly |
| Hur stor är den rekommenderade årliga avsättningen enligt avsättningsanalysen? | "Den rekommenderade årliga avsättningen till fond för underhåll är 138 000 kr." | n/a (no identifier involved) | **none** — exact match, unaffected by this fix |

Two additional deterministic checks were run directly against the pipeline with the **real
`gjutformen-12` tenant's actual Store data** (not synthetic fixtures), using a scripted `FakeLLM`
to force each case and `auth.get_tenant("gjutformen-12")` for the real trusted name
(`"Brf Gjutformen 12"`):

```
[1] tenant name present (12 exempt) + a SEPARATE wrong reserve figure (183 000 vs real 138 000 kr):
refusal: True numeric_grounding_failed
LLM calls: 2
✅ the identifier exemption does not blanket-exempt unrelated wrong numbers in the same answer.

[2] tenant name present (12 exempt) + the correct reserve figure:
refusal: False
answer: 'BRF GJUTFORMEN 12 rekommenderas en årlig avsättning på 138 000 kr.'
LLM calls: 1
✅ real pilot data + tenant identifier + genuine claim → accepted, no repair triggered.

[3] deliberate scripted mismatch, no tenant name mentioned at all:
refusal: True numeric_grounding_failed
LLM calls: 2
✅ ordinary numeric mismatches (SPEC §2.10) remain exactly as strict as before this fix.
```

## What this does not change

Citation verification, tenant isolation, the one-repair-attempt bound, the conservative
refuse-over-guess policy, and every existing public `AskResponse` field are untouched. The
`ask()` signature gains one keyword-only argument, `trusted_names: Iterable[str] = ()`, defaulting
to empty — every pre-existing call site (`ask(store, question, provider=fake)`) is byte-for-byte
unaffected. `app/numeric_grounding.check_numeric_grounding` gains one keyword-only argument,
`trusted_names`, with the same empty default — `extract_numbers`'s public signature is unchanged.

## Remaining limitations

Masking requires an **exact** normalized span (case/space-variant-insensitive, but not
whitespace-count-insensitive) — a tenant name mentioned with irregular spacing or a stylistic
variant not matching the registered string verbatim will not be exempted (falls back to the
existing conservative refusal, never a false accept). Document-title exemption only covers a
citation's *own* `document_name` for the response that verified it — a title mentioned without
its citation being present in that specific response is not exempted. Neither period-grouped
thousands nor the word "procent" handle every possible European numeral-formatting convention
(e.g. a period used ambiguously as a single thousands group, as in "15.659", is deliberately left
as a decimal rather than guessed — see `app/numeric_grounding.py`'s `_NUMBER_RE` comment).
