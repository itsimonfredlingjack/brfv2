from app.auth import AuthStore
from app.normalize import find_spans
from app.registry import TenantRegistry
from app.store import Store
from scripts.seed import DEMO_USERS, build_golden, render_pdf, seed_demo, seed_store
from scripts.seed_content import DOCUMENTS, GOLDEN_ANSWERABLE


def test_render_is_deterministic():
    a = render_pdf(DOCUMENTS[0])
    b = render_pdf(DOCUMENTS[0])
    assert a == b


def test_seed_corpus_shape(tmp_path):
    store = Store(data_dir=tmp_path)
    assert seed_store(store) == 5
    assert len(store.documents) == 5
    for meta in store.documents.values():
        assert meta.pages >= 2
        assert meta.chunks >= 1
        assert meta.words > 100


def test_golden_passages_all_locatable(tmp_path):
    store = Store(data_dir=tmp_path)
    seed_store(store)
    golden = build_golden(store)  # raises if any passage is unfindable
    assert len(golden["answerable"]) == len(GOLDEN_ANSWERABLE)
    assert len(golden["unanswerable"]) >= 8
    for qa in golden["answerable"]:
        assert qa["rects"], qa["id"]
        for x0, y0, x1, y1 in qa["rects"]:
            assert 0 <= x0 < x1 <= 595 and 0 <= y0 < y1 <= 842


def test_golden_passages_also_match_extraction_pipeline(tmp_path):
    """The independent golden locator (search_for) and our own word pipeline
    must agree that each passage exists on the claimed page."""
    store = Store(data_dir=tmp_path)
    seed_store(store)
    golden = build_golden(store)
    by_name = {m.name: m.id for m in store.documents.values()}
    for qa in golden["answerable"]:
        pages = store.pages[by_name[qa["document"]]]
        words = [w.text for w in pages[qa["page"] - 1].words]
        assert find_spans(words, qa["passage"]), f"{qa['id']}: {qa['passage'][:50]!r}"


def test_hyphenation_split_present_in_corpus(tmp_path):
    """The Årsredovisning plants 'för-'/'valtningen' across a line break —
    keep it there; unit + eval scenarios rely on it."""
    store = Store(data_dir=tmp_path)
    seed_store(store)
    doc_id = next(m.id for m in store.documents.values() if m.name == "Årsredovisning 2025.pdf")
    all_words = [w.text for p in store.pages[doc_id] for w in p.words]
    assert "för-" in all_words
    assert "valtningen" in all_words


def test_seed_demo_reset_preserves_memberships(tmp_path):
    """`--reset` wipes tenants (memberships cascade via FK) but auth.db's
    users table survives across resets. Regression: seed_demo() used to
    `continue` past its membership-reconciliation loop whenever a demo
    user's create_user() raised AuthError (i.e. every second-and-later
    run), leaving every demo account with zero memberships after a
    reset+reseed even though the run reported success."""
    auth = AuthStore(tmp_path / "auth.db")
    registry = TenantRegistry(tmp_path, auth)

    seed_demo(registry, auth)
    # Simulate `python -m scripts.seed --reset`'s tenant wipe: users persist.
    for t in registry.list():
        registry.delete(t["brf_id"])
    seed_demo(registry, auth)

    for email, password, _name, expected_mems in DEMO_USERS:
        user = auth.get_user_by_email(email)
        assert user is not None, email
        mems = auth.memberships_for(user["id"])
        assert len(mems) == len(expected_mems), (email, mems)  # no duplicates
        assert {m["brf_id"]: m["role"] for m in mems} == dict(expected_mems), email
        assert auth.verify_login(email, password) == user["id"], email
