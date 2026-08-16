# n_ctx cost and document-level ask — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Gemma 4 12B long-context cost and quality with a three-depth needle (A), then add a third `ask()` path that packs whole documents only when the top-scoring document fits (B).

**Architecture:** A is scripts plus a pure haystack/recommendation module; it never changes tracked compose or product routing. B adds `document_ask.py` (score + pack) and a branch in `ask()` after gate A. Two-document live eval runs only at the n_ctx A recommended, after 16384 is restored.

**Tech Stack:** FastAPI backend, existing `LlamaCppRuntime` / FakeLLM / StubRuntime, llama.cpp docker on loopback, pytest, `scripts.compare_ask_cases`.

## Global Constraints

- Worktree: `/home/simon/brfv2/.worktrees/full-corpus-ask` on `feat/full-corpus-ask`. Do not edit `/home/simon/brfv2` (main).
- Spec: `docs/superpowers/specs/2026-08-16-nctx-cost-and-document-ask-design.md`.
- TDD: no production code without a failing test first (except the live GPU driver in Task 3/8/9 and evidence markdown).
- Tracked `/home/simon/llama-cpp/docker-compose.yml` is not edited. `-c` overrides are gitignored / `/tmp`. Always restore `-c 16384` in `finally`.
- `fullCorpusTokenThreshold=0` disables full-corpus **and** the document path.
- Top document does not fit → retrieval, never document #2. Log `bound=top_document_n_ctx`. Report `top_miss_rate`.
- Rank documents by `max_score`; also record `n_matching_chunks`. Do not rank by count or sum.
- Needle table (10/50/90%) decides useful n_ctx. Stadgar name/seat questions do not.
- Two-document live slice only at A’s recommended n_ctx, and only if stadgar+annual-report can pack. Otherwise write that packing is impossible.
- No non-loopback TCP. Nothing derived from a real PDF in git (numbers, synthetic canaries, anonymised `doc_01`).
- Code in English; user-facing strings and commit messages in Swedish.
- Retrieval path byte-for-byte when the new gates do not fire.

---

## File map

| File | Role |
| --- | --- |
| Create `backend/app/needle_haystack.py` | Canaries, overwrite-at-depth haystack, `recommend_nctx` |
| Create `backend/tests/test_nctx_cost.py` | Haystack depths + recommendation rules |
| Create `backend/scripts/measure_nctx_cost.py` | Docker `-c` override, VRAM/RAM, needle Qs, restore |
| Create `backend/app/document_ask.py` | `score_documents`, `pack_documents`, `hits_for_document_ids` |
| Create `backend/tests/test_document_ask.py` | Scorer, packer, `ask()` branch |
| Modify `backend/app/answer.py` | After gate A: wide search → pack → synthesize or retrieval |
| Modify `backend/app/multihop.py` | Skip planner when packer would pack |
| Modify `backend/tests/test_multihop.py` | Planner not called on document path |
| Create `backend/scripts/live_document_ask.py` | One-doc @ 16384 and two-doc @ recommended n_ctx |
| Create `docs/evidence/nctx-cost.md` | A numbers + recommendation (after Task 3) |
| Create `docs/evidence/document-ask.md` | B case tables (after Tasks 8–9) |

---

### Task 1: Needle haystack + n_ctx recommendation (pure)

**Files:**
- Create: `backend/app/needle_haystack.py`
- Test: `backend/tests/test_nctx_cost.py`

