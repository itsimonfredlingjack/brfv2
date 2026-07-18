"""Pin the readiness-verdict logic in scripts/model_readiness.py with fixed,
synthetic per-question rows — no real corpus, no LLM, matching this phase's
offline-only test discipline. The harness's actual end-to-end proof is its
own two self-tests (--selftest / --selftest-negative), documented in
docs/evidence/model-readiness.md; these tests pin `compute_verdict` alone,
the pure function the brief calls out for fixed-input unit coverage.
"""

from __future__ import annotations

from scripts.model_readiness import compute_verdict


def _row(
    qid: str,
    class_: str,
    *,
    case: str | None = None,
    refused: bool = False,
    n_citations: int = 1,
    n_rejected: int = 0,
) -> dict:
    return {
        "qid": qid,
        "class_": class_,
        "case": case,
        "refused": refused,
        "refusal_reason": "grounding_failed" if refused else None,
        "n_citations": n_citations,
        "citations_detail": [],
        "n_rejected": n_rejected,
        "rejected_reasons": ["quote_not_found"] * n_rejected,
    }


def _fragment(qid: str, case: str, **kw) -> dict:
    return _row(qid, "fragment", case=case, **kw)


def _prose(qid: str, **kw) -> dict:
    return _row(qid, "prose", **kw)


def _unanswerable(qid: str, **kw) -> dict:
    return _row(qid, "unanswerable", **kw)


class TestComputeVerdictReady:
    def test_all_fragments_answered_and_control_refuses_is_ready(self):
        rows = [
            _fragment("q09", "org_number"),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _prose("q01"),
            _prose("q02"),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is True
        assert reasons == []

    def test_prose_control_refusal_does_not_gate_the_verdict(self):
        # Prose controls are reported (per-question table) but are context
        # only — the brief's READY criterion covers fragment + unanswerable
        # classes exclusively.
        rows = [
            _fragment("q09", "org_number"),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _prose("q01", refused=True, n_citations=0),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is True
        assert reasons == []

    def test_rejected_citations_alongside_a_verified_one_still_reads_ready(self):
        # A fragment question can have rejected candidates (e.g. a duplicate
        # or malformed citation from the same LLM response) alongside the
        # ONE that verified — n_rejected does not gate the verdict, only
        # n_citations (the count already past citations.resolve_citation).
        rows = [
            _fragment("q09", "org_number", n_citations=1, n_rejected=2),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is True
        assert reasons == []


class TestComputeVerdictNotReady:
    def test_empty_row_list_is_not_ready_with_explicit_reasons(self):
        # A go/no-go gate must not read "no evidence of failure" as "evidence
        # of readiness" — empty input is NOT READY, with reasons naming what's
        # missing, not a silent vacuous pass.
        ready, reasons = compute_verdict([])
        assert ready is False
        assert len(reasons) == 2
        joined = " ".join(reasons)
        assert "fragment-fact" in joined
        assert "obesvarbar kontrollfråga" in joined

    def test_fragment_less_input_is_not_ready_even_if_unanswerable_control_refuses(self):
        rows = [
            _prose("q01"),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert any("fragment-fact" in r for r in reasons)

    def test_missing_unanswerable_control_is_not_ready_even_if_all_fragments_pass(self):
        rows = [
            _fragment("q09", "org_number"),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert any("obesvarbar kontrollfråga" in r for r in reasons)

    def test_one_refused_fragment_question_fails_the_verdict(self):
        rows = [
            _fragment("q09", "org_number", refused=True, n_citations=0),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert len(reasons) == 1
        assert "q09" in reasons[0]

    def test_answered_fragment_question_with_zero_citations_fails(self):
        # Structural edge case: not refused, but no verified citation landed
        # (e.g. every citation rejected under a warn/insufficientData path).
        rows = [
            _fragment("q09", "org_number", refused=False, n_citations=0),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _unanswerable("q11", refused=True, n_citations=0),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert "q09" in reasons[0]

    def test_unanswerable_control_answering_instead_of_refusing_fails(self):
        rows = [
            _fragment("q09", "org_number"),
            _fragment("q08", "party_name"),
            _fragment("q03", "cell_value"),
            _unanswerable("q11", refused=False, n_citations=1),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert len(reasons) == 1
        assert "q11" in reasons[0]

    def test_multiple_failures_are_all_reported(self):
        rows = [
            _fragment("q09", "org_number", refused=True, n_citations=0),
            _fragment("q08", "party_name", refused=True, n_citations=0),
            _fragment("q03", "cell_value"),
            _unanswerable("q11", refused=False, n_citations=1),
        ]
        ready, reasons = compute_verdict(rows)
        assert ready is False
        assert len(reasons) == 3
        joined = " ".join(reasons)
        assert "q09" in joined and "q08" in joined and "q11" in joined
        assert "q03" not in joined
