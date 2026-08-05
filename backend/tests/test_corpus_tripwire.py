"""Corpus-mixing tripwire (CI3). CI2 made `corpus_origin` a structural,
non-bypassable tenant property (`tenant_meta.json`, stamped onto every
`DocumentMeta` at ingestion, naming rules on the `brf_id` namespace) and
migrated the two pre-existing dev tenants onto it. That was a one-time
review. This file turns it into a permanent, WALKED property: every tenant
directory under a data root is checked, every time the suite runs, so a
future bug that writes a document with the wrong origin (a bypassed
`add_document` call, a hand-edited `documents.json`, a broken migration)
gets caught here instead of being discovered in production.

The one invariant every tenant must satisfy:
  1. `tenant_meta.json` exists and declares a valid corpus_origin.
  2. Every document under that tenant carries that SAME corpus_origin —
     no per-doc value is missing, and no two documents disagree.
  3. The tenant's `brf_id` naming matches its origin (`val-` prefix iff
     `public_scraped`; `customer` forbids the `val-` prefix; `synthetic` is
     unconstrained) — the same rule `app.registry._check_naming` enforces
     at creation time, re-derived independently here rather than imported,
     so a drift between the two implementations would itself be visible.

Missing/malformed `tenant_meta.json`, or a per-document `corpus_origin` that
is still absent, is a FAILURE here, not a skip — CI2's migration
(`Store._load_or_init_corpus_origin` / `Store._load_documents`) is supposed
to have already fixed every tenant on disk; a tenant that still lacks
origin is exactly the regression this file exists to catch.

Two independent checks:
  - `TestWalkerOnConstructedRoot` / `TestPlantedMixingIsCaught` /
    `TestNamingViolationIsCaught`: a data root built fresh inside this test
    session (via the real `TenantRegistry`/`Store` API, plus hand-planted
    violations that bypass it) — proves the walker has zero false positives
    on a healthy tree AND actually catches a planted violation.
  - `TestRealDevDataRoot` (marked `realdata`): walks the REAL dev data root,
    `backend/data/tenants` (gitignored; currently the two synthetic demo
    tenants `gjutformen-12`/`sjoutsikten-7`). Skipped only if that root
    doesn't exist at all (a fresh checkout with no dev data yet is not a
    violation). Its location is overridable via `BRF_TRIPWIRE_REAL_ROOT` so
    a RED-proof run can point this exact test at a throwaway copy without
    ever writing to the real directory — see
    docs/evidence/corpus-isolation.md for a recorded RED/green run.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.auth import AuthStore
from app.registry import TenantRegistry
from app.schemas import CORPUS_ORIGINS
from tests.pdf_fixtures import build_pdf

VAL_PREFIX = "val-"
REAL_ROOT_ENV = "BRF_TRIPWIRE_REAL_ROOT"


# ---------- the walker ----------


@dataclass
class TenantReport:
    brf_id: str
    tenant_dir: Path
    tenant_meta_origin: str | None  # None = missing file, unreadable, or invalid value
    doc_origins: set[str | None]  # one entry per document; None = corpus_origin key missing
    doc_count: int


def _read_tenant_meta_origin(tenant_dir: Path) -> str | None:
    p = tenant_dir / "tenant_meta.json"
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text("utf-8"))
    except Exception:
        return None
    origin = raw.get("corpus_origin") if isinstance(raw, dict) else None
    return origin if origin in CORPUS_ORIGINS else None


def _read_doc_origins(tenant_dir: Path) -> tuple[set[str | None], int]:
    p = tenant_dir / "documents.json"
    if not p.exists():
        return set(), 0
    raw = json.loads(p.read_text("utf-8"))
    origins = {v.get("corpus_origin") for v in raw.values()}
    return origins, len(raw)


def walk_tenants(tenants_root: Path) -> list[TenantReport]:
    """Every immediate subdirectory of `tenants_root` that looks like a
    tenant (has a `tenant_meta.json` and/or a `documents.json` — a stray
    unrelated directory under the root, if one ever existed, is not
    mistaken for a tenant). Order is deterministic (sorted by name)."""
    if not tenants_root.exists():
        return []
    reports = []
    for child in sorted(p for p in tenants_root.iterdir() if p.is_dir()):
        meta_path = child / "tenant_meta.json"
        docs_path = child / "documents.json"
        if not meta_path.exists() and not docs_path.exists():
            continue
        origin = _read_tenant_meta_origin(child)
        doc_origins, doc_count = _read_doc_origins(child)
        reports.append(TenantReport(child.name, child, origin, doc_origins, doc_count))
    return reports


def _naming_violation(brf_id: str, origin: str | None) -> str | None:
    """Independently re-derives `app.registry._check_naming`'s rule (not
    imported — a drift between the two would itself show up as this
    function disagreeing with what `TenantRegistry.create` allowed)."""
    is_val = brf_id.startswith(VAL_PREFIX)
    if origin == "public_scraped" and not is_val:
        return f"{brf_id}: origin 'public_scraped' requires a '{VAL_PREFIX}' prefix, but the brf_id doesn't have one."
    if origin == "customer" and is_val:
        return f"{brf_id}: origin 'customer' must NOT have a '{VAL_PREFIX}' prefix, but the brf_id does."
    return None


def assert_tenant_not_mixed(report: TenantReport) -> None:
    """The property this whole file exists to guard: one tenant, one origin,
    everywhere — declared on disk, matched by every document, matched by
    the naming convention. Raises AssertionError naming the tenant and the
    conflicting origin(s) on any violation."""
    assert report.tenant_meta_origin is not None, (
        f"{report.brf_id}: tenant_meta.json is missing or malformed at {report.tenant_dir / 'tenant_meta.json'} "
        f"— CI2's migration (Store._load_or_init_corpus_origin) should have written a valid corpus_origin here."
    )
    assert None not in report.doc_origins, (
        f"{report.brf_id}: at least one document has no corpus_origin field — "
        f"CI2's per-document migration (Store._load_documents) should have stamped one."
    )
    assert report.doc_origins <= {report.tenant_meta_origin}, (
        f"{report.brf_id}: mixed corpus_origin across documents {sorted(report.doc_origins)} — "
        f"tenant_meta.json declares '{report.tenant_meta_origin}'."
    )
    violation = _naming_violation(report.brf_id, report.tenant_meta_origin)
    assert violation is None, violation


# ---------- constructed-root fixtures ----------


def _doc_meta(doc_id: str, corpus_origin: str) -> dict:
    """A minimal, schema-shaped documents.json entry — enough for the
    walker (and DocumentMeta, if something else ever loads it) to be happy."""
    return {
        "id": doc_id,
        "name": f"{doc_id}.pdf",
        "pages": 1,
        "words": 3,
        "chunks": 1,
        "uploaded_at": "2026-01-01T00:00:00+00:00",
        "source": "digital",
        "corpus_origin": corpus_origin,
    }


def _build_healthy_root(tmp_path: Path) -> Path:
    """A multi-tenant root covering all three origins (one tenant each,
    two documents apiece), built through the REAL API (TenantRegistry +
    Store.add_document) — not hand-written — so this proves the walker
    against tenants that came into being exactly the way production ones
    do."""
    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)
    registry.create("Customer Co", "customer", "brf-cust-1")
    registry.create("Public Scrape", "public_scraped", "val-scrape-1")
    registry.create("Synthetic Demo", "synthetic", "brf-synth-1")
    for brf_id in ("brf-cust-1", "val-scrape-1", "brf-synth-1"):
        store = registry.get(brf_id)
        store.add_document("A.pdf", build_pdf([[("Text A.", 72, 100)]]))
        store.add_document("B.pdf", build_pdf([[("Text B.", 72, 100)]]))
    return tmp_path / "tenants"


def _plant_mixed_tenant(tenants_root: Path, brf_id: str = "brf-mixed-1") -> Path:
    """Hand-writes a tenant directory whose two documents DISAGREE on
    corpus_origin, bypassing Store/TenantRegistry entirely — exactly the
    shape a future bug (a bypassed add_document call, a hand-edited
    documents.json, a broken migration) would take."""
    tenant_dir = tenants_root / brf_id
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "tenant_meta.json").write_text(json.dumps({"corpus_origin": "customer"}), "utf-8")
    (tenant_dir / "documents.json").write_text(
        json.dumps(
            {
                "doc1": _doc_meta("doc1", "customer"),
                "doc2": _doc_meta("doc2", "public_scraped"),
            }
        ),
        "utf-8",
    )
    return tenant_dir


def _plant_wrong_naming_tenant(tenants_root: Path, brf_id: str = "val-should-not-be-customer") -> Path:
    """A tenant with internally-consistent origins (no mixing) but a naming
    violation: a 'val-' brf_id declaring 'customer' origin."""
    tenant_dir = tenants_root / brf_id
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "tenant_meta.json").write_text(json.dumps({"corpus_origin": "customer"}), "utf-8")
    (tenant_dir / "documents.json").write_text(json.dumps({"doc1": _doc_meta("doc1", "customer")}), "utf-8")
    return tenant_dir


# ---------- tests: healthy constructed root (zero false positives) ----------


class TestWalkerOnConstructedRoot:
    def test_walk_finds_every_tenant(self, tmp_path):
        root = _build_healthy_root(tmp_path)
        reports = walk_tenants(root)
        assert {r.brf_id for r in reports} == {"brf-cust-1", "val-scrape-1", "brf-synth-1"}

    @pytest.mark.parametrize("expected_origin", ["customer", "public_scraped", "synthetic"])
    def test_healthy_tenant_has_no_violations(self, tmp_path, expected_origin):
        root = _build_healthy_root(tmp_path)
        by_origin = {r.tenant_meta_origin: r for r in walk_tenants(root)}
        report = by_origin[expected_origin]
        assert report.doc_count == 2
        assert_tenant_not_mixed(report)  # must not raise


# ---------- tests: RED proof — planted mixing is caught ----------


class TestPlantedMixingIsCaught:
    def test_mixed_tenant_fails_naming_tenant_and_both_origins(self, tmp_path):
        tenants_root = tmp_path / "tenants"
        _plant_mixed_tenant(tenants_root)
        reports = walk_tenants(tenants_root)
        assert len(reports) == 1

        with pytest.raises(AssertionError) as excinfo:
            assert_tenant_not_mixed(reports[0])
        message = str(excinfo.value)
        assert "brf-mixed-1" in message
        assert "customer" in message
        assert "public_scraped" in message

    def test_removing_the_plant_restores_green(self, tmp_path):
        tenants_root = tmp_path / "tenants"
        tenant_dir = _plant_mixed_tenant(tenants_root)
        shutil.rmtree(tenant_dir)
        assert walk_tenants(tenants_root) == []  # nothing left to check


class TestNamingViolationIsCaught:
    def test_customer_tenant_with_val_prefix_fails_naming(self, tmp_path):
        tenants_root = tmp_path / "tenants"
        _plant_wrong_naming_tenant(tenants_root)
        reports = walk_tenants(tenants_root)
        assert len(reports) == 1
        with pytest.raises(AssertionError, match="val-should-not-be-customer"):
            assert_tenant_not_mixed(reports[0])


# ---------- the real dev data root ----------


def _default_real_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tenants"


def _real_root() -> Path:
    override = os.environ.get(REAL_ROOT_ENV)
    return Path(override) if override else _default_real_root()


@pytest.mark.realdata
class TestRealDevDataRoot:
    """The actual property the pilot depends on, not just a constructed
    proxy for it. Runs against `backend/data/tenants` by default; skipped
    only if that directory doesn't exist on this checkout at all (gitignored
    — a fresh clone has none). See module docstring for the RED-proof
    override seam (`BRF_TRIPWIRE_REAL_ROOT`)."""

    def test_real_tenants_are_not_mixed(self):
        root = _real_root()
        if not root.exists():
            pytest.skip(f"no data root at {root} — nothing to check on this checkout")
        reports = walk_tenants(root)
        assert reports, f"{root} exists but contains no tenant directories (sanity check: not vacuous)"
        for report in reports:
            assert_tenant_not_mixed(report)