**Interfaces:**
- Produces: `CANARIES`, `build_haystack(*, target_tokens: int, count) -> tuple[str, list[dict]]`, `recommend_nctx(rows: list[dict]) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_nctx_cost.py
from app.needle_haystack import CANARIES, build_haystack, recommend_nctx


def _count(text: str) -> int:
    return len(text.split())


def test_canaries_overwrite_at_10_50_90_percent():
    hay, placements = build_haystack(target_tokens=1000, count=_count)
    assert _count(hay) == 1000
    by_marker = {p["marker"]: p for p in placements}
    for needle in CANARIES:
        p = by_marker[needle["marker"]]
        assert needle["code"] in hay
        assert abs(p["depth"] - needle["depth"]) <= 0.02
        prefix = hay[: hay.index(needle["code"])]
        assert abs(_count(prefix) / 1000 - needle["depth"]) <= 0.02


def test_recommend_smallest_that_hits_all_three_depths():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 10000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
    assert rec["reason"] == "smallest_all_depths"


def test_recommend_drops_larger_window_that_loses_90_percent():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 11000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
    assert 65536 in rec["discarded"]


def test_recommend_prefers_window_that_hits_all_three_over_smaller_that_misses_90():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 10000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 32768


def test_recommend_disqualifies_65536_with_under_1gib_free():
    rows = [
        {"n_ctx": 32768, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 9000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": True, "vram_full_mib": 12000, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 32768
    assert 65536 in rec["discarded"]


def test_recommend_ignores_nctx_that_did_not_start():
    rows = [
        {"n_ctx": 16384, "started": True, "stable": True, "hit_10": True, "hit_50": True, "hit_90": False, "vram_full_mib": 8000, "gpu_total_mib": 12282},
        {"n_ctx": 65536, "started": False, "stable": False, "hit_10": False, "hit_50": False, "hit_90": False, "vram_full_mib": None, "gpu_total_mib": 12282},
    ]
    rec = recommend_nctx(rows)
    assert rec["n_ctx"] == 16384
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/simon/brfv2/.worktrees/full-corpus-ask/backend && uv run pytest tests/test_nctx_cost.py -v`

Expected: FAIL with `ModuleNotFoundError: app.needle_haystack`

- [ ] **Step 3: Minimal implementation**

```python
# backend/app/needle_haystack.py
from __future__ import annotations

CANARIES = (
    {"depth": 0.10, "marker": "ALPHA", "code": "NEEDLE10-A7K3M2"},
    {"depth": 0.50, "marker": "MID", "code": "NEEDLE50-P9Q4W1"},
    {"depth": 0.90, "marker": "OMEGA", "code": "NEEDLE90-Z2R8C5"},
)
FILLER_WORD = "lorem"
GPU_FREE_MIN_MIB = 1024


def build_haystack(*, target_tokens: int, count) -> tuple[str, list[dict]]:
    if target_tokens < 32:
        raise ValueError("target_tokens too small")
    words = [FILLER_WORD] * target_tokens
    placements = []
    for needle in CANARIES:
        payload = f"Markor {needle['marker']} {needle['code']}".split()
        start = int(needle["depth"] * target_tokens)
        if start + len(payload) > target_tokens:
            start = target_tokens - len(payload)
        words[start : start + len(payload)] = payload
        prefix_words = words[:start]
        depth = len(prefix_words) / target_tokens
        placements.append({**needle, "start": start, "depth": depth})
    hay = " ".join(words)
    if count(hay) != target_tokens:
        raise RuntimeError("haystack token count drifted")
    return hay, placements


def recommend_nctx(rows: list[dict]) -> dict:
    discarded: list[int] = []
    alive = []
    for r in rows:
        if not r.get("started") or not r.get("stable"):
            discarded.append(r["n_ctx"])
            continue
        free = (r.get("gpu_total_mib") or 0) - (r.get("vram_full_mib") or 0)
        if r["n_ctx"] == 65536 and free < GPU_FREE_MIN_MIB:
            discarded.append(r["n_ctx"])
            continue
        alive.append(r)
    hit90 = [r for r in alive if r.get("hit_90")]
    if hit90:
        smallest_90 = min(r["n_ctx"] for r in hit90)
        kept = []
        for r in alive:
            if not r.get("hit_90") and r["n_ctx"] > smallest_90:
                discarded.append(r["n_ctx"])
            else:
                kept.append(r)
        alive = kept
    all_three = [r for r in alive if r.get("hit_10") and r.get("hit_50") and r.get("hit_90")]
    if all_three:
        chosen = min(all_three, key=lambda r: r["n_ctx"])
        return {"n_ctx": chosen["n_ctx"], "reason": "smallest_all_depths", "discarded": discarded}
    if not alive:
        return {"n_ctx": None, "reason": "none_started", "discarded": discarded}

    def depth_score(r: dict) -> tuple[int, int]:
        deepest = (1 if r.get("hit_10") else 0) + (2 if r.get("hit_50") else 0) + (4 if r.get("hit_90") else 0)
        return (deepest, -r["n_ctx"])

    chosen = max(alive, key=depth_score)
    return {"n_ctx": chosen["n_ctx"], "reason": "deepest_then_smallest", "discarded": discarded}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_nctx_cost.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/needle_haystack.py backend/tests/test_nctx_cost.py
git commit -m "$(cat <<'EOF'
feat(eval): nål vid 10/50/90 procent och n_ctx-rekommendation

EOF
)"
```

