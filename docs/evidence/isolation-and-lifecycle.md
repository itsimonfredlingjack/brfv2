# Evidence — tenant isolation, auth, and data lifecycle (2026-07-16)

The pilot's definition of working is: a member of BRF A can never retrieve, cite, see, or delete
BRF B's content, board-member login is enforced, and deleting a BRF hard-deletes all its data.
This is proven by tests (never by assertion) and by a fresh-context red-team.

## Isolation model — separation, not filtering

Each `brf_id` gets its **own `Store`** via `TenantRegistry`: its own filesystem directory
(`data/tenants/<brf_id>/`), its own chunk map, its own hybrid index, its own settings. There is
no shared collection and no retrieval path that spans tenants. A request resolves an
authenticated membership to a `brf_id` first (`tenant_store` dependency), and only then reaches
that tenant's Store. `brf_id` is validated against `^[a-z0-9][a-z0-9-]{0,63}$` before any path
use, so it cannot traverse the filesystem. Non-members receive **404, not 403**, so tenant and
document ids cannot be probed for existence.

Why this beats query-filtering (the research report's proposal): a forgotten `WHERE brf_id=…`
leaks; a separate object graph has no code path that returns another tenant's data. Correctness
depends on structure, not on every query remembering a filter.

## Automated suites — `make test-isolation` → 47 passed

```
uv run pytest tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py -q
47 passed, 6 warnings
```

### `test_isolation.py` (24 adversarial checks) — every one is an attack that must fail

- **Cross-tenant read (5):** A-admin listing B's documents, fetching B's PDF, reading B's
  extraction, reading B's settings, and requesting B's real doc_id under A's path — all 404, and
  B's secret bytes never appear in any response body.
- **Cross-tenant write (4):** A-admin uploading into B, deleting B's document, deleting B's
  tenant, changing B's settings — all 404; B's data verified unchanged afterward.
- **Cross-tenant retrieval (2):** asking BRF A a question built from B's unique secret code
  returns only A documents in `retrieval[]`; the two indexes are asserted to be physically
  separate objects with disjoint content.
- **Forged credentials (3):** no session → 401 on every verb; fabricated bearer token → 401; a
  *valid* B session still gets 404 on A's routes (a real login is still a stranger to A).
- **Id tricks (8):** `../brf-b`, `..%2fbrf-b`, `brf-b/../brf-b`, `brf-a/../../etc`, `brf_b`,
  `BRF-B`, leading-space (parametrized across 7 crafted ids) — none reach another tenant; an
  unknown tenant → 404.
- **Filesystem separation (1):** tenant directories are disjoint and neither nests in the other;
  each tenant's PDF files live only under its own directory.
- **Route-coverage meta-guard (1):** walks every `/api/brf/{brf_id}/…` route's dependency tree
  and fails if `tenant_store`/`require_admin` is absent — catches a *future* route added without
  isolation, not just today's.

### `test_auth.py` (17 tests)

Password hashing (scrypt, per-user salt, never stored plaintext — asserted against the raw DB
bytes), login success/failure, throttle after 10 failures + reset on success, session
round-trip, only the token *hash* stored (asserted against raw DB), expired/deleted/garbage
tokens rejected, role scoping (member vs admin vs non-member), and membership cascade on tenant
delete.

### `test_lifecycle.py` (6 tests)

- Document hard-delete removes PDF + extraction + chunks + index entry, verified by reloading the
  Store from disk (nothing resurrects).
- Whole-BRF hard-delete removes the directory, the index, and all memberships; a second tenant is
  verified completely untouched; a deleted tenant is not silently recreated by `registry.get`.
- Retention: `retentionDays` purges only documents older than the window; `0` keeps everything;
  the registry sweep is per-tenant (tenant A's window doesn't touch tenant B).

## Fresh-context red-team

A separate agent with no knowledge of the test suite attacked a live two-tenant instance
(`http://localhost:8791`, real HTTP, fake LLM) with BRF A credentials, trying to reach BRF B.
Both black-box (crafted requests) and white-box (reading the source for gaps). Full transcript
and verdicts: **`isolation-redteam.md`**.

## Full suite

`uv run pytest -q` → see `test-summary.txt`; the tenant work sits on top of the vertical slice's
grounding/citation/highlight tests, all still green.
