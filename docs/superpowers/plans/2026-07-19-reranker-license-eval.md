# Licensable-Reranker Recovery Eval — Plan

> **For agentic workers:** small phase — one code task (TDD) + one controller-run measurement task.

**Goal:** Determine whether a commercially-licensed, self-hostable reranker recovers annual-report table rows as well as the CC-BY-NC jina model, by making the reranker model configurable and running the existing deterministic recovery harness across candidates.

## Global Constraints

- Invariant: reranking reorders *which* chunks reach the prompt only. `RetrievalHit.text` frozen; `citations.py`/`normalize.py`/verification byte-identical. Model swap changes ranking, never what can be cited.
- Default `BRF_RERANK_MODEL` = `jinaai/jina-reranker-v2-base-multilingual` (unchanged) — existing rerank-marked test + cached weights keep passing.
- Embedder pinned `hashed`, `BRF_ENRICH=0` for the comparison (reranker-only variable).
- Measurement offline (`HF_HUB_OFFLINE=1`, harness enforces `assert_zero_connections`); model weights download once, un-audited.
- Data discipline: committed evidence metrics-only; raw artifacts gitignored under `backend/out/reality/`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Make the reranker model configurable

**Files:** Modify `backend/app/rerank.py` (~line 25); Test `backend/tests/test_rerank.py`

- [ ] **Step 1: Write the failing test** — add to `backend/tests/test_rerank.py`:

```python
def test_model_name_is_env_configurable(monkeypatch):
    import importlib
    monkeypatch.setenv("BRF_RERANK_MODEL", "some-org/some-reranker")
    import app.rerank as rr
    importlib.reload(rr)
    assert rr.MODEL_NAME == "some-org/some-reranker"
    monkeypatch.delenv("BRF_RERANK_MODEL", raising=False)
    importlib.reload(rr)
    assert rr.MODEL_NAME == "jinaai/jina-reranker-v2-base-multilingual"  # default unchanged
```

- [ ] **Step 2: Run to verify it fails.** `cd backend && uv run pytest tests/test_rerank.py -k env_configurable -v` → FAIL (MODEL_NAME is a hardcoded literal).

- [ ] **Step 3: Implement** — in `backend/app/rerank.py`, replace the hardcoded literal:

```python
import os
...
MODEL_NAME = os.environ.get("BRF_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")
```

(Confirm `_load_model()` and `reranker_available()` already reference `MODEL_NAME` — they do; no other change needed.)

- [ ] **Step 4: Run to verify pass.** `cd backend && uv run pytest tests/test_rerank.py -v` → all pass (existing tests + the new one). If any test reloads `app.rerank` and leaves state, ensure the new test restores the default via `importlib.reload` (shown above).

- [ ] **Step 5: Commit.**
```bash
git add backend/app/rerank.py backend/tests/test_rerank.py
git commit -m "rerank: make cross-encoder model configurable via BRF_RERANK_MODEL (default unchanged)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Measure recovery across rerankers (controller-run)

**Files:** none (measurement). Produces `docs/evidence/reranker-license-eval.md`.

- [ ] **Step 1: Download + load-verify candidates** (network, one-time, un-audited):
```bash
cd backend
.venv/bin/python - <<'PY'
from sentence_transformers import CrossEncoder
for m in ["cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "BAAI/bge-reranker-v2-m3"]:
    ce = CrossEncoder(m, max_length=1024)
    s = ce.predict([("Hur stora var föreningens räntekostnader?", "Räntekostnader 1 234 567")])
    print(m, "OK", float(s[0]))
PY
```
If a model fails to load via `CrossEncoder`, record it and (clean lane) keep mmarco / (Chinese lane) substitute a comparable Apache-2.0 model, noting the substitution.

- [ ] **Step 2: Run the offline recovery comparison** (embedder hashed, enrichment off, audit 0):
```bash
cd backend
O=out/reality/reranker_eval; mkdir -p $O
BRF_ENRICH=0 BRF_RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 \
  .venv/bin/python -m scripts.reality.enrichment_recovery --rerank --out $O/mmarco.json
BRF_ENRICH=0 BRF_RERANK_MODEL=BAAI/bge-reranker-v2-m3 \
  .venv/bin/python -m scripts.reality.enrichment_recovery --rerank --out $O/bge.json
# jina + no-rerank already measured (out/reality/enrichment/rec_baseline_rerank.json = 16/17, rec_baseline.json = 10/17)
```
(PYTHONPATH=backend if invoking a /tmp script.) Record `in_topk`/17 per model and the per-case rank deltas vs jina.

- [ ] **Step 3: Regression check** — the rerank-marked real-model test still passes on the default (jina) model: `cd backend && uv run pytest tests/test_rerank.py -v`. Full suite green: `.venv/bin/python -m pytest -q`.

- [ ] **Step 4: Write `docs/evidence/reranker-license-eval.md`** (metrics-only): the recovery table (no-rerank / jina / mmarco / bge, in_topk/17 + notable per-case ranks), the provenance/licence of each, the interpretation (does the clean candidate dissolve the blocker? what ceiling does bge show?), the wrong-row caveat (out of scope, next phase), and reproduce commands. If the clean candidate underperforms, say so plainly and name the mdeberta fine-tune fork.

- [ ] **Step 5: Commit evidence + update NOTES/memory.**

---

## Self-Review

- Spec coverage: config change → Task 1; both candidates + jina/no-rerank comparison → Task 2 Step 2; provenance tradeoff + interpretation → Task 2 Step 4; invariant (no citation change) → Global Constraints + Task 1 (rerank.py only); guards/regression → Task 2 Step 3. ✓
- Placeholder scan: none. Type consistency: `BRF_RERANK_MODEL` / `MODEL_NAME` consistent. ✓