---

### Task 2: n_ctx cost script (restore-safe, loopback)

**Files:**
- Create: `backend/scripts/measure_nctx_cost.py`
- Test: add restore/override helpers tests in `tests/test_nctx_cost.py`

**Interfaces:**
- Consumes: `build_haystack`, `recommend_nctx`, `LlamaCppRuntime`
- Produces: JSON to gitignored `backend/out/nctx-cost/` (numbers only)

- [ ] **Step 1: Failing test for compose restore command and hit detection**

```python
from scripts.measure_nctx_cost import canary_hit, restore_compose_cmd, override_compose_cmd

def test_canary_hit_is_exact_substring():
    assert canary_hit("foo NEEDLE10-A7K3M2 bar", "NEEDLE10-A7K3M2") is True
    assert canary_hit("NEEDLE10-A7K3M2XXXX", "NEEDLE10-A7K3M2") is True
    assert canary_hit("NEEDLE50-P9Q4W1", "NEEDLE10-A7K3M2") is False

def test_restore_compose_cmd_has_no_override_file():
    cmd = restore_compose_cmd("/home/simon/llama-cpp")
    assert cmd == ["docker", "compose", "-f", "/home/simon/llama-cpp/docker-compose.yml", "up", "-d"]

def test_override_cmd_includes_tmp_file_and_nctx():
    cmd = override_compose_cmd("/home/simon/llama-cpp", "/tmp/llama-nctx.yml")
    assert cmd[:4] == ["docker", "compose", "-f", "/home/simon/llama-cpp/docker-compose.yml"]
    assert "/tmp/llama-nctx.yml" in cmd
```

- [ ] **Step 2: Run to verify fail**

`uv run pytest tests/test_nctx_cost.py::test_canary_hit_is_exact_substring tests/test_nctx_cost.py::test_restore_compose_cmd_has_no_override_file -v`

Expected: FAIL import

- [ ] **Step 3: Implement script module helpers + live `main()`**

`measure_nctx_cost.py` must:

- `install_network_audit()` from `scripts.eval`; hard-fail on non-loopback.
- N_CTXS = `(16384, 32768, 65536)`.
- Write override YAML to `/tmp/llama-nctx-override.yml` (not the repo). Copy every compose flag except `-c`.
- For each n_ctx: override → wait until `/props` n_ctx matches (timeout 180s) → `nvidia-smi` + `docker stats` loaded → build haystack with live `runtime.count` targeting `n_ctx - 256` → three chat completions (question last, `max_tokens=64`, `cache_prompt: true`) → record timings + hits → sleep 120s → tiny completion for `stable` → on failure record `started=False` and **still** continue to next after restore attempt.
- `finally` on the whole script: `restore_compose_cmd` and wait until `/props` n_ctx is 16384.
- Stdout: JSON numbers. No haystack text. Canary codes may appear as the expected codes (synthetic, not from PDFs).
- Call `recommend_nctx` and print `recommended_n_ctx`.
- `--dry-run` builds haystack with a stub count and prints target depths (for offline smoke). Live `main` requires `BRF_LLM_BASE_URL`.

Chat payload (loopback only):

```python
{
  "model": os.environ.get("BRF_LLM_MODEL", "gemma4:e12b"),
  "messages": [
    {"role": "system", "content": "Svara med enbart koden. Inget annat."},
    {"role": "user", "content": haystack + "\n\nFRÅGA: Vilken kod står vid markören ALPHA?"},
  ],
  "max_tokens": 64,
  "temperature": 0,
  "cache_prompt": True,
}
```

Questions: ALPHA, MID, OMEGA in that order. Hit = `canary_hit(completion, code)`.

VRAM: `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits`. RAM: `docker stats llama-server --no-stream --format {{.MemUsage}}`.

KV: GET `/slots`; if a byte/cache field exists, record it; else set `kv_full: null` and `kv_source: "vram_delta"`.

- [ ] **Step 4: pytest helpers pass**

`uv run pytest tests/test_nctx_cost.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/measure_nctx_cost.py backend/tests/test_nctx_cost.py
git commit -m "$(cat <<'EOF'
feat(eval): mät n_ctx-kostnad med nål och tvingad restore till 16384

EOF
)"
```

