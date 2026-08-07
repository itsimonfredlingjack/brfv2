# Implementation Plan: Enforce sovereign inference boundary

**Track ID:** `sovereign-inference-boundary`  
**Spec:** [spec.md](./spec.md)  
**Created:** 2026-08-05  
**Updated:** 2026-08-06  
**Status:** [~] Phase 0 complete; implementation phases not started  

Follow `conductor/workflow.md`: moderate TDD for invariant paths; Conventional Commits; independent review of the actual diff; **manual verification after each phase**; no unrelated working-tree staging.

---

## Overview

**Architecture consolidation, not incident response.** Fedora desktop and `BRF_MODE=pilot` are already structurally self-hosted. This track removes hosted Anthropic/Claude product paths from source/web/dev/eval, applies `model_endpoint.py` to every self-hosted construction, fails closed at the AI boundary, aligns eval/docs/Make, and keeps packaging protections.

Normative decisions: **spec.md → Locked product decisions 1–7**.

## Progress summary

| Phase | Status | Progress |
| --- | --- | --- |
| 0. Agent guidance consolidation | [x] | 100% |
| 1. Audit inventory (code + model-adjacent) | [ ] | 0% |
| 2. Red tests for the target invariant | [ ] | 0% |
| 3. Refactor provider selection to self-hosted / test-only | [ ] | 0% |
| 4. Endpoint trust for all product self-hosted construction | [ ] | 0% |
| 5. Remove hosted dependencies and configuration surface | [ ] | 0% |
| 6. Expand repository-wide security / regression tests | [ ] | 0% |
| 7. Update operations and documentation | [ ] | 0% |
| 8. Acceptance, packaging non-regression, independent review | [ ] | 0% |

---

## Phase 0: Agent guidance consolidation — COMPLETE

**Objective:** Shared, tracked operational instructions for every coding agent. Conductor remains source of truth for product principles, stack, and workflow.

**Completed:** 2026-08-06

### Tasks

- [x] **0.1** Audit root `AGENTS.md`, local `CLAUDE.md`, `kalla-native` guides, Conductor, README, track
- [x] **0.2** Rewrite tracked root `AGENTS.md` with verified brownfield knowledge + dual inference status
- [x] **0.3** Keep short `kalla-native/AGENTS.md` (Expo version docs only + pointer to root)
- [x] **0.4** Remove root `CLAUDE.md` and `kalla-native/CLAUDE.md` after migration
- [x] **0.5** Lock Decisions 1–7 and corrected framing in track spec/plan
- [x] **0.6** Manual verification: no unique instructions only in CLAUDE.md; scope limited to allowed paths

### Verification

- [x] Root `AGENTS.md` states: Fedora/pilot already structurally self-hosted; hosted Claude/Anthropic still in source/dev/eval and scheduled for this track
- [x] Conductor linked as policy source of truth
- [x] CLAUDE.md files removed
- [x] No application code / Makefile / deps changed in Phase 0

---

## Phase 1: Audit inventory (code + model-adjacent)

**Objective:** Freeze inventory of hosted paths, env keys, tests, packaging rules, and **Decision 7** model-adjacent surfaces. No product behaviour change except documentation under the track if needed.

### Tasks

- [ ] **1.1** Re-walk provider surfaces: `llm.py`, `llm_hosted.py`, `model_endpoint.py`, `desktop.apply_model_runtime`, `main.py` pilot gate, all `pick_provider` / `complete(` call sites
- [ ] **1.2** Inventory env/selection keys (including api/cli/ANTHROPIC to remove)
- [ ] **1.3** Inventory tests that assert hosted **success** (to invert)
- [ ] **1.4** Inventory packaging strengths to preserve
- [ ] **1.5** **Decision 7 audit:** OCR/extract, embeddings, rerank, transcription, analytics/telemetry, error reporting, logs/traces, backups — for each: local vs external? evidence path? in-track vs named follow-up?
- [ ] **1.6** Record Graph/Fortnox as authorised read-only intake (not model processing)
- [ ] **1.7** Manual verification checkpoint: audit table reviewed; no product code changed

### Verification

- [ ] Audit table matches live tree
- [ ] Every Decision 7 path has a disposition
- [ ] `git status` clean of accidental out-of-scope edits

### Checkpoint

```text
docs(sovereign-inference-boundary): phase 1 inventory
```

---

## Phase 2: Red tests for the target invariant

**Objective:** Encode Decisions 1–4 behaviour in tests that fail on today’s tree.

### Tasks

- [ ] **2.1** Tests: ANTHROPIC/claude PATH / api / cli → no hosted selection; fail closed without approved endpoint
- [ ] **2.2** Tests: public SaaS base URLs rejected via provider construction; loopback allowed
- [ ] **2.3** Tests: fake/scripted still work; pilot preflight expectations documented
- [ ] **2.4** List obsolete hosted-success tests for rewrite (do not delete until green path)
- [ ] **2.5** Manual verification: red for the right reason

### Verification

- [ ] New invariant tests fail on pre-change code
- [ ] Desktop packaging rules untouched

### Checkpoint

```text
test(llm): red tests for sovereign inference boundary
```

---

## Phase 3: Refactor provider selection (Decision 1)

**Objective:** Only selfhosted / fake / scripted / none.

### Tasks

- [ ] **3.1** Remove `llm_hosted.py` and plug-in discovery
- [ ] **3.2** Simplify `pick_provider()` per Decision 1
- [ ] **3.3** Strip hosted remedies from operator-facing errors
- [ ] **3.4** All LLM call sites use shared picker
- [ ] **3.5** Green selection tests
- [ ] **3.6** Manual verification with hostile env

### Checkpoint

