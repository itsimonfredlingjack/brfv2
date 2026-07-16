# Gate 0b — adversarial review, round 2 (2026-07-16)

The prior review workflow (39 agents) died at a session usage limit with ~20 findings
unverified. Its journal survived in full: **42 finder findings + 15 completed verdicts**
(11 confirmed, 3 refuted, 1 partly-wrong) were recovered and every finding dispositioned
against current HEAD. Fixes landed in commits `3244dc3` (frontend) and `4015c82` (backend).

**Verification after fixes:** `uv run pytest -q` → **123 passed, 1 skipped** (11 new repro
tests); retrieval eval recall@6 = **1.000 (46/46)** on both embedders; `npm run build` clean.

## Disposition of all 42 findings

| # | Finding (severity) | Verdict | Action |
|---|---|---|---|
| 1 | PdfViewer loading-task/PDF leak on early cleanup (high) | CONFIRMED | **Fixed** `3244dc3` |
| 2 | Render task not cancelled before destroy → error banner (med) | REFUTED (pdf.js cancels internally with the filtered exception) | none |
| 3 | initialPage in load-effect deps re-downloads PDF (med) | REFUTED (unreachable: modal unmounts) | none |
| 4 | Re-click same citation doesn't navigate (med) | REFUTED (same modal reason) | none |
| 5 | Chat input cleared while busy — silent loss (med) | CONFIRMED | **Fixed** `3244dc3` |
| 6 | Default aiModel 'gpt-4o' invalid + backend accepts any string (med) | CONFIRMED | **Fixed** `3244dc3` + pattern validation `4015c82` |
| 7 | Stale settings-save timer wipes 'saving' state (low) | CONFIRMED | **Fixed** `3244dc3` |
| 8 | Stale overlays over errored canvas (low) | CONFIRMED | already fixed prior session (overlays cleared at render start) |
| 9 | Cancelled render's finally hides spinner (low) | CONFIRMED | already fixed prior session (task-identity guard) |
| 10 | Dead file-input reset in finally (low) | CONFIRMED | **Fixed** `3244dc3` (reset in onChange) |
| 11 | seed.py double-seed duplicates corpus (high) | CONFIRMED | fixed prior session (early exit) |
| 12 | HybridIndex.build non-atomic → IndexError (high) | CONFIRMED | fixed prior session (fresh-object swap + lock) |
| 13 | Store._rebuild in-place clear → partial chunk map (high) | CONFIRMED | fixed prior session |
| 14 | /api/reset request-time import depends on cwd (high) | VERIFIED live: works under documented run config, but brittle | **Hardened** `4015c82` (sys.path pin); dev-only gating lands with pilot mode |
| 15 | CLI provider drops max_tokens (med) | CONFIRMED | fixed prior session (soft cap instruction) |
| 16 | CLI JSON envelope is_error/subtype unchecked (med) | CONFIRMED | **Fixed** `4015c82` |
| 17 | Anthropic stop_reason max_tokens unchecked (med) | CONFIRMED | fixed prior session |
| 18 | Warn-mode insufficient_data bypasses verification + requireSources (med) | CONFIRMED | **Fixed** `4015c82` + 2 tests |
| 19 | Tech failures labeled insufficient_data + leak exception text (med) | CONFIRMED | **Fixed** `4015c82` (`provider_error`, detail log-only) + test |
| 20 | Low-relevance gate reads hits[0] not max confidence (med) | CONFIRMED | **Fixed** `4015c82` |
| 21 | Raw chunk ids outside retrieved set accepted (low) | CONFIRMED | **Fixed** `4015c82` (retrieved-set restriction) + test |
| 22 | Boot-drop of broken docs never persisted (low) | CONFIRMED | **Fixed** `4015c82` |
| 23 | add_document leaves orphans on rebuild failure (low) | CONFIRMED | **Fixed** `4015c82` (rollback) |
| 24 | update_settings persists before rebuild (low) | CONFIRMED | **Fixed** `4015c82` (revert on failure) |
| 25 | eval --limit 0 treated as no-limit (low) | CONFIRMED | **Fixed** `4015c82` |
| 26 | pick_provider eager Anthropic → /api/health 500 (low) | CONFIRMED | **Fixed** `4015c82` |
| 27 | wipe() rebuilds once per document (low) | CONFIRMED | **Fixed** `4015c82` (single rebuild) |
| 28 | Answer *prose* never verified against quotes — prompt-injectable via malicious PDF (high) | CONFIRMED as design gap | **Mitigated** `4015c82` (contract rule 7: excerpts are data, never instructions) + **ticketed**: answer-faithfulness check is a later-phase item; UI renders verified quotes distinctly. Within-tenant threat only after this phase's isolation. |
| 29 | No upload size / resource caps (med) | CONFIRMED | 50 MB cap fixed prior session; **400-page cap added** `4015c82` |
| 30 | CLI stderr leaked into user-visible error (low) | CONFIRMED | **Fixed** `4015c82` (log-only) |
| 31 | Model string as CLI arg (injection surface) + unconfirmed reset (low) | CONFIRMED | **Fixed** `4015c82` (aiModel pattern, no leading dash); reset gating in pilot mode |
| 32 | doc_id path built before membership check (low, "defended today") | acknowledged | superseded by this phase's tenancy layer; isolation suite adds path-traversal attacks |
| 33 | canonical_stream no chain-merge (3+ fragments) (med) | CONFIRMED by repro | **Fixed** `4015c82` + tests |
| 34 | Em/en dash folded to '-' triggers spurious merge (med) | CONFIRMED by repro | **Fixed** `4015c82` (merge-signal set separate from equality fold) + tests |
| 35 | Partial quotes starting/ending inside a merge unfindable (med) | CONFIRMED by repro | **Fixed** `4015c82` (unmerged fallback matcher) + tests |
| 36 | _pick_span accepts 1-word-graze overlap (§2.6) (low) | CONFIRMED | **Fixed** `4015c82` (≥50 % of span must lie in chunk) + test |
| 37 | chunkOverlap ≥ chunkSize allowed (low) | CONFIRMED | fixed prior session (validator) |
| 38 | Word hyphenated across a *page* break unfindable merged (low) | TRUE by construction | accepted limitation per SPEC §2.4 policy; documented in drift doc |
| 39 | _expand_query O(query×vocab) per search (low) | TRUE, bounded | ticketed perf note — per-tenant vocab at pilot scale is a few thousand terms; revisit at real-corpus scale |
| 40 | _minmax degenerate-pool edge (low) | uncertain, benign | noted, no action |
| 41 | Gate top-confidence duplicate of #20 (low) | CONFIRMED | same fix as #20 |
| 42 | _found_elsewhere rescans all pages incl. cited (low) | TRUE, rejected-quotes-only path | noted, no action at pilot scale |

## Open tickets carried forward

1. **Answer-faithfulness verification** (#28) — verify the prose against the verified quotes
   (NLI/entailment or a judge pass). Later phase; prompt hardening + verified-quote UI today.
2. **_expand_query scaling** (#39) — precompute a substring index if per-tenant vocab grows
   beyond ~50k terms.

A fresh adversarial workflow runs over the **entire pilot-phase diff** (including these fixes)
before the phase report — findings there will be dispositioned the same way.