---

### Task 3: Run A on this host (live, then restore)

**Files:**
- Create: `docs/evidence/nctx-cost.md` (numbers only)
- Gitignored JSON: `backend/out/nctx-cost/run.json`

No production routing changes.

- [ ] **Step 1: Confirm current server is 16384**

```bash
curl -s http://127.0.0.1:8000/props | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['default_generation_settings']['n_ctx'])"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

- [ ] **Step 2: Run the script**

```bash
cd /home/simon/brfv2/.worktrees/full-corpus-ask/backend
BRF_LLM=selfhosted BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=gemma4:e12b \
  uv run python -m scripts.measure_nctx_cost --out out/nctx-cost
```

Timeout: this can take tens of minutes (three windows, 2 min stability each, long prefills). Do not skip the `finally` restore if a window OOMs.

- [ ] **Step 3: Verify restore**

`/props` n_ctx must be **16384**. If not, run restore compose manually and do not start B live work.

- [ ] **Step 4: Write `docs/evidence/nctx-cost.md`**

Include: started/stable per n_ctx; VRAM loaded/full; RAM; prompt_ms/prompt_n/cache_n for Q1; hit/miss at 10/50/90; `recommend_nctx` result and which rule fired. No haystack, no GPU dump beyond the table.

The **90% column** is the quality verdict. Do not mention stadgar questions as evidence.

- [ ] **Step 5: Commit evidence**

```bash
git add docs/evidence/nctx-cost.md
git commit -m "$(cat <<'EOF'
docs(eval): n_ctx-kostnad och nåltabell för gemma4:e12b

EOF
)"
```

Record the recommended n_ctx for Task 9 (environment: write `backend/out/nctx-cost/recommended.txt` gitignored, and the same number in the evidence file).

---

### Task 4: Document scorer (max + count)

**Files:**
- Create: `backend/app/document_ask.py`
- Test: `backend/tests/test_document_ask.py`

**Interfaces:**
- Produces: `DocumentScore(document_id, document_name, max_score, n_matching_chunks)`, `score_documents(hits: list[RetrievalHit]) -> list[DocumentScore]` sorted by `(-max_score, document_name, document_id)`

- [ ] **Step 1: Failing test**

```python
from app.document_ask import score_documents
from app.schemas import RetrievalHit

def _hit(doc, name, score, n=1, page=1):
    return RetrievalHit(
        chunk_id=f"{doc}-{n}", score=score, confidence=0.5, bm25=0.0, dense=0.0,
        document_id=doc, document_name=name, page=page, text="t", rerank_score=None,
    )

def test_score_documents_ranks_by_max_and_reports_counts():
    hits = [
        _hit("a", "A.pdf", 0.2, n=1),
        _hit("a", "A.pdf", 0.9, n=2),
        _hit("b", "B.pdf", 0.8, n=1),
        _hit("b", "B.pdf", 0.1, n=2),
        _hit("b", "B.pdf", 0.3, n=3),
    ]
    rows = score_documents(hits)
    assert [r.document_id for r in rows] == ["a", "b"]
    assert rows[0].max_score == 0.9 and rows[0].n_matching_chunks == 2
    assert rows[1].max_score == 0.8 and rows[1].n_matching_chunks == 3
```

- [ ] **Step 2: Run — expect FAIL import**

- [ ] **Step 3: Implement `score_documents` only**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(ask): dokumentpoäng som max fused och antal träffchunkar`

---

### Task 5: Packer — top must fit

**Files:**
- Modify: `backend/app/document_ask.py`
- Modify: `backend/app/full_corpus.py` or document_ask: `hits_for_document_ids`
- Test: `backend/tests/test_document_ask.py`

**Interfaces:**
- Consumes: `decide_fit` effective cap math (`prefix + 512 + response_budget <= n_ctx`)
- Produces: `PackDecision(use_documents: bool, bound: str, document_ids: list[str], scores: list[DocumentScore], prefix_tokens: int | None)`
- `pack_documents(*, scores, chunks, documents, runtime, system, n_ctx, response_budget, threshold) -> PackDecision`
- `MAX_FULL_DOCUMENTS = 3`

When `threshold==0` or `n_ctx is None`: `use_documents=False`, bound `threshold` / `n_ctx_missing`.

