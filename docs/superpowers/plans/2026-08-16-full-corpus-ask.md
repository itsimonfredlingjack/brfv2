# Full-corpus ask path — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an association’s chunk-token sum fits both the configurable threshold and live `n_ctx`, skip retrieval and put every chunk in the prompt (document/page order, same excerpt format, question last); otherwise leave today’s path unchanged.

**Architecture:** A new `app/full_corpus.py` owns token counting, `n_ctx` from `GET {origin}/props`, the two-bound fit gate, hit building, and prefix fingerprint. `ask()` branches on the gate before search. `_synthesize` and the citation/numeric chain stay untouched except `CitationOut.score=None` on this path and user-prompt order. llama.cpp `/tokenize` and `/props` are called on the server origin (strip `/v1` from `BRF_LLM_BASE_URL`).

**Tech Stack:** FastAPI backend, Pydantic Settings, llama.cpp server (`b9976`, `n_ctx=16384`), FakeLLM tests, reality scripts.

## Global Constraints

- Python 3.12; `uv` in `backend/`. Offline tests: `BRF_LLM=fake`, `BRF_EMBEDDER=hashed`.
- No non-loopback network. `scripts.eval.install_network_audit` on live scripts.
- Nothing derived from a real document is committed (numeric reports only).
- Citation resolver, numeric gate, excerpt label format unchanged.
- Retrieval path byte-for-byte unchanged when the gate is false (`n_ctx` missing, threshold 0, over cap).
- Code in English; user-facing strings and commit messages in Swedish.
- `CitationOut.score: float | None` required, **no default**.
- Spec: `docs/superpowers/specs/2026-08-16-full-corpus-ask-design.md`.

## File map

| Path | Role |
| --- | --- |
| Create `backend/app/full_corpus.py` | Origin helper, token counter, `n_ctx`, `FitDecision`, hit builder, prefix hash |
| Modify `backend/app/schemas.py` | `Settings.fullCorpusTokenThreshold` default 32000; `CitationOut.score: float \| None` |
| Modify `backend/app/answer.py` | Gate before search; question-last user prompt; bypass `minRelevance`; `score=None` |
| Modify `backend/app/llm.py` | `cache_prompt: true`; log timings; `DeterministicTestLLM` both prompt orders; origin URL |
| Modify `backend/app/multihop.py` | Skip `plan_query` when the archive fits |
| Create `backend/scripts/measure_corpus_tokens.py` | Per-association numeric token report |
| Modify `backend/scripts/reality/refusal_buckets.py` | Opt-in `--prompt-chunks` (default remains `index.search` topK) |
| Create `backend/scripts/compare_ask_cases.py` | Per-(doc, question) before→after table; headline verified→refused |
| Create `backend/tests/test_full_corpus.py` | Gate, prompt, scores, prefix, excerpt count |
| Modify `backend/tests/test_llm.py` | `cache_prompt` in payload; DeterministicTestLLM UTDRAG-first |
| Modify `backend/tests/test_refusal_buckets.py` | Opt-in mode `retrieval_miss==0` |
| Modify `xs_mobilapp/src/api/types.ts`, `kalla-native/src/api/types.ts` | `score: number \| null` |

---

### Task 1: Server origin, `n_ctx` from `/props`, tokenizer

**Files:**
- Create: `backend/app/full_corpus.py`
- Test: `backend/tests/test_full_corpus.py`

**Interfaces:**
- Produces: `server_origin(base_url: str) -> str`, `class LlamaCppRuntime` with `n_ctx() -> int | None` and `count(text: str) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_full_corpus.py
import httpx
import pytest

from app.full_corpus import LlamaCppRuntime, server_origin


def test_server_origin_strips_v1_suffix():
    assert server_origin("http://127.0.0.1:8000/v1") == "http://127.0.0.1:8000"
    assert server_origin("http://127.0.0.1:8000/v1/") == "http://127.0.0.1:8000"


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/simon/brfv2/backend && uv run pytest -q tests/test_full_corpus.py -v
```

Expected: `ModuleNotFoundError: app.full_corpus` or collection error.

- [ ] **Step 3: Write minimal implementation**

`server_origin`: rstrip `/`, remove trailing `/v1`. `LlamaCppRuntime` uses a separate httpx client on that origin (not the `/v1` chat client). `n_ctx()`: GET `/props`, read `default_generation_settings.n_ctx`; if missing GET `/slots` and read `[0].n_ctx`; else WARN + `None`. `count()`: POST `/tokenize` `{"content": text}`, return `len(tokens)`.

- [ ] **Step 4: Re-run tests — expect PASS**

- [ ] **Step 5: Commit** (only if the human asked for commits)

