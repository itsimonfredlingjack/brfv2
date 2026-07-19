# Evidence — corpus isolation: CI1–CI3 (2026-07-19)

Three document collections back this system and must never blend: real customer BRF
documents, a scraped public corpus of annual reports, and synthetic fixtures used for
tests/eval/demos. This phase (CI1–CI3) made that separation physical (CI1), structural
on the tenant model (CI2), and now permanently self-checking (CI3).

**Redaction:** this report is metrics/mechanism-only — no real document content, no
real tenant ids beyond the two already-named dev demo tenants, no customer data.

## The three collections and where they physically live

| Collection | `corpus_origin` | Physical location | Repo status |
| --- | --- | --- | --- |
| Real customer documents | `customer` | `backend/data/tenants/<brf_id>/` (pilot tenants) and `DONT_PUSH_brf_stuff/` (repo root, used only by reality scripts) | gitignored, in-repo directory tree |
| Scraped public annual reports | `public_scraped` | `~/brf-corpus-public/brf-annual-reports-2026-07-18/` | **outside the repo entirely** (moved there in CI1 — a path outside the repo is a hard boundary; `.gitignore` is only a convention) |
| Synthetic fixtures | `synthetic` | `backend/data/tenants/` (the two dev demo tenants), plus in-memory PDF fixtures built by tests/eval (`tests/pdf_fixtures.py`, `scripts/seed.py`) | gitignored where on disk; fixture-builders themselves are committed code, not data |

## The design: origin is a tenant property, structurally enforced (CI2)

`corpus_origin` is declared once, on the **tenant**, at creation — never per-document,
never inferred from path or filename, never caller-suppliable. Mechanism
(`backend/app/store.py`, `backend/app/registry.py`):

- `tenant_meta.json` — a file sibling to `documents.json`/`settings.json` under
  `data_root/tenants/<brf_id>/`, holding `{"corpus_origin": "..."}`. Once it exists on
  disk it is authoritative; a caller-supplied value is only used when a tenant directory
  doesn't have one yet.
- `TenantRegistry.create(name, corpus_origin, brf_id=None)` — `corpus_origin` is a
  **required** parameter, no default. Omitting it is a `TypeError` at the call site.
- `Store.add_document(name, pdf_bytes)` — **no origin parameter at all**. There is no
  argument to abuse: every ingested document is stamped with `self.corpus_origin`, the
  tenant's own value, at construction. A defensive check right after construction
  guards any future refactor that might build `DocumentMeta` some other way (proven in
  `test_corpus_isolation.py::TestMismatchDefenseRaises` by forcing exactly that shape of
  mismatch).

## Naming rules

The `brf_id` namespace is kept honest about a tenant's declared origin
(`app/registry.py::_check_naming`, enforced in `TenantRegistry.create` before the
tenant registers in auth at all):

- `public_scraped` **requires** a `val-` prefix.
- `customer` **forbids** a `val-` prefix.
- `synthetic` is unconstrained (no naming rule — the two pre-existing demo tenants
  needed no grandfather clause beyond that).

## Migration outcome

Both real dev tenants under `backend/data/tenants/` (gitignored) predate CI2 and were
migrated live: `gjutformen-12` and `sjoutsikten-7` — no `tenant_meta.json`, and
`documents.json` entries with no `corpus_origin` key. First `Store` load after CI2
wrote `tenant_meta.json` with `{"corpus_origin": "synthetic"}` for both and backfilled
`corpus_origin: "synthetic"` onto every existing document entry. Verified idempotent
(second load: no further changes). Confirmed again now, before writing this report:

```
gjutformen-12   {'e0a0e033d523': 'synthetic', 'cc9fca0e9d46': 'synthetic', '96920eeac4ff': 'synthetic', 'b2aec2ad93cb': 'synthetic', '623032ccf0b6': 'synthetic'}
sjoutsikten-7   {'be86bd20b7c2': 'synthetic', 'ebd9273c9372': 'synthetic', 'e67b9260a651': 'synthetic', '744d5b2cf09d': 'synthetic'}
```

Both tenants: single origin, matching `tenant_meta.json`, non-`val-` names — consistent
with `synthetic`'s unconstrained naming rule.

## The mixing tripwire (CI3)

`backend/tests/test_corpus_tripwire.py` — the backend counterpart to
`src/no-fabrication.test.js`: a **walked**, permanent version of the one-time CI2
migration check. Core signatures:

```python
def walk_tenants(tenants_root: Path) -> list[TenantReport]:
    """Every immediate subdirectory of tenants_root that looks like a tenant
    (has a tenant_meta.json and/or a documents.json)."""

def assert_tenant_not_mixed(report: TenantReport) -> None:
    """tenant_meta.json exists and is valid; every document's corpus_origin
    is present and equals tenant_meta's; brf_id naming matches origin."""
```

Two independent test classes exercise it:

- **Constructed root** (`TestWalkerOnConstructedRoot`, `TestPlantedMixingIsCaught`,
  `TestNamingViolationIsCaught`) — a data root built fresh each test run through the
  real `TenantRegistry`/`Store` API (one tenant per origin, two documents each) proves
  zero false positives; a hand-planted mixed tenant (two documents with differing
  `corpus_origin`, written directly to `documents.json`, bypassing the API — exactly the
  shape a future bug would take) proves the walker catches it.
- **Real dev data root** (`TestRealDevDataRoot`, marked `realdata`) — walks the actual
  `backend/data/tenants/` (gitignored). Skips only if that directory doesn't exist at
  all (fresh checkout, no dev data yet); a malformed/missing `tenant_meta.json` or a
  still-missing per-document origin on an *existing* tenant is a **failure**, not a
  skip. Location overridable via `BRF_TRIPWIRE_REAL_ROOT` — the seam used for the
  RED proof below, so the real directory is never written to by a test run.

