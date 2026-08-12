"""Executes eval/golden_crossdoc.json — the cross-document golden cases.

The LLM is scripted (the plan, then the answer) because these cases assert
what the ORCHESTRATION does, not what a model happens to say: the plan shape,
the fan-out, and that every claimed citation survives the real, unchanged
verification against the real page words. Retrieval, `resolve_citation` and
the numeric gate are all genuine here.
"""

import json
from pathlib import Path

import pytest

from app.llm import FakeLLM
from app.multihop import ask_planned
from app.schemas import Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf

GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "eval" / "golden_crossdoc.json").read_text("utf-8"))
CASES = GOLDEN["cases"]


@pytest.fixture()
def store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    for doc in GOLDEN["corpus"]:
        lines = [(text, 72, 100 + 14 * i) for i, text in enumerate(doc["lines"])]
        st.add_document(doc["name"], build_pdf([lines]))
    st.update_settings(Settings(minRelevance=0.05, topK=3))
    return st


def _chunk_id_containing(store: Store, needle: str) -> str:
    for cid, chunk in store.chunks.items():
        if needle in chunk.text:
            return cid
    raise AssertionError(f"golden-fallet pekar på text som inte finns i korpusen: {needle!r}")


def _script(store: Store, case: dict) -> FakeLLM:
    if case["expect_mode"] == "clarify":
        return FakeLLM([{"mode": "clarify", "subqueries": [], "clarification": case["clarification"]}])
    return FakeLLM([
        {"mode": "multi", "clarification": "", "subqueries": case["subqueries"]},
        {
            "answer": case["answer"],
            "citations": [
                {"chunk_id": _chunk_id_containing(store, c["contains"]), "quote": c["quote"]}
                for c in case["citations"]
            ],
            "insufficient_data": False,
        },
    ])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_crossdoc_case(store, case):
    result = ask_planned(store, case["question"], provider=_script(store, case))

    assert result.plan.mode == case["expect_mode"], f"{case['id']}: fel planläge"

    if case["expect_mode"] == "clarify":
        assert result.response.refusal, f"{case['id']}: en tvetydig fråga får inte besvaras"
        assert result.response.citations == []
        assert result.response.answer.strip() == case["clarification"].strip()
        return

    assert not result.response.refusal, f"{case['id']}: {result.response.answer}"
    assert len(result.response.citations) >= case["expect_min_citations"], (
        f"{case['id']}: för få verifierade källhänvisningar"
    )
    # Every surviving citation was verified against the real page words.
    assert all(c.rects for c in result.response.citations), f"{case['id']}: källa utan sidkoordinater"

    cited_docs = {c.document_name for c in result.response.citations}
    assert set(case["expect_documents"]) <= cited_docs, (
        f"{case['id']}: svaret belades inte i alla väntade dokument — fick {cited_docs}"
    )
    assert len(cited_docs) >= 2, f"{case['id']}: detta är ett tvärdokumentfall"


def test_every_golden_kind_from_brf4_is_covered():
    """The three shapes this slice committed to."""
    assert {c["kind"] for c in CASES} == {
        "two_document_answer",
        "multi_part_question",
        "ambiguous_asks_for_clarification",
    }
