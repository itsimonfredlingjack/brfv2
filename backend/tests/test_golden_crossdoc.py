"""Executes eval/golden_crossdoc.json — the cross-document golden cases.

The LLM is scripted (the plan, then the answer) because these cases assert
what the ORCHESTRATION does, not what a model happens to say: the plan shape,
the fan-out, and that every claimed citation survives the real, unchanged
verification against the real page words. Retrieval, `resolve_citation` and
the numeric gate are all genuine here.
"""

import json
import re
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
            "insufficient_data": case.get("insufficient_data", False),
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

    if case.get("expect_refusal_reason"):
        # A negative case: fan-out widens RETRIEVAL, it must not lower the bar
        # for answering. No citations may survive, and no answer is shown.
        assert result.response.refusal, f"{case['id']}: borde ha vägrat"
        assert result.response.refusal_reason == case["expect_refusal_reason"]
        assert result.response.citations == []
        return

    assert not result.response.refusal, f"{case['id']}: {result.response.answer}"
    assert len(result.response.citations) >= case["expect_min_citations"], (
        f"{case['id']}: för få verifierade källhänvisningar"
    )
    # Every surviving citation was verified against the real page words.
    assert all(c.rects for c in result.response.citations), f"{case['id']}: källa utan sidkoordinater"

    for needle in case.get("expect_answer_contains", []):
        assert needle in result.response.answer, (
            f"{case['id']}: svaret saknar {needle!r} — en tidsbestämd fråga måste bära "
            "både beloppet och när det började gälla"
        )

    cited_docs = {c.document_name for c in result.response.citations}
    assert set(case["expect_documents"]) <= cited_docs, (
        f"{case['id']}: svaret belades inte i alla väntade dokument — fick {cited_docs}"
    )
    # Most cases here are cross-document, but not all: r01 turned out to be a
    # SINGLE-document question with a vocabulary gap once the real contract was
    # read. Fan-out's value is the gap, not the document count (see
    # docs/evidence/crossdoc-fanout.md), so a case may opt out rather than have
    # a second source invented for it.
    if case.get("expect_cross_document", True):
        assert len(cited_docs) >= 2, f"{case['id']}: detta är ett tvärdokumentfall"


def test_every_golden_kind_from_brf4_is_covered():
    """The shapes this slice committed to."""
    assert {c["kind"] for c in CASES} == {
        "two_document_answer",
        "multi_part_question",
        "ambiguous_asks_for_clarification",
        "conflicting_documents",
        "no_evidence_refuses",
        "time_bound_question",
        "vocabulary_gap",
    }


_MONTHS = (
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _is_temporal(needle: str) -> bool:
    """Does this condition name a POINT IN TIME rather than an amount?"""
    folded = needle.casefold()
    return any(m in folded for m in _MONTHS) or bool(_YEAR_RE.search(needle))


def test_time_bound_case_asserts_more_than_the_amount():
    """Guards the guard: a time-bound case that only checks the figure would
    pass on an answer that never says WHEN the figure started applying — the
    exact thing the case exists to test.

    The previous form asked only whether some condition contained a LETTER,
    which "1250 kr" satisfies. Split the conditions instead: at least one must
    name a time, at least one must not, or the case is not time-bound at all.
    """
    cases = [c for c in CASES if c["kind"] == "time_bound_question"]
    assert cases, "ingen tidsbestämd fråga i golden — vaktposten vaktar ingenting"
    for case in cases:
        needles = case["expect_answer_contains"]
        assert len(needles) >= 2, f"{case['id']}: ett enda villkor kan inte täcka både belopp och tidpunkt"
        assert any(_is_temporal(n) for n in needles), (
            f"{case['id']}: inget villkor gäller NÄR beloppet började gälla"
        )
        assert any(not _is_temporal(n) for n in needles), (
            f"{case['id']}: inget villkor gäller själva beloppet"
        )


def test_conflicting_cases_really_state_two_different_things():
    """Guards the guard: if both quotes named the same figure, the conflict
    case would pass while proving nothing about conflicting evidence.

    Every case of the kind, not `next(...)`: the first form guarded x03 and
    left r02 — the case built from a real board situation — unguarded.
    """
    cases = [c for c in CASES if c["kind"] == "conflicting_documents"]
    assert len(cases) >= 2, "vaktposten skrevs för flera motstridighetsfall"
    for case in cases:
        figures = {q["contains"] for q in case["citations"]}
        assert len(figures) == 2, f"{case['id']}: måste ange två OLIKA uppgifter"
        assert all(f in case["answer"] for f in figures), (
            f"{case['id']}: svaret måste visa båda uppgifterna"
        )
