"""Locks on the BRF-5 measurement harness itself.

Deliberately NOT locked here: "planned recall >= single recall". That is the
hypothesis the harness exists to TEST, and on the current corpus it is false
(see docs/evidence/crossdoc-fanout.md). Asserting it would turn a measurement
into a wish.

What is locked is that the harness can still measure: the golden cases'
required evidence must be retrievable at all, and the distractor padding must
actually make retrieval discriminate.
"""

import tempfile
from pathlib import Path

import pytest

from scripts.eval_crossdoc import (
    build_store,
    load_golden,
    measure,
    required_chunk_ids,
    single_evidence,
)


@pytest.fixture(scope="module")
def golden() -> dict:
    return load_golden()


def test_every_golden_needle_resolves_to_a_chunk(golden):
    """A `contains` needle that matches nothing would make its case's
    evidence requirement silently empty."""
    with tempfile.TemporaryDirectory() as tmp:
        store = build_store(golden, Path(tmp))
        for case in golden["cases"]:
            required = required_chunk_ids(store, case)
            assert len(required) == len(case.get("citations", [])), (
                f"{case['id']}: needle matchar fel antal chunkar"
            )


def test_required_evidence_is_reachable_at_default_settings(golden):
    """The ceiling check: a chunk that retrieval cannot surface can never be
    cited, so a golden case whose evidence is unreachable is untestable."""
    with tempfile.TemporaryDirectory() as tmp:
        store = build_store(golden, Path(tmp), distractors=20)
        report = measure(store, golden)
        assert report.scored, "inga poängsatta fall — mätningen vore verkningslös"
        for r in report.scored:
            assert r.planned_recall == 1.0, f"{r.id}: bevisunderlaget går inte att nå"


def test_distractors_actually_make_retrieval_choose(golden):
    """Guards the guard. Without padding, topK can reach the whole corpus and
    every strategy scores a perfect 1.00 while discriminating nothing — the
    first run of this harness did exactly that and looked like a success.

    (The bare corpus has since grown past topK on its own, so that specific
    assertion was dropped rather than kept as a stale tautology. The padding
    is still what makes the ratio large enough to measure under.)"""
    with tempfile.TemporaryDirectory() as tmp:
        padded = build_store(golden, Path(tmp), distractors=20)
        assert len(padded.chunks) > 3 * padded.settings.topK, (
            "för lite utfyllnad för att sökningen ska behöva välja"
        )
        # And the padding must be reachable-but-not-dominant: a real search
        # still returns exactly the budget, not the whole corpus.
        hits = single_evidence(padded, golden["cases"][0]["question"])
        assert len(hits) == padded.settings.topK