```text
feat(ask): läs n_ctx från llama.cpp /props och tokenisera på origin
```

---

### Task 2: Fit gate with explicit bound logging

**Files:**
- Modify: `backend/app/full_corpus.py`
- Modify: `backend/app/schemas.py` (`fullCorpusTokenThreshold: int = Field(default=32000, ge=0)`)
- Test: `backend/tests/test_full_corpus.py`

**Interfaces:**
- Produces: `FitDecision(use_full_corpus, bound, chunk_token_sum, prefix_tokens, n_ctx, threshold, effective_cap)`
- `decide_fit(*, chunk_token_sum, prefix_tokens, n_ctx, threshold, question_reserve=512, response_budget) -> FitDecision`

Bounds (verbatim from spec): `threshold` | `n_ctx` | `fits` | `n_ctx_missing` | `tokenizer_error`. `threshold==0` → `bound=threshold`, `use_full_corpus=False`.

- [ ] **Step 1: Failing tests**

```python
from app.full_corpus import decide_fit

QUESTION_RESERVE = 512
RESPONSE = 1800  # 1200 + 600 headroom, matches defaults


def test_threshold_zero_forces_retrieval():
    d = decide_fit(chunk_token_sum=10, prefix_tokens=20, n_ctx=16384, threshold=0, response_budget=RESPONSE)
    assert d.use_full_corpus is False and d.bound == "threshold"


def test_missing_n_ctx_is_not_a_fit():
    d = decide_fit(chunk_token_sum=10, prefix_tokens=20, n_ctx=None, threshold=32000, response_budget=RESPONSE)
    assert d.use_full_corpus is False and d.bound == "n_ctx_missing"


def test_n_ctx_binds_when_threshold_is_decorative():
    # 32000 > 16384 on this host: an archive under the knob can still miss the window.
    prefix = 14000
    d = decide_fit(
        chunk_token_sum=5000, prefix_tokens=prefix, n_ctx=16384, threshold=32000, response_budget=RESPONSE
    )
    assert d.use_full_corpus is False and d.bound == "n_ctx"
    assert d.effective_cap == 16384 - QUESTION_RESERVE - RESPONSE


def test_both_bounds_hold():
    d = decide_fit(chunk_token_sum=100, prefix_tokens=200, n_ctx=16384, threshold=32000, response_budget=RESPONSE)
    assert d.use_full_corpus is True and d.bound == "fits"


def test_threshold_binds_before_n_ctx():
    d = decide_fit(chunk_token_sum=40000, prefix_tokens=100, n_ctx=16384, threshold=32000, response_budget=RESPONSE)
    assert d.use_full_corpus is False and d.bound == "threshold"
```

- [ ] **Step 2: Run — expect FAIL** (`decide_fit` missing)

- [ ] **Step 3: Implement `decide_fit` + Settings field.** Log at INFO: `full_corpus bound=%s use=%s chunk_tokens=%s prefix_tokens=%s n_ctx=%s threshold=%s`. For `n_ctx_missing`, log WARN as well.

- [ ] **Step 4: Tests PASS.** Existing `Settings()` constructions still validate (new field has a default).

- [ ] **Step 5: Commit** `feat(ask): tvåbound grind för helarkivvägen med synlig bound`

---

### Task 3: Hits, `ask()` branch, prompt order, score contract

**Files:**
- Modify: `backend/app/full_corpus.py` (`hits_for_full_corpus`, `prefix_fingerprint`, `user_prompt`)
- Modify: `backend/app/answer.py`
- Modify: `backend/app/schemas.py` (`CitationOut.score: float | None` — no default)
- Modify: `xs_mobilapp/src/api/types.ts`, `kalla-native/src/api/types.ts` (`score: number | null`)
- Test: `backend/tests/test_full_corpus.py`

**Interfaces:**
- `hits_for_full_corpus(chunks, documents) -> list[RetrievalHit]` sorted by `(document_name, document_id, page, word_start, chunk_id)`; `score=confidence=bm25=dense=0.0`, `rerank_score=None`.
- `ask(..., corpus_runtime=None)`: if `decide_fit` says fits, skip search/rerank/legends, `_synthesize(..., low_relevance=False)`, user prompt `UTDRAG:\n{excerpts}\n\nFRÅGA: {question}`, `CitationOut.score=None`.
- Default `corpus_runtime`: `None` unless injected (or later a live `LlamaCppRuntime` when `BRF_LLM_BASE_URL` is set). **Existing tests pass no runtime → retrieval path unchanged.**

- [ ] **Step 1: Failing tests** (use a stub runtime with `n_ctx=16384` and `count = lambda t: max(1, len(t.split()))`)

