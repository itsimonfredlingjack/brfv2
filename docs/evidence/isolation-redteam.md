# Evidence — fresh-context isolation red-team (2026-07-16)

A dedicated agent, with no knowledge of the isolation test suite, was given BRF A credentials and
one job: make BRF A retrieve, cite, see, or delete BRF B's content in a live two-tenant instance
(`http://localhost:8791`, real HTTP, fake LLM, two disjoint seeded corpora). It attacked both
black-box (crafted requests) and white-box (reading the backend source for gaps).

## Result: BLOCKED across the board — zero bytes crossed the boundary

45+ requests across every vector in the brief plus several the agent invented. No cross-tenant
leak, no cross-tenant deletion. B's unique markers (org.nr `769633-8821`, loan numbers
`220445`/`220446`, bank `Skärgårdsbanken`, vendor `Rent & Grönt i Väst AB`) never appeared in any
A-origin response. All four of B's documents survived every delete attempt (verified from disk
afterward).

| # | Attack | Verdict |
|---|---|---|
| 1 | A tokens on B's direct routes (list/read/settings/ask/delete, 20 reqs) | BLOCKED — 404 "Okänd förening." |
| 2 | B's real doc_ids under A's tenant path (read + delete, 16 reqs) | BLOCKED — 404 "Okänt dokument." |
| 3 | RAG bleed: ask A using B's secrets + prompt-injection to dump B | BLOCKED — retrieval[] only A chunks, no B string anywhere |
| 4 | Path trickery (`../`, `..%2f`, `..%252f`, case, trailing dot/space/null/newline, unicode, `;`-param) | BLOCKED — 404 |
| 5 | Forged/replayed/absent tokens and cookies, wrong scheme | BLOCKED — 401; valid B session → 404 on A |
| 6 | Method confusion + header spoof (`X-Forwarded-User: stina`, `X-Original-URL`, `X-Brf-Id`) | BLOCKED — headers ignored, served only A's own data |
| 7 | 404-vs-403 existence oracle | BLOCKED — byte-identical 404 for real-B vs bogus tenant |
| 8 | Member (Bo) mutating even his OWN tenant | BLOCKED — 403 "Kräver administratörsroll." |

### Root cause of the strength (agent's white-box analysis, confirmed)

`tenant_store()` resolves membership **before** touching any store: `auth.role_for(user_id, brf_id)`
is an exact SQL equality on the raw path string, and `registry.get(brf_id)` uses the *same* raw
string — so the classic path-normalization confused-deputy is impossible. Non-members get 404, so
ids can't be probed. Isolation is object-graph + filesystem (own `Store`/`HybridIndex` under
`tenants/<brf_id>/`), so retrieval physically cannot span tenants. Doc routes look up `doc_id` only
in the resolved store's own map. Citation resolution further restricts the model to chunks it was
shown — even a malicious model cannot cite B.

## Secondary finding (not a boundary bypass) — FIXED

`POST /api/reset` had **no auth dependency** — in dev mode an anonymous caller could wipe all
tenants and reseed. The agent correctly characterized it as *not* a cross-tenant leak (dev-gated,
global, symmetric, self-reseeding — it does not move B's data to A) and deliberately did not
detonate it. Fixed regardless: `/api/reset` now requires an authenticated session
(`Depends(current_user)`) on top of being dev-only, and the unused client method was removed.
Tests `test_reset_requires_authentication_in_dev` and `test_reset_forbidden_outside_dev` (now
asserting 401) lock it in.

## Reproduction

The target was seeded via `scripts.seed.seed_demo` into a scratch data root and served with
`BRF_MODE=dev BRF_LLM=fake` on :8791. The attack scripts were throwaway (scratchpad only); no repo
file was modified and the server was not restarted during the attack.