```text
feat(llm): remove hosted providers from product selection
```

---

## Phase 4: Endpoint trust everywhere (Decision 2)

**Objective:** Apply `model_endpoint.py` to every product self-hosted construction path.

### Tasks

- [ ] **4.1** Call `require_allowed_endpoint` from `OpenAICompatProvider` or shared factory
- [ ] **4.2** Update module docs that claimed Makefile URL is outside policy
- [ ] **4.3** Constructor-level tests for commercial host rejection
- [ ] **4.4** Confirm pilot `http://127.0.0.1:8000/v1` still allowed
- [ ] **4.5** Manual verification

### Checkpoint

```text
feat(llm): enforce model endpoint policy on self-hosted client
```

---

## Phase 5: Dependencies and model identity (Decisions 1, 5)

### Tasks

- [ ] **5.1** Remove `anthropic` from product deps; refresh lock
- [ ] **5.2** Grep purge of product imports/keys
- [ ] **5.3** Remove hosted schema/persisted defaults; deployment owns `BRF_LLM_MODEL`; migrate tenants without fabricating provenance
- [ ] **5.4** Align `forbidden_providers.json` comments (keep structural rules; Decision 6: no whole-repo word ban)
- [ ] **5.5** Plan desktop runtime rebuild if delivery hash changes
- [ ] **5.6** Manual verification: app imports without anthropic

### Checkpoint

```text
chore(deps): drop anthropic from product runtime
```

---

## Phase 6: Fail-closed AI boundary + repository-wide tests (Decisions 3, 6)

### Tasks

- [ ] **6.1** AI routes → clear unavailable (prefer 503); health/readiness shows inference unavailable; backend may start for non-AI
- [ ] **6.2** Pilot/demo preflight fails without generation endpoint
- [ ] **6.3** Rewrite hosted-success tests → absence / non-selection / fail-closed
- [ ] **6.4** Source-tree forbidden scan targeting Decision 6 surfaces (not word ban)
- [ ] **6.5** Desktop artifact tests still meaningful
- [ ] **6.6** Grounding/refusal regression pass
- [ ] **6.7** Manual FR checklist

### Checkpoint

```text
test(llm): repository-wide sovereign inference regressions
```

---

## Phase 7: Operations and documentation (Decision 4)

### Tasks

- [ ] **7.1** Makefile: no silent Claude/Anthropic for eval/backend; preserve/clarify eval-selfhosted; eval-fast stays model-free
- [ ] **7.2** DEMO / runbooks / DEPLOY-SELFHOSTED-LLM
- [ ] **7.3** Supersede dual-path SPEC-PILOT/SPEC/NOTES with historical labels
- [ ] **7.4** Sync Conductor tech-stack residual if needed
- [ ] **7.5** Keep AGENTS.md accurate if runtime facts change
- [ ] **7.6** Manual verification: “how do I run generation?” → self-hosted or test only

### Checkpoint

```text
docs: align ops with sovereign inference boundary
```

---

## Phase 8: Acceptance and independent review

### Tasks

- [ ] **8.1** Targeted pytest (llm, model_endpoint, sovereign, desktop unit)
- [ ] **8.2** `make test` + `make test-isolation`
- [ ] **8.3** Desktop rebuild/verify if delivery changed; do not weaken inspect rules
- [ ] **8.4** Optional live backend-pilot with tunnel
- [ ] **8.5** Negative: ANTHROPIC set, no base URL → AI unavailable, no hosted
- [ ] **8.6** Independent review of actual diff
- [ ] **8.7** Update metadata; mark track complete in registry when done
- [ ] **8.8** P0 acceptance criteria all checked

### Checkpoint

```text
test(llm): sovereign inference boundary acceptance complete
```

---

## Final verification checklist

- [ ] Decision 1–7 satisfied
- [ ] Provider surface: selfhosted / fake / scripted / none only
- [ ] Endpoint policy on all product self-hosted construction
- [ ] Fail-closed AI boundary (non-AI may start)
- [ ] Eval not silently hosted
- [ ] Desktop packaging intact
- [ ] Grounding/refusal green
- [ ] Precise enforcement (no whole-repo word ban)
- [ ] Independent review done

---

## Decisions log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-08-05 | Track created (spec/plan) | Initial evidence-based draft |
| 2026-08-06 | **Decisions 1–7 locked** | Human product directive; see spec |
| 2026-08-06 | Framing = consolidation, not incident | Fedora/pilot already structurally self-hosted |
| 2026-08-06 | Endpoint policy = existing classes everywhere | Decision 2; no public DNS in this track |
| 2026-08-06 | Fail closed = AI 503/unavailable; non-AI may start | Decision 3 |
| 2026-08-06 | Eval = no silent hosted; eval-fast model-free; full eval needs approved self-hosted | Decision 4 |
| 2026-08-06 | Model identity from deployment config | Decision 5 |
| 2026-08-06 | Phase 0 agent guidance complete | Tracked AGENTS.md; CLAUDE.md removed |

---

## Deviations log

| Date | Task | Deviation | Reason | Resolution |
| --- | --- | --- | --- | --- |
| 2026-08-06 | Plan structure | Inserted Phase 0; renumbered inventory as Phase 1; former “lock decisions” moved into Phase 0 + locked in spec | Human required Phase 0 docs before red tests | Plan updated |

---

## Working-tree safety

Unrelated dirty/untracked paths (do not clobber):

- `DEMO.md`, website backend/tests/UI, `research/`, pre-existing `conductor/` setup

**Rules:** no `git add .`; no commits unless asked; Phase 0 only touches agent guides, CLAUDE removals, and this track.

---

**Plan created:** 2026-08-05  
**Last updated:** 2026-08-06