### RED proof 1 — constructed scratch root

Planted a tenant directory by hand (bypassing `Store`/`TenantRegistry` entirely) with
`tenant_meta.json` declaring `customer` and two documents disagreeing
(`customer` / `public_scraped`), then ran the tripwire's own functions against it:

```
AssertionError: brf-mixed-demo: mixed corpus_origin across documents ['customer', 'public_scraped'] — tenant_meta.json declares 'customer'.
```

Removed the planted tenant directory, re-ran: `walk_tenants` returned `[]` (nothing
left to check) — green.

### RED proof 2 — real data root, throwaway copy

Copied `backend/data/tenants/` to a scratch location, mutated **one document** inside
the copy of `gjutformen-12` from `synthetic` to `customer` (the other four documents in
that tenant untouched), then ran `TestRealDevDataRoot` with
`BRF_TRIPWIRE_REAL_ROOT` pointed at the copy:

```
AssertionError: gjutformen-12: mixed corpus_origin across documents ['customer', 'synthetic'] — tenant_meta.json declares 'synthetic'.
```

Confirmed the real `backend/data/tenants/gjutformen-12/documents.json` was untouched
(all five documents still `synthetic`) before deleting the throwaway copy. Re-ran
`TestRealDevDataRoot` against the real (unmodified) root afterward: **1 passed**.

## Customer-cannot-receive-scraped: the black-box guard

`backend/tests/test_corpus_isolation.py::TestCustomerCannotReceiveScrapedOrigin` — even
though `add_document` has no origin parameter to test against directly, this proves the
guarantee end to end and adversarially:

- A `customer`-origin tenant's documents, ingested via the **direct `Store` API**, only
  ever carry `corpus_origin == "customer"`.
- The same tenant, ingested via the **real HTTP upload route**
  (`POST /api/brf/{brf_id}/documents`, through the app fixture) — same result, including
  the listing endpoint.
- A request that stuffs an extra `corpus_origin: "public_scraped"` form field into the
  multipart upload (an adversarial smuggling attempt) is silently ignored by FastAPI
  (no bound parameter) — the document still lands as `customer`.
- **Signature tests**, so this stops being true only by accident: `inspect.signature`
  on `Store.add_document` must be exactly `{name, pdf_bytes}`; the *actual registered*
  FastAPI route object for the upload endpoint (introspected from `app.routes`, not a
  hand-copied assumption) must not have gained an `origin`/`corpus_origin`-shaped
  parameter. Either test fails the moment someone adds one.

## The CI2-flagged mislabel — fixed

`backend/scripts/reality/digital_reality.py` ingests a **real customer document** from
the local gitignored corpus (`DONT_PUSH_brf_stuff/`) into a bare
`Store(data_dir=tempfile.mkdtemp(...))` with no `corpus_origin` argument — which, after
CI2's migration default, silently inherited `"synthetic"`. CI2's own report flagged this
as an out-of-scope residual gap. Fixed here with the smallest honest change:

```python
store = Store(data_dir=tempfile.mkdtemp(prefix="brf-reality-"), corpus_origin="customer")
```

No other restructuring; `--help` still resolves cleanly (import/argparse unaffected).

## Trivial hardening: `TenantRegistry.delete` and `tenant_meta.json`

`TenantRegistry.delete` calls `shutil.rmtree(..., ignore_errors=True)` — a mid-tree
failure is silently swallowed, which could in principle leave `tenant_meta.json`
behind for a same-`brf_id` recreate to inherit unexpectedly (CI2 flagged this as a
pre-existing risk). Fixed with an explicit unlink after the `rmtree` call:

```python
shutil.rmtree(self._tenant_dir(brf_id), ignore_errors=True)
(self._tenant_dir(brf_id) / "tenant_meta.json").unlink(missing_ok=True)
```

Tested in `test_lifecycle.py::TestTenantMetaHardeningOnDelete` by monkeypatching
`shutil.rmtree` to a no-op (simulating the exact failure `ignore_errors=True` is meant
to swallow): `tenant_meta.json` is still gone afterward, and recreating the same
`brf_id` with a **different** origin (`customer` → `synthetic`) picks up the new one
with no stale residue. Confirmed the test fails without the fix (reverted
`registry.py` only, re-ran): `AssertionError: assert not True` on
`meta_path.exists()` — then restored the fix.

## Suite counts

- Full offline suite: `uv run pytest -q` → **375 passed, 1 skipped**
  (baseline 361 passed/1 skipped + 14 new: 8 in `test_corpus_tripwire.py`, 5 in
  `test_corpus_isolation.py`, 1 in `test_lifecycle.py`).
- Isolation trio (`test_isolation.py test_lifecycle.py test_auth.py`) →
  **48 passed** (baseline 47 + 1 new hardening test).

## Reproduce

```
# Full suite + isolation trio
cd backend && uv run pytest -q
uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py

# Just the tripwire (constructed root + real data root)
uv run pytest -q tests/test_corpus_tripwire.py -v

# Just the customer black-box guard
uv run pytest -q tests/test_corpus_isolation.py -v

# Real-data-root RED proof (never touches the real directory):
#   cp -R backend/data/tenants /tmp/scratch-tenants
#   hand-edit one document's corpus_origin in the copy to disagree with its siblings
BRF_TRIPWIRE_REAL_ROOT=/tmp/scratch-tenants uv run pytest -q tests/test_corpus_tripwire.py::TestRealDevDataRoot -v
#   then: rm -rf /tmp/scratch-tenants
```