Prefix for a set of ids: `hits_for_full_corpus` on chunks filtered to those ids, then `_render_excerpts`, then `runtime.count(system + "\n\nUTDRAG:\n" + excerpts)`.

- [ ] **Step 1: Failing tests**

```python
from app.document_ask import pack_documents
from tests.test_full_corpus import StubRuntime
from app.schemas import RetrievalHit, Chunk, DocumentMeta

# Build two DocumentScore lists: top=huge, second=tiny.
# StubRuntime.count = len(split). Huge text → does not fit n_ctx=80.
# Assert use_documents is False and bound == "top_document_n_ctx"
# and document_ids == [].

# Second test: top=tiny, second=huge, third=tiny, n_ctx fits top+third but not +huge.
# Assert document_ids == [top, third], bound == "fits".
```

Use real `Store` + `build_pdf` if constructing Chunk maps by hand is brittle. Pattern from `test_full_corpus._two_chunk_store`:

```python
def test_top_too_large_does_not_pack_second(tmp_path):
    st = Store(data_dir=tmp_path)
    st.add_document("big.pdf", build_pdf([[("alpha " * 80, 72, 100)]]))
    st.add_document("small.pdf", build_pdf([[("beta only", 72, 100)]]))
    st.update_settings(st.settings.model_copy(update={"fullCorpusTokenThreshold": 32000}))
    scores = score_documents([
        RetrievalHit(chunk_id=next(c.id for c in st.chunks.values() if "alpha" in c.text),
                     score=1.0, confidence=1.0, bm25=1.0, dense=1.0,
                     document_id=next(c.document_id for c in st.chunks.values() if "alpha" in c.text),
                     document_name="big.pdf", page=1, text="alpha", rerank_score=None),
        RetrievalHit(chunk_id=next(c.id for c in st.chunks.values() if "beta" in c.text),
                     score=0.5, confidence=0.5, bm25=0.5, dense=0.5,
                     document_id=next(c.document_id for c in st.chunks.values() if "beta" in c.text),
                     document_name="small.pdf", page=1, text="beta", rerank_score=None),
    ])
    decision = pack_documents(
        scores=scores, chunks=st.chunks, documents=st.documents,
        runtime=StubRuntime(n=40), system="sys",
        n_ctx=40, response_budget=5, threshold=32000,
    )
    assert decision.use_documents is False
    assert decision.bound == "top_document_n_ctx"
    assert decision.document_ids == []
```

Tune `n_ctx` / word counts so the assertion holds with `count=len(split)`.

- [ ] **Step 2: FAIL** (pack_documents missing)

- [ ] **Step 3: Implement packer**

```python
def pack_documents(...) -> PackDecision:
    if threshold == 0:
        return PackDecision(False, "threshold", [], scores, None)
    if n_ctx is None:
        return PackDecision(False, "n_ctx_missing", [], scores, None)
    if not scores:
        return PackDecision(False, "no_hits", [], scores, None)
    packed: list[str] = []
    prefix_tokens = None
    for i, row in enumerate(scores):
        if len(packed) >= MAX_FULL_DOCUMENTS:
            break
        candidate = packed + [row.document_id]
        prefix_tokens = _prefix_tokens(candidate, ...)
        fits = prefix_tokens + QUESTION_RESERVE_TOKENS + response_budget <= n_ctx
        if i == 0 and not fits:
            return PackDecision(False, "top_document_n_ctx", [], scores, prefix_tokens)
        if fits:
            packed = candidate
        # else: skip this later document; do not unpack
    return PackDecision(True, "fits", packed, scores, prefix_tokens)
```

Log: `document_ask bound=%s n_docs=%s prefix_tokens=%s top_max=%s top_n_chunks=%s`

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(ask): packa hela dokument bara när toppdokumentet ryms`

---

### Task 6: `ask()` document branch

**Files:**
- Modify: `backend/app/answer.py`
- Test: `backend/tests/test_document_ask.py`

**Interfaces:**
- After `evaluate_full_corpus` returns non-fit (and not tokenizer None-with-error already handled), if `corpus_runtime` is set and threshold > 0: wide `index.search` (`top_k=len(chunks)`, `candidates=max(settings.candidateCount, len(chunks))`), `score_documents`, `pack_documents`. If `use_documents`: `_synthesize(..., low_relevance=False, full_corpus=True)` with `hits_for_document_ids`. Else fall through to existing retrieval (do **not** reuse the wide hit list as the prompt — today’s path must search at `topK`).

Wide search is extra work on the retrieval fallback. Acceptable. Do not pass wide hits into `_synthesize` on fallback.

- [ ] **Step 1: Failing tests**

```python
def test_document_path_puts_all_chunks_of_packed_docs_and_question_last(tmp_path):
    # two tiny docs, threshold=1 so archive misses gate A, n_ctx large
    # FakeLLM answers from K1
    # assert user starts with UTDRAG, FRÅGA last
    # assert len(retrieval) == len(chunks of packed docs)  # likely both
    # assert all citation.score is None