```python
from app.answer import ask
from app.llm import FakeLLM
from app.store import Store
from tests.pdf_fixtures import build_pdf

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
    return st


def test_full_corpus_skips_search_and_puts_question_last(tmp_path, monkeypatch):
    st = _two_chunk_store(tmp_path)
    st.update_settings(st.settings.model_copy(update={"minRelevance": 1.0, "fullCorpusTokenThreshold": 32000}))
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
    # K-labels in prompt: one per chunk
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
    from pydantic import ValidationError
    from app.schemas import CitationOut
    with pytest.raises(ValidationError):
        CitationOut(
            document_id="d", document_name="n", page=1, quote="q",
            quotes=["q"], chunk_id="c", rects=[[0, 0, 1, 1]],
        )
```

Also assert `test_low_relevance_refuses_before_llm` in `test_answer.py` still passes without `corpus_runtime` (no silent switch).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement.** In `ask()`, after empty-index check: try fit; on fits, build hits, render excerpts, `_synthesize` with `low_relevance=False` and a path flag or a dedicated user-prompt helper. Do **not** feed zeros into `minRelevance`. When copying scores onto `CitationOut`, use `None` if `h.score == 0.0 and h.rerank_score is None and not retrieved_via_search` — cleaner: pass `from_retrieval: bool` into `_synthesize` or set a sentinel on hits. Prefer an explicit `full_corpus: bool` argument on `_synthesize` so legend-padding zeros on the retrieval path still copy as `0.0` (today’s behaviour).

- [ ] **Step 4: Tests PASS**, including `tests/test_answer.py::TestGates::test_low_relevance_refuses_before_llm`

- [ ] **Step 5: Commit** `feat(ask): helarkivväg med UTDRAG först och CitationOut.score null`

---

### Task 4: Prefix fingerprint stability

**Files:**
- Modify: `backend/app/full_corpus.py` (`prefix_fingerprint(system: str, excerpts: str) -> str`)
- Modify: `backend/app/answer.py` (INFO log when fingerprint changes per tenant)
- Test: `backend/tests/test_full_corpus.py`

- [ ] **Step 1: Failing tests**

```python
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
```

- [ ] **Step 2–4:** Implement hash of `system + excerpts`; log INFO `full_corpus prefix_changed tenant=%s` on change. Tests PASS.

- [ ] **Step 5: Commit** `test(ask): lås att helarkivprefixet är identiskt mellan frågor`

---

### Task 5: `cache_prompt` + timings log

**Files:**
- Modify: `backend/app/llm.py` (`OpenAICompatProvider.complete`)
- Test: `backend/tests/test_llm.py`

- [ ] **Step 1:** Extend the existing httpx MockTransport tests: the JSON body of `/chat/completions` must contain `"cache_prompt": true`. A 200 payload with `"timings": {"prompt_n": 10, "prompt_ms": 1, "cache_n": 9}` must be accepted (content still returned). Log those three fields at INFO.

- [ ] **Step 2:** Run `uv run pytest -q tests/test_llm.py -k cache_prompt -v` — FAIL

- [ ] **Step 3:** Add the field to the payload. If the server 400s on unknown `cache_prompt`, degrade once (same pattern as `response_format` / `reasoning_effort`). Still log `timings` when present.

- [ ] **Step 4:** Tests PASS. Do **not** treat a live `cache_n≈11` as success; that is a later measurement finding.

- [ ] **Step 5: Commit** `feat(llm): skicka cache_prompt och logga llama.cpp-timings`

Also update `DeterministicTestLLM` to find `FRÅGA:` after `UTDRAG:` as well as at the start:

```python
question_match = re.search(r"^FRÅGA:\s*(.*?)\n\nUTDRAG:", user, re.DOTALL)
if not question_match:
    question_match = re.search(r"\n\nFRÅGA:\s*(.*?)\Z", user, re.DOTALL)
```

Add a unit test with a UTDRAG-first user string (scripted provider still emits JSON).

---

### Task 6: Skip planner when the archive fits

**Files:**
- Modify: `backend/app/multihop.py`
- Test: `backend/tests/test_multihop.py` (new test)

- [ ] **Step 1:** Test that `ask_planned` with `corpus_runtime=StubRuntime()` on a tiny store does not call `plan_query`. Monkeypatch `app.multihop.plan_query` to raise if invoked. `ask_planned` must still return a synthesized `AskResponse` via `ask()`.

Thread `corpus_runtime` through `ask_planned(..., corpus_runtime=None)` into `ask`.

- [ ] **Step 2–4:** At the top of `ask_planned`, after empty-index, if fit → `return PlannedAnswer(ask(..., corpus_runtime=...), QueryPlan(mode="single", ...), pack)` without `plan_query`. Tests PASS.

