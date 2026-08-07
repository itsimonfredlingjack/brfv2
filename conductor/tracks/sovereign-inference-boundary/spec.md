# Specification: Enforce sovereign inference boundary

**Track ID:** `sovereign-inference-boundary`  
**Type:** Feature (security / product invariant · architecture consolidation)  
**Priority:** Critical  
**Created:** 2026-08-05  
**Updated:** 2026-08-06  
**Status:** Decisions locked; Phase 0 (agent guidance) complete; product implementation not started  
**Branch context:** `feat/produktbas`  

---

## Framing (correct)

This track is **repository-wide architecture consolidation and hardening**, not incident response.

### What is already structurally self-hosted

Verified protections (do **not** describe this track as repairing an active data leak in Fedora or pilot):

| Surface | Protection |
| --- | --- |
| **`BRF_MODE=pilot`** | Startup requires `provider.name == "selfhosted"` (`backend/app/main.py`) |
| **Desktop runtime** | `apply_model_runtime` pins `BRF_LLM=selfhosted` and re-checks endpoints |
| **Fedora RPM payload** | Excludes `llm_hosted.py` and the Anthropic package; prune/build-runtime |
| **Artifact tests** | `ops/forbidden_providers.json` + `inspect_payload.py` + `test_desktop_artifact.py` |
| **Installed product endpoint policy** | `model_endpoint.py` default-deny (loopback / private-network) |

### What is inconsistent

| Surface | Current state (verified) |
| --- | --- |
| **Source / web / dev / eval** | Hosted Anthropic API and Claude CLI still implemented and deliberately supported |
| **Makefile & tests** | Still maintain hosted paths as defaults / success cases |
| **`OpenAICompatProvider`** | Does not apply `model_endpoint.py` on every non-desktop construction path |
| **Product identity** | Conductor and product claim: Träff never uses external model providers for association-content processing |

The track makes **source, runtime policy, documentation, agent guidance, and shipped artefacts express the same invariant**. It remains critical for that consistency—not because Fedora/pilot were observed leaking.

---

## Summary

Align the whole repository with the product invariant: **selfhosted** is the only real inference provider; **fake** / **scripted** remain for tests and deterministic acceptance; hosted Anthropic/Claude paths, plug-in discovery, and commercial defaults are removed from product code; existing `model_endpoint.py` policy applies to every self-hosted construction path; AI fails closed without an approved endpoint; evaluation no longer silently uses hosted providers.

---

## Locked product decisions

These are normative for implementation. Open questions that conflict with them are closed.

### Decision 1 — No hosted model providers in Träff product code

Intended end state:

- **selfhosted** is the only real inference provider
- **fake** and **scripted** remain for tests and deterministic acceptance
- Anthropic API support is **removed**
- Claude CLI provider support is **removed**
- **`llm_hosted.py` is removed**
- Hosted-provider plug-in discovery is **removed**
- **`BRF_LLM=api` and `BRF_LLM=cli` are removed**
- **`ANTHROPIC_API_KEY` is removed** from product configuration
- Automatic hosted fallback is **removed**
- Anthropic SDK is **removed** from product dependencies
- No provider-specific commercial model remains as a product default

External coding and research agents may still be used by developers **outside** the Träff runtime. They are not product providers and must not receive association content through Träff.

### Decision 2 — Reuse the existing endpoint policy everywhere

- Starting point: `backend/app/model_endpoint.py`
- Apply it to **every** construction path for the self-hosted provider, including web/dev/eval
- Retain existing allowed deployment classes for this track:
  - **loopback** (including SSH-forwarded pilot endpoint)
  - **private-network** IP addresses over **HTTPS**
- Do **not** add arbitrary public DNS endpoints or a general unsafe bypass in this track
- A future Träff-controlled public Swedish/EU endpoint needs a **separate ADR** (trust registration, TLS identity, machine authentication)—not solved here
- An OpenAI-compatible protocol is **not** evidence that infrastructure is controlled by Träff

### Decision 3 — Fail closed at the AI boundary

When no approved self-hosted endpoint is configured:

- No alternative or hosted model may be selected
- The ordinary backend **may still start** where non-AI functions can operate
- AI-dependent routes must return a clear unavailable result, preferably **503** through the existing error architecture
- Readiness/health must expose that **inference is unavailable**
- Pilot/demo commands that require generation must **fail during preflight** before serving traffic

### Decision 4 — Evaluation behaviour

- Unit tests and deterministic acceptance use **fake** or **scripted**
- **`make eval-fast`** remains retrieval-only and model-free
- Full model-quality evaluation requires an **explicitly configured, policy-approved self-hosted endpoint**
- **`make eval` and `make eval-b` must no longer silently use Claude CLI or Anthropic**
- Preserve or clarify **`eval-selfhosted`** targets rather than introducing unnecessary duplicate commands

### Decision 5 — Deployment controls model identity

