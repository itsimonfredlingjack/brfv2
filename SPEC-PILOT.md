# SPEC-PILOT — Phase 2: pilot-ready for one real BRF

> Source of truth: Simon's pilot brief (2026-07-16). This file records the phase contract so
> tests and future sessions can reference it. The vertical-slice SPEC.md still governs the
> grounding/citation/highlight behavior, which must stay green throughout.

## Goals (in order, each gated by its own proof)

1. **Provider-agnostic generation; self-hosted Gemma 4 as the pilot/production path.**
   A clean provider interface behind one endpoint swap. Dev and eval default to the standard
   hosted provider (synthetic data → no data-residency constraint). For a real-data pilot,
   `BRF_MODE=pilot` forces self-hosted Gemma 4 (open weights, vLLM or Ollama) so no document
   text reaches an external API. Proof: full eval green on the hosted default + a self-hosted
   run with zero external LLM calls. The EU GPU host is Simon's input; the endpoint is
   configurable (`BRF_LLM_BASE_URL`, `BRF_LLM_MODEL`, optional `BRF_LLM_API_KEY`).
   *(Refined by Simon's 2026-07-16 configuration decision: the earlier "self-hosted as the
   only path" framing wrongly applied to dev; dev/eval now default to the hosted provider.)*
2. **Hard multi-tenant isolation keyed by `brf_id`.** Every layer scoped to a tenant and
   enforced at the data layer — not filtered in a query. Honest ChromaDB/Qdrant assessment;
   simplest approach that makes isolation provable.
3. **Minimal real auth.** Board-member login, user→BRF membership, member/admin distinction.
   No SSO, no org hierarchies, no permission matrices.
4. **Data lifecycle.** Document/BRF delete → hard-delete of all chunks, embeddings, boxes,
   files, settings — proven by test. Configurable retention window. Full-disk encryption is a
   deploy-step note, not built.

## The hard part

An **adversarial isolation suite** that actively tries to make a member of BRF A retrieve,
cite, see, or delete BRF B's content — API, crafted queries, shared caches, ID collisions —
plus a fresh-context red-team verifier agent. Suite green = phase works.

## Definition of done

Two distinct BRFs seeded with different data; A can never touch B (adversarial suite green);
generation runs through the provider interface (dev/eval on the hosted default; pilot mode
forces self-hosted Gemma 4 with zero external LLM calls — both proven); board-member login
enforced; BRF deletion hard-deletes all data (proven); original eval green per-tenant.
Evidence in `docs/evidence/`.

## Out of scope (later phase, Simon's gate)

GraphRAG / corpus-wide questions, formal DPIA, audit dashboards, the unwired
Granskning/Bevakningar tabs, scaling beyond a handful of tenants.

## Post-BP6 narrowing: session transport (2026-07-29)

Recorded here because it changes behavior this contract's §3 covers. It is a
**narrowing of an existing guarantee, not new scope**, and it reopens no gate:
BP1–BP6 stand as decided, and the BP6 artifacts in `docs/` are left exactly as
they were approved.

Session credentials now travel **only** in the httpOnly `brf_session` cookie:

- `POST /api/auth/login` no longer returns the session token in its JSON body.
  The response is `{user, memberships}`. Echoing the token put a long-lived
  credential where page script — or any logging proxy in between — could read
  it, which is what httpOnly exists to prevent.
- `Authorization: Bearer` is no longer an authentication path. Login issues no
  token, so accepting one would only widen the auth surface for a credential
  no legitimate client can obtain.

Nothing outside the test fixtures consumed the token. Those now take the
session from `Set-Cookie` and pass it explicitly per request, so the
adversarial isolation suite keeps its defining property — a request without
the header is genuinely unauthenticated — with no assertion relaxed.

Proven by:

- `tests/test_api.py::TestAuthFlow::test_login_body_carries_no_session_token`
  — the body is exactly `{user, memberships}` and the cookie is httpOnly;
- `tests/test_isolation.py::TestForgedCredentials::test_bearer_header_is_not_an_authentication_path`
  — a **real, currently-valid** token is refused as a Bearer header while the
  same token in the cookie still works, so it is the transport being rejected
  and not an invalid token;
- `tests/test_isolation.py::TestForgedCredentials::test_forged_session_cookie_rejected`.

Commit `991349d`; full backend suite green at 588 passed, 3 skipped.

## Departures from deep-research-report.md (deliberate, per the brief)

- Generation: **Gemma 4** (brief) instead of Mistral Large 2 / Silo Viking (report).
- Tenancy: **data-layer separation** (brief) instead of metadata-filter namespacing (report).