- [ ] **Step 5: Commit** `feat(ask): hoppa över planeraren när hela arkivet ryms`

---

### Task 7: Measurement script, opt-in buckets, case diff

**Files:**
- Create: `backend/scripts/measure_corpus_tokens.py`
- Create: `backend/scripts/compare_ask_cases.py`
- Modify: `backend/scripts/reality/refusal_buckets.py`
- Test: `backend/tests/test_full_corpus.py`, `backend/tests/test_refusal_buckets.py`

**measure_corpus_tokens.py**
- `--folder` required. Each immediate subdirectory with PDFs = one association; if the folder itself contains PDFs (flat, like `DONT_PUSH_brf_stuff`), treat it as one association named after the folder.
- Ingest via `Store.add_document`. Tokenize `chunk.text` and `" ".join(w.text for w in page.words)` with the same `LlamaCppRuntime.count`.
- Stdout numbers only, e.g.

```
association documents pages chunks chunk_token_sum unique_tokens spill p50 p95 max
DONT_PUSH_brf_stuff 10 … …
```

- `install_network_audit`; hard-fail on non-loopback.

**refusal_buckets.py**
- Add `--prompt-chunks` (default off). Default path unchanged (`index.search` topK=6).
- Opt-in: use the same fit gate / all chunks that `ask()` would put in the prompt.
- When `--prompt-chunks` and an answer-bearing row exists: assert containment `retrieval_miss == 0` (exit non-zero otherwise). Locator miss (“no answer-bearing row in the document”) is not a gate failure.

**compare_ask_cases.py**
- Input: two JSON files from `annual_reports` (or a generic list of `{doc, qid, refused, n_citations, refusal_reason, elapsed_s}`).
- Output: one row per `(doc, qid)`: before → after. Print `verified_to_refused=N`. That N is the report headline. Also `refused_to_verified`. No new metric names.

- [ ] **Step 1:** Tests for: spill uses the same word-join; `--prompt-chunks` with all chunks containing the label row → bucket ≠ retrieval_miss; `compare_ask_cases` counts a verified→refused swap even when totals are equal.

- [ ] **Step 2–4:** Implement. Tests PASS.

- [ ] **Step 5: Commit** `feat(ask): tokenmätning, opt-in-rigg och falldiff före/efter`

---

### Task 8: Offline suite + live verification (this host)

Work in a git worktree if not already isolated (`using-git-worktrees`).

- [ ] **Step 1:** From repo root: `make test` (offline). Paste the summary. Fix regressions before claiming done.

- [ ] **Step 2:** Copy **PDFs only** from the laptop:

```bash
mkdir -p /home/simon/brfv2/DONT_PUSH_brf_stuff
rsync -av --include='*.pdf' --exclude='*' \
  aidev@linuxtop:/home/aidev/Projects/brfv2-local-archive-2026-08-05/repository-material/DONT_PUSH_brf_stuff/ \
  /home/simon/brfv2/DONT_PUSH_brf_stuff/
```

Do not copy `SUMMARIES` or markdown.

- [ ] **Step 3:** Token script with network audit. Save numeric stdout under gitignored `backend/out/`. Record `chunk_token_sum`, `unique_tokens`, spill, and whether `n_ctx` or `threshold` would bind.

- [ ] **Step 4:** Reality README runners **as they are** with `fullCorpusTokenThreshold=0` (retrieval), then again with the gate on, same docs and questions. `compare_ask_cases` on the two JSONs. Headline = verified→refused count.

- [ ] **Step 5:** Second question timings: log `prompt_n` / `cache_n` / `prompt_ms`. If `prompt_n` does not drop, write that this llama.cpp build has no working prefix cache (already observed on `b9976` with a 442-token shared prefix). Do not call that a success.

- [ ] **Step 6:** Opt-in `--prompt-chunks` on the full-corpus run: containment `retrieval_miss==0` where answer-bearing rows exist.

- [ ] **Step 7:** Final report (chat + numeric files only): files touched, per-association tokens, case-diff table, effective cap, what broke.

---

## Self-review vs spec

| Spec requirement | Task |
| --- | --- |
| `/props` n_ctx, not `/v1/models`; WARN if missing | 1 |
| Two bounds + log which bound | 2 |
| Same excerpt format; question last only on full-corpus | 3 |
| Bypass minRelevance; RetrievalHit zeros; CitationOut.score required None | 3 |
| Prefix hash tests | 4 |
| `cache_prompt` + empirical prompt_n | 5, 8 |
| Skip planner | 6 |
| Token script + unique/spill same join | 7 |
| refusal_buckets default unchanged; opt-in assert | 7 |
| Case diff, not totals | 7, 8 |
| Retrieval consumers documented | spec (no extra code except native 0.00 consequence) |