- Remove **`claude-opus-4-8`** and other hosted-provider names as persisted or schema defaults
- Real model identity comes from trusted deployment configuration such as **`BRF_LLM_MODEL`**
- Current pilot may use **`gemma4:e12b`**, but architecture must remain **model-replaceable**
- Migrate existing tenant settings without fabricating model provenance (prefer clear default + ignore legacy hosted ids for selection)

### Decision 6 — Precise enforcement

Do **not** ban words such as Anthropic, Claude, or OpenAI across the whole repository.

They may legitimately appear in:

- competitive research
- historical migration notes
- removal documentation
- tests proving forbidden runtime paths are absent

Enforcement targets:

- runtime dependencies
- importable product modules
- provider registration
- environment and configuration keys
- product network destinations
- packaged artefacts
- operational commands capable of processing association content

### Decision 7 — Audit model-adjacent processing

The invariant also covers external processing of association content through:

- OCR and document extraction
- embeddings
- reranking
- transcription
- analytics and telemetry
- error reporting
- logs and traces
- backups

**Phase 1** must inventory these paths. Do not automatically expand implementation into unrelated rewrites. If the audit finds a real external processing path, document evidence and decide whether it belongs in this track or a **named follow-up**.

Microsoft Graph and Fortnox are **authorised read-only source integrations**, not model-processing providers.

**Canonical wording:**

> Träff does not disclose association content to external model, OCR, embedding, reranking, transcription, analytics, telemetry or error-reporting services. Authorised read-only intake from the association’s existing systems of record is permitted.

---

## Context

Conductor product artifacts (`conductor/product.md`, `product-guidelines.md`, `tech-stack.md`) state the sovereign inference boundary. Agent guidance is consolidated in tracked `AGENTS.md` (Phase 0). Detailed policy lives in Conductor; this track implements runtime/docs alignment.

---

## Problem (architecture inconsistency)

Desktop packaging and pilot mode already enforce self-hosted generation. The **source tree** still encodes a dual path for web/dev/eval (hosted providers as deliberate defaults). Product identity and repository behaviour diverge until this track lands.

### Current-state evidence (verified)

#### `backend/app/llm.py`

- Self-hosted + test providers ship always; third-party providers in optional `app.llm_hosted`, discovered at selection time.
- Order: scripted → fake → selfhosted (`BRF_LLM=selfhosted` or auto + `BRF_LLM_BASE_URL`) → hosted plug-ins → none.
- `OpenAICompatProvider` does **not** call `require_allowed_endpoint`.

#### `backend/app/llm_hosted.py`

- Anthropic API + Claude CLI; docstring: dev/eval default, fully supported for web product.

#### Dependencies and ops

- `anthropic` in `backend/pyproject.toml`
- Makefile: hosted as default for dev/eval comments; unpinned `make backend` / `make eval`
- Pilot/desktop: selfhosted pins and payload exclusion as above

#### Endpoint trust

- `model_endpoint.py` default-deny; historically documented as outside Makefile-driven `BRF_LLM_BASE_URL` (Decision 2 closes this for product construction paths)

#### Tests

- `test_llm.py` asserts hosted registration/selection success
- Offline suite uses `BRF_LLM=fake` (preserve)

#### Residuals

- `Settings.aiModel` default `claude-opus-4-8`
- Historical dual-path docs (`SPEC-PILOT.md`, etc.)

---

## Invariant definition

**I-SIB-1.** No external model inference (or equivalent external AI processing of association content) for product paths—see Decision 7 wording.

**I-SIB-2.** Product generation runs only on Träff-controlled infrastructure; protocol compatibility ≠ trust (Decision 2).

**I-SIB-3.** Fail closed at the AI boundary per Decision 3 (non-AI may start; AI returns unavailable).

**I-SIB-4.** fake/scripted only for tests/deterministic acceptance.

**I-SIB-5.** Developer tools outside product runtime remain allowed; not product providers.

**I-SIB-6.** Fedora packaging protections must not be weakened.

---

## Threat and failure cases

| ID | Failure mode |
| --- | --- |
| T1 | Env key + auto selects Anthropic on web/dev backend |
| T2 | `claude` on PATH + auto |
| T3 | `BRF_LLM=api` / `cli` |
| T4 | `BRF_LLM_BASE_URL` to public SaaS OpenAI-compatible host |
| T5 | Hosted SDK reintroduced in product deps |
| T6 | Docs/Make teach hosted defaults |
| T7 | Tests require hosted selection as success |
| T8 | Desktop packaging weakened |
| T9 | Telemetry/error reporting uploads association content |
| T10 | Embeddings/rerank/OCR remote external processing |

T1–T8 are in-scope for implementation phases. T9–T10: inventory in Phase 1; scope decision before rewrite.

---

## Scope

### In scope

- Remove hosted providers, plug-in discovery, related env keys and product deps (Decision 1)
- Apply `model_endpoint.py` to every self-hosted construction path (Decision 2)
- Fail-closed AI UX/health/preflight (Decision 3)
- Eval/Make/docs alignment (Decision 4, Phase 7)
- Model identity / schema defaults (Decision 5)
- Precise enforcement tests (Decision 6)
- Model-adjacent audit inventory (Decision 7 / Phase 1)
- Phase 0 agent guidance (complete)
- Preserve grounding, citations, refusal, desktop packaging strength

