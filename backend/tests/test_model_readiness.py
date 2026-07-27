"""Pin the readiness-verdict logic in scripts/model_readiness.py with fixed,
synthetic per-question rows — no real corpus, no LLM, matching this phase's
offline-only test discipline. The harness's actual end-to-end proof is its
own two self-tests (--selftest / --selftest-negative), documented in
docs/evidence/model-readiness.md; these tests pin `compute_verdict` alone,
the pure function the brief calls out for fixed-input unit coverage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.model_readiness import build_run_metadata, compute_verdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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


class TestRunMetadata:
    """XS-36: a preserved model_readiness.json must self-attest which model,
    runtime and commit produced it — XS-35 could only tie the artifact to its
    commit via surrounding prose and the file's mtime.
    """

    ENV = {
        "BRF_LLM": "selfhosted",
        "BRF_LLM_MODEL": "gemma4:e12b",
        "BRF_LLM_RUNTIME_LABEL": "agenntserver",
        "BRF_EMBEDDER": "model2vec",
        "BRF_LLM_BASE_URL": "http://127.0.0.1:8000/v1",
    }

    def test_records_configured_identity_and_commit(self):
        meta = build_run_metadata(self.ENV, REPO_ROOT, datetime.now())
        assert meta["configured_model"] == "gemma4:e12b"
        assert meta["configured_runtime_label"] == "agenntserver"
        assert meta["configured_llm"] == "selfhosted"
        assert meta["embedder"] == "model2vec"
        # Real repo: a 40-char SHA and an explicit clean/dirty flag.
        assert isinstance(meta["commit"], str) and len(meta["commit"]) == 40
        assert meta["dirty"] in (True, False)

    def test_omits_base_url_so_the_artifact_carries_no_endpoint_topology(self):
        meta = build_run_metadata(self.ENV, REPO_ROOT, datetime.now())
        assert "http" not in json.dumps(meta)
        assert not any("base_url" in k for k in meta)

    def test_timestamp_is_utc_and_current(self):
        meta = build_run_metadata(self.ENV, REPO_ROOT, datetime.now())
        stamped = datetime.strptime(meta["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ")
        stamped = stamped.replace(tzinfo=timezone.utc)
        assert abs(datetime.now(timezone.utc) - stamped) < timedelta(minutes=5)

    def test_naive_and_aware_inputs_stamp_the_same_instant(self):
        # datetime.now() is naive; the run must still record true UTC rather
        # than silently labelling local wall-clock time as Zulu.
        now = datetime.now()
        naive = build_run_metadata(self.ENV, REPO_ROOT, now)["timestamp_utc"]
        aware = build_run_metadata(self.ENV, REPO_ROOT, now.astimezone())["timestamp_utc"]
        assert naive == aware

    def test_missing_env_degrades_to_empty_strings_not_crash(self):
        meta = build_run_metadata({}, REPO_ROOT, datetime.now())
        assert meta["configured_model"] == ""
        assert meta["configured_runtime_label"] == ""

    def test_non_repo_path_reports_unknown_commit_rather_than_failing(self, tmp_path):
        meta = build_run_metadata(self.ENV, tmp_path, datetime.now())
        assert meta["commit"] is None
        assert meta["dirty"] is None


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