def test_threshold_zero_still_question_first(tmp_path):
    # same store, threshold=0
    # assert user.startswith("FRÅGA:")

def test_document_path_does_not_call_rerank(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("rerank must not run on document path")
    monkeypatch.setattr("app.answer.rerank_chunks", boom)
    # store with rerankEnabled True would raise earlier if reranker missing —
    # instead monkeypatch reranker_available True and rerank_chunks
    # Simpler: monkeypatch index.search to record top_k and assert document path
    # used wide top_k then packed without calling rerank_chunks.
```

Also: `test_full_corpus_still_wins_when_archive_fits` — existing two-chunk store + default threshold + StubRuntime 16384 still skips search (gate A). Keep `test_full_corpus.py` green.

- [ ] **Step 2: FAIL** (`ask` never packs)

- [ ] **Step 3: Wire `ask()`**

Reuse `_synthesize(..., full_corpus=True)` for score contract and prompt order. Log `ask_path=documents` vs `ask_path=retrieval bound=top_document_n_ctx`.

- [ ] **Step 4: PASS** `tests/test_document_ask.py tests/test_full_corpus.py`

- [ ] **Step 5: Commit** `feat(ask): dokumentväg mellan helarkiv och chunkretrieval`

---

### Task 7: Skip planner when the packer would pack

**Files:**
- Modify: `backend/app/multihop.py`
- Test: `backend/tests/test_multihop.py`

Extract a small helper used by both `ask` and `ask_planned` so planner skip and `ask` cannot disagree: e.g. `evaluate_document_path(store, chunks, documents, index, runtime) -> PackDecision | None` in `document_ask.py` (includes the wide search). `ask_planned` calls gate A first (existing), else this helper; if `use_documents`, call `ask()` (which will pack again — duplicate search is OK for v1) without `plan_query`.

- [ ] **Step 1: Failing test** (mirror `TestFullCorpusSkipsPlanner`)

```python
def test_ask_planned_skips_planner_when_top_document_fits(self, tmp_path, monkeypatch):
    # archive over threshold (three tiny docs, threshold=1), n_ctx large
    # monkeypatch plan_query to raise
    # ask_planned(..., corpus_runtime=StubRuntime())
    # assert single complete() call, UTDRAG first
```

- [ ] **Step 2: FAIL** (plan_query still called)

- [ ] **Step 3: Skip planner when packer.use_documents**

If top does not fit, `plan_query` **must** still run (do not skip). Add a negative test: huge top doc, `plan_query` is called (FakeLLM must include a plan JSON then an answer). Keep this test short: monkeypatch `plan_query` to a sentinel that records a call, then returns `QueryPlan(mode="single", subqueries=[question], degraded=False)`.

- [ ] **Step 4: PASS** `tests/test_multihop.py tests/test_document_ask.py`

- [ ] **Step 5: Commit** `feat(ask): hoppa över planeraren när dokumentvägen packar`

---

### Task 8: One-document live comparison at 16384

**Files:**
- Create: `backend/scripts/live_document_ask.py`
- Gitignored: `backend/out/document-ask/`
- Evidence (numbers): append later in Task 9’s `docs/evidence/document-ask.md` or write a stub section now

**Must run at installed 16384** (Task 3 restored it). Confirm `/props` first.

`--folder` required (the 10 PDFs). `--slice one-doc`. `threshold=0` vs default.

Questions (generic):

- q_name, q_seat, q_interest, q_solidity as in the spec.

Each case JSON fields: `qid`, `refused`, `refusal_reason`, `n_citations`, `elapsed_s`, `ask_path`, `bound`, `n_packed`, `top_document_kind` (`stadgar|annual_report|other` from filename heuristics: `Stadgar` → stadgar, `år`/`ars`/`års` → annual_report, else other — **do not write filenames into committed evidence**), `scores`: `[{kind, max_score, n_matching_chunks}, ...]` top 3.

`top_miss_rate` = count(bound==top_document_n_ctx) / n_cases.

Run `compare_ask_cases` overall, and a packed-only filter (cases where after `ask_path==documents`). Headline in evidence: packed-only `verified_to_refused`.

Network audit on. `BRF_EMBEDDER=hashed` is acceptable for this measurement if that was the previous live stadgar run; prefer the same embedder as production on this host (`model2vec` if weights exist). Match `live_stadgar.py`: hashed is OK if documented.

Log Q1 vs Q2 `prompt_n`/`cache_n` on a packed case (expect no collapse).

- [ ] **Step 1:** Implement script; no committed PDF text.

- [ ] **Step 2:** Run one-doc slice; write gitignored JSON.

- [ ] **Step 3:** Do not commit JSON. Commit script tests if any (optional: JSON shape unit test with fixtures, no PDFs).

```bash
git add backend/scripts/live_document_ask.py
git commit -m "$(cat <<'EOF'
feat(eval): livejämförelse för dokumentvägen per fall

EOF
)"
```

---

### Task 9: Two-document live slice at A’s n_ctx

**Depends on Task 3 recommendation.**

- [ ] **Step 1:** Read recommended n_ctx from `docs/evidence/nctx-cost.md`.

- [ ] **Step 2:** If recommended is 16384, or stadgar+one annual report prefix still exceeds effective cap: **do not** run a fake before/after. Write in evidence: packing two documents is impossible at recommended n_ctx; two-doc table omitted. Commit that finding. Stop this task.

- [ ] **Step 3:** If packing is possible: temporarily `-c` to recommended (same override helper as Task 2), wait `/props`, run `--slice two-doc` with `q_fund_vs_stadgar` and `q_notice_vs_meeting`, `threshold=0` vs default, then **restore 16384** in `finally`. Confirm `/props` is 16384.

- [ ] **Step 4:** Case table + packed-only headline + `top_miss_rate` + per-doc `max_score` / `n_matching_chunks`. Cache Q1 vs Q2 on document path.

- [ ] **Step 5:** Write `docs/evidence/document-ask.md` (both slices). Commit.

```bash
git add docs/evidence/document-ask.md
git commit -m "$(cat <<'EOF'
docs(eval): dokumentväg mot retrieval per fall