### Out of scope

- Speculative public-DNS Träff endpoint design (separate ADR)
- Incident narrative / breach remediation framing
- Unrelated OCR/embeddings rewrites without audit evidence
- Grounding contract redesign
- Changing Graph/Fortnox read-only semantics
- Committing unrelated dirty working-tree files

---

## Functional requirements

### FR-1: Provider surface (Decision 1)

Only: selfhosted | fake | scripted | none (fail closed).

**Acceptance:** no anthropic-api/claude-cli registration; no api/cli keys; no ANTHROPIC influence; no claude PATH influence; `llm_hosted.py` gone; no plug-in discovery.

### FR-2: Fail closed (Decision 3)

**Acceptance:** no hosted fallback; AI routes clear unavailable (prefer 503); health exposes inference unavailable; non-AI can start; pilot/demo preflight fails without generation endpoint.

### FR-3: Endpoint trust (Decision 2)

**Acceptance:** every product `OpenAICompatProvider` (or factory) construction validates via `model_endpoint`; loopback + private HTTPS retained; no public DNS bypass; desktop tests still pass.

### FR-4: Dependencies (Decision 1 + 6)

**Acceptance:** no product `anthropic` dependency; repository tests detect reintroduction of forbidden runtime modules/packages/keys; desktop inspect intact.

### FR-5: Model identity (Decision 5)

**Acceptance:** no hosted commercial default in schema/persisted defaults; identity from deployment config; model-replaceable.

### FR-6: Preserve contracts

**Acceptance:** grounding/refusal/citations unchanged in intent; offline tests deterministic; desktop pins remain; all LLM call sites use shared picker.

### FR-7: Evaluation (Decision 4)

**Acceptance:** eval-fast model-free; full eval needs approved self-hosted; eval/eval-b not silent hosted; eval-selfhosted clarified/preserved.

---

## Operational requirements

- Align Makefile, DEMO/runbooks, DEPLOY-SELFHOSTED-LLM, supersede dual-path SPEC-PILOT claims with historical labels
- Agent guidance: tracked root `AGENTS.md` (Phase 0 done)
- Desktop rebuild if delivery hash changes when deps drop

---

## Acceptance criteria (track complete)

### P0

- [ ] Decisions 1–7 implemented as specified
- [ ] No selectable hosted product providers in source runtime
- [ ] Endpoint policy on all product self-hosted construction
- [ ] Fail-closed AI boundary (Decision 3)
- [ ] Hosted SDK not required by product runtime
- [ ] Repository-wide regressions (Decision 6 scope)
- [ ] Desktop packaging protections intact
- [ ] Eval/docs/Make no silent hosted defaults
- [ ] Offline tests green; grounding/refusal not regressed
- [ ] Independent review of actual diff
- [x] Phase 0 agent guidance consolidated into tracked AGENTS.md

### P1

- [ ] Source-level forbidden-provider scan without full RPM
- [ ] Tenant/schema model default de-hosted (Decision 5)
- [ ] Phase 1 model-adjacent audit written with scope decisions

### P2

- [ ] Optional SE/EU endpoint attestation metadata (not required for this track’s loopback/private policy)
- [ ] Egress audit extensions if gaps found

---

## Risks

| Risk | Mitigation |
| --- | --- |
| SaaS OpenAI-compatible URL labeled selfhosted | Decision 2 on every construction path |
| Public DNS needed later for Träff-controlled host | Separate ADR; not this track |
| Delivery hash / evidence invalidation | Explicit desktop rebuild tasks |
| Scope creep into OCR/embeddings | Phase 1 inventory + named follow-ups |
| Dirty working tree | Surgical edits; no `git add .` |

---

## Closed former open questions

| Former question | Resolution |
| --- | --- |
| Endpoint policy for non-desktop? | Same `model_endpoint.py` classes (Decision 2) |
| Claude CLI for synthetic eval? | Removed from product paths; not a product provider (Decision 1, 4) |
| make eval without model? | No silent hosted; require approved self-hosted for full model eval; eval-fast stays model-free (Decision 4) |
| aiModel default? | Remove hosted commercial defaults; deployment owns identity (Decision 5) |
| How far model-adjacent? | Inventory Phase 1; no automatic expansion (Decision 7) |

---

## References

- `conductor/product.md`, `product-guidelines.md`, `tech-stack.md`, `workflow.md`
- Root `AGENTS.md` (Phase 0)
- `backend/app/llm.py`, `llm_hosted.py`, `model_endpoint.py`, `desktop.py`, `main.py`, `schemas.py`
- `ops/forbidden_providers.json`, packaging scripts, `Makefile`
- `docs/adr/0002-model-endpoint-boundary.md`

---

**Approved By:** product decisions locked 2026-08-06 (human directive)  
**Approval Date:** 2026-08-06
