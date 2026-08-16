"""Size-gated full-corpus ask path (docs/superpowers/specs/2026-08-16-full-corpus-ask-design.md)."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from app.answer import ask
from app.full_corpus import LlamaCppRuntime, decide_fit, live_corpus_runtime, server_origin
from app.llm import FakeLLM
from app.schemas import CitationOut
from app.store import Store
from tests.pdf_fixtures import build_pdf


def test_server_origin_strips_v1_suffix():
    assert server_origin("http://127.0.0.1:8000/v1") == "http://127.0.0.1:8000"
    assert server_origin("http://127.0.0.1:8000/v1/") == "http://127.0.0.1:8000"


def test_live_corpus_runtime_is_none_when_llm_is_fake(monkeypatch):
    monkeypatch.setenv("BRF_LLM", "fake")
    monkeypatch.setenv("BRF_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    assert live_corpus_runtime() is None


def test_n_ctx_reads_props_default_generation_settings_not_v1_models():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/props":
            return httpx.Response(
                200,
                json={"default_generation_settings": {"n_ctx": 16384}},
            )
        return httpx.Response(404, text="no")

    rt = LlamaCppRuntime("http://127.0.0.1:8000/v1", transport=httpx.MockTransport(handler))
    assert rt.n_ctx() == 16384
    assert any(u.endswith("/props") and "/v1/props" not in u for u in calls)
    assert not any("/v1/models" in u for u in calls)


def test_n_ctx_missing_returns_none(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"default_generation_settings": {}})

    rt = LlamaCppRuntime("http://127.0.0.1:8000/v1", transport=httpx.MockTransport(handler))
    with caplog.at_level("WARNING"):
        assert rt.n_ctx() is None
    assert "n_ctx" in caplog.text.lower()


def test_count_posts_tokenize_on_origin_not_v1():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tokenize"
        assert "/v1/" not in str(request.url)
        return httpx.Response(200, json={"tokens": [1, 2, 3]})

    rt = LlamaCppRuntime("http://127.0.0.1:8000/v1", transport=httpx.MockTransport(handler))
    assert rt.count("hej") == 3


QUESTION_RESERVE = 512
RESPONSE = 1800  # 1200 + 600 headroom, matches defaults


def test_default_threshold_is_none():
    from app.schemas import Settings

    assert Settings().fullCorpusTokenThreshold is None


def test_threshold_zero_forces_retrieval():
    d = decide_fit(chunk_token_sum=10, prefix_tokens=20, n_ctx=16384, threshold=0, response_budget=RESPONSE)
    assert d.use_full_corpus is False and d.bound == "threshold"


def test_missing_n_ctx_is_not_a_fit():
    d = decide_fit(chunk_token_sum=10, prefix_tokens=20, n_ctx=None, threshold=None, response_budget=RESPONSE)
    assert d.use_full_corpus is False and d.bound == "n_ctx_missing"


def test_none_threshold_fits_when_prefix_under_window():
    d = decide_fit(chunk_token_sum=40000, prefix_tokens=200, n_ctx=16384, threshold=None, response_budget=RESPONSE)
    assert d.use_full_corpus is True and d.bound == "fits"
    assert d.effective_cap == 16384 - QUESTION_RESERVE - RESPONSE


def test_chunk_token_sum_is_not_a_gate():
    d = decide_fit(chunk_token_sum=40000, prefix_tokens=100, n_ctx=16384, threshold=None, response_budget=RESPONSE)
    assert d.use_full_corpus is True and d.bound == "fits"


def test_n_ctx_binds_when_prefix_over_window():
    prefix = 14100
    d = decide_fit(
        chunk_token_sum=5000, prefix_tokens=prefix, n_ctx=16384, threshold=None, response_budget=RESPONSE
    )
    assert d.use_full_corpus is False and d.bound == "n_ctx"
    assert d.effective_cap == 16384 - QUESTION_RESERVE - RESPONSE


def test_optional_cap_binds_on_prefix_not_chunk_sum():
    d = decide_fit(
        chunk_token_sum=100, prefix_tokens=40000, n_ctx=65536, threshold=32000, response_budget=RESPONSE
    )
    assert d.use_full_corpus is False and d.bound == "threshold"
    assert d.effective_cap == 32000


class StubRuntime:
    def __init__(self, n=16384):
        self._n = n

    def n_ctx(self):
        return self._n

    def count(self, text: str) -> int:
        return max(1, len(text.split()))


def _two_chunk_store(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document("B.pdf", build_pdf([[("Andra dokumentets enda mening.", 72, 100)]]))
    st.add_document("A.pdf", build_pdf([[("Forsta dokumentets enda mening.", 72, 100)]]))
    # Tests that cite K1 as A.pdf assume name/page order, not the product probe U-shape.
    st._full_corpus_order = "page"
    return st


def test_full_corpus_skips_search_and_puts_question_last(tmp_path, monkeypatch):
    st = _two_chunk_store(tmp_path)
    st.update_settings(st.settings.model_copy(update={"minRelevance": 1.0}))
    fake = FakeLLM([{
        "answer": "Forsta dokumentets enda mening.",
        "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}],
        "insufficient_data": False,
    }])
    resp = ask(st, "Vad star det?", provider=fake, corpus_runtime=StubRuntime())
    assert not resp.refusal
    assert fake.calls, "relevansgrinden maste förbikopplas"
    user = fake.calls[0]["user"]
    assert user.startswith("UTDRAG:")
    assert user.rstrip().endswith("FRÅGA: Vad star det?") or "\n\nFRÅGA: Vad star det?" in user
    assert user.index("UTDRAG:") < user.index("FRÅGA:")
    assert len(resp.retrieval) == len(st.chunks)
    assert all(h.score == 0.0 and h.confidence == 0.0 and h.rerank_score is None for h in resp.retrieval)
    assert all(c.score is None for c in resp.citations)


def test_excerpt_count_equals_chunk_count(tmp_path):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([{
        "answer": "x",
        "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}],
        "insufficient_data": False,
    }])
    resp = ask(st, "x", provider=fake, corpus_runtime=StubRuntime())
    assert len(resp.retrieval) == len(st.chunks)
    user = fake.calls[0]["user"]
    for i in range(len(st.chunks)):
        assert f"[K{i+1}]" in user


def test_over_threshold_keeps_question_first(tmp_path):
    st = _two_chunk_store(tmp_path)
    st.update_settings(st.settings.model_copy(update={"fullCorpusTokenThreshold": 0, "minRelevance": 0.0}))
    fake = FakeLLM([{
        "answer": "x",
        "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}],
        "insufficient_data": False,
    }])
    ask(st, "Vad star det?", provider=fake, corpus_runtime=StubRuntime())
    assert fake.calls[0]["user"].startswith("FRÅGA:")


def test_citation_out_score_has_no_default():
    kwargs = dict(
        document_id="d", document_name="n", page=1, quote="q",
        quotes=["q"], chunk_id="c", rects=[[0, 0, 1, 1]],
    )
    with pytest.raises(ValidationError):
        CitationOut(**kwargs)
    cited = CitationOut(**kwargs, score=None)
    assert cited.score is None


def test_prefix_identical_across_questions(tmp_path):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([
        {"answer": "a", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
        {"answer": "b", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
    ])
    rt = StubRuntime()
    ask(st, "Fraga ett?", provider=fake, corpus_runtime=rt)
    ask(st, "Helt annan fraga?", provider=fake, corpus_runtime=rt)
    p0, p1 = fake.calls[0]["user"], fake.calls[1]["user"]
    prefix0 = p0.split("\n\nFRÅGA:")[0]
    prefix1 = p1.split("\n\nFRÅGA:")[0]
    assert prefix0 == prefix1
    assert fake.calls[0]["system"] == fake.calls[1]["system"]


def test_prefix_changes_when_document_added(tmp_path):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([
        {"answer": "a", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
        {"answer": "b", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
    ])
    rt = StubRuntime()
    ask(st, "Fraga?", provider=fake, corpus_runtime=rt)
    st.add_document("C.pdf", build_pdf([[("Tredje dokumentet.", 72, 100)]]))
    ask(st, "Fraga?", provider=fake, corpus_runtime=rt)
    assert fake.calls[0]["user"].split("\n\nFRÅGA:")[0] != fake.calls[1]["user"].split("\n\nFRÅGA:")[0]


def test_prefix_fingerprint_hashes_system_and_excerpts():
    from app.full_corpus import prefix_fingerprint

    same = prefix_fingerprint("sys", "utdrag")
    assert same == prefix_fingerprint("sys", "utdrag")
    assert same != prefix_fingerprint("sys", "annat")
    assert same != prefix_fingerprint("annat-sys", "utdrag")


def test_prefix_change_logged_on_first_ask_and_after_upload(tmp_path, caplog):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([
        {"answer": "a", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
        {"answer": "b", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
        {"answer": "c", "citations": [{"chunk_id": "K1", "quote": "Forsta dokumentets enda mening."}], "insufficient_data": False},
    ])
    rt = StubRuntime()
    with caplog.at_level("INFO"):
        ask(st, "Fraga ett?", provider=fake, corpus_runtime=rt)
        first = [r.message for r in caplog.records if "prefix_changed" in r.message]
        ask(st, "Helt annan fraga?", provider=fake, corpus_runtime=rt)
        second = [r.message for r in caplog.records if "prefix_changed" in r.message]
    assert len(first) == 1
    assert len(second) == 1
    caplog.clear()
    st.add_document("C.pdf", build_pdf([[("Tredje dokumentet.", 72, 100)]]))
    with caplog.at_level("INFO"):
        ask(st, "Fraga?", provider=fake, corpus_runtime=rt)
    assert any("prefix_changed" in r.message for r in caplog.records)


def test_spill_uses_same_word_join_as_chunker(tmp_path):
    from scripts.measure_corpus_tokens import report_association

    st = Store(data_dir=tmp_path)
    st.update_settings(st.settings.model_copy(update={"chunkSize": 5, "chunkOverlap": 2}))
    words = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    st.add_document("X.pdf", build_pdf([[(words, 72, 100)]]))
    rt = StubRuntime()
    row = report_association("x", st, rt)
    page = next(iter(st.pages.values()))[0]
    page_text = " ".join(w.text for w in page.words)
    unique = rt.count(page_text)
    chunk_sum = sum(rt.count(c.text) for c in st.chunks.values())
    assert row["unique_tokens"] == unique
    assert row["chunk_token_sum"] == chunk_sum
    assert row["spill"] == chunk_sum - unique
    assert row["spill"] > 0


def test_compare_counts_verified_to_refused_even_when_totals_match():
    from scripts.compare_ask_cases import compare_runs

    before = {
        "documents": {
            "a": {
                "questions": [
                    {"qid": "q1", "refused": False, "n_citations": 1, "refusal_reason": None, "elapsed_s": 1.0},
                    {"qid": "q2", "refused": True, "n_citations": 0, "refusal_reason": "insufficient_data", "elapsed_s": 1.0},
                ]
            }
        }
    }
    after = {
        "documents": {
            "a": {
                "questions": [
                    {"qid": "q1", "refused": True, "n_citations": 0, "refusal_reason": "insufficient_data", "elapsed_s": 2.0},
                    {"qid": "q2", "refused": False, "n_citations": 1, "refusal_reason": None, "elapsed_s": 2.0},
                ]
            }
        }
    }
    out = compare_runs(before, after)
    assert out["verified_to_refused"] == 1
    assert out["refused_to_verified"] == 1
    rows = {(r["doc"], r["qid"]): r for r in out["rows"]}
    assert rows[("a", "q1")]["before_refused"] is False
    assert rows[("a", "q1")]["after_refused"] is True