EOF
)"
```

---

### Task 10: Offline suite + restore check

- [ ] **Step 1:** `cd /home/simon/brfv2/.worktrees/full-corpus-ask && make test`

Expected: previous 1354+ new tests passed, 0 new failures.

- [ ] **Step 2:** `curl` `/props` n_ctx is 16384.

- [ ] **Step 3:** `uvx ruff@0.15.0 check --config ruff.toml backend/app/document_ask.py backend/app/needle_haystack.py backend/app/answer.py backend/app/multihop.py backend/scripts/measure_nctx_cost.py backend/scripts/live_document_ask.py`

- [ ] **Step 4:** If anything failed, fix with TDD; do not leave llama.cpp off 16384.

---

## Spec coverage

| Spec requirement | Task |
| --- | --- |
| Needle 10/50/90, hit = exact canary | 1, 2, 3 |
| n_ctx recommendation rules | 1, 3 |
| VRAM/RAM/prefill/stability | 2, 3 |
| Restore 16384 | 2, 3, 9, 10 |
| Rank by max_score, report n_matching_chunks | 4, 8 |
| Top miss → retrieval, never #2 | 5, 6 |
| `threshold=0` disables both new paths | 5, 6 |
| Gate A still wins when archive fits | 6 |
| Question last + score None on document path | 6 |
| Planner skip when packing | 7 |
| One-doc @ 16384 + top_miss_rate | 8 |
| Two-doc only at recommended n_ctx | 9 |
| No PDF-derived git content, loopback only | 2, 8, 9 |

## Execution notes

- A mutates the only GPU server. Do not parallelise Task 3 with anything that calls `:8000`.
- Do not run two write-capable agents on `answer.py` / `document_ask.py`.
- If 32768/65536 OOM, that row is `started=false`; still restore 16384 before continuing.
