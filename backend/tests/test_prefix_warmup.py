"""Background prefix warmup after archive text changes."""

from __future__ import annotations

from app.llm import FakeLLM, LLMError
from app.prefix_warmup import WARMUP_QUESTION, schedule_warm_prefix, warm_prefix
from tests.pdf_fixtures import build_pdf
from tests.test_full_corpus import StubRuntime, _two_chunk_store


def test_warm_prefix_sends_question_last_dummy(tmp_path):
    st = _two_chunk_store(tmp_path)
    fake = FakeLLM([{"answer": "x", "citations": [], "insufficient_data": True}])
    out = warm_prefix(st, StubRuntime(), fake)
    assert out["status"] == "done"
    assert fake.calls
    user = fake.calls[0]["user"]
    assert user.startswith("UTDRAG:")
    assert f"FRÅGA: {WARMUP_QUESTION}" in user
    assert user.index("UTDRAG:") < user.index("FRÅGA:")
    assert fake.calls[0]["max_tokens"] == 1


def test_warm_prefix_skips_when_threshold_zero(tmp_path):
    st = _two_chunk_store(tmp_path)
    st.update_settings(st.settings.model_copy(update={"fullCorpusTokenThreshold": 0}))
    fake = FakeLLM([{"answer": "x", "citations": [], "insufficient_data": True}])
    out = warm_prefix(st, StubRuntime(), fake)
    assert out["status"] == "skip"
    assert out["reason"] == "threshold"
    assert fake.calls == []


def test_warm_prefix_skips_stale_generation(tmp_path):
    st = _two_chunk_store(tmp_path)
    st._warmup_gen = 2
    fake = FakeLLM([{"answer": "x", "citations": [], "insufficient_data": True}])
    out = warm_prefix(st, StubRuntime(), fake, expected_gen=1)
    assert out["status"] == "skip"
    assert out["reason"] == "stale"
    assert fake.calls == []


def test_warm_prefix_swallows_truncated_completion(tmp_path):
    st = _two_chunk_store(tmp_path)

    class Truncating:
        def complete(self, system, user, *, max_tokens, model):
            self.called = True
            raise LLMError("truncated")

    provider = Truncating()
    out = warm_prefix(st, StubRuntime(), provider)
    assert provider.called is True
    assert out["status"] == "done"


def test_schedule_is_noop_when_llm_is_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("BRF_LLM", "fake")
    st = _two_chunk_store(tmp_path)
    called = []
    monkeypatch.setattr("app.prefix_warmup.warm_prefix", lambda *a, **k: called.append(1))
    schedule_warm_prefix(st)
    assert called == []


def test_rebuild_does_not_warm_under_fake_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("BRF_LLM", "fake")
    monkeypatch.setattr(
        "app.prefix_warmup.warm_prefix",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("rebuild must not warm under fake LLM")),
    )
    st = _two_chunk_store(tmp_path)
    st.add_document("C.pdf", build_pdf([[("Tredje dokumentet.", 72, 100)]]))
    assert st.chunks
