"""Does the bounded fan-out actually find evidence a single search misses?

BRF-5, first measurable slice. `PER_QUERY_TOP_K` and `MAX_EVIDENCE_CHUNKS`
were reasoned, not measured — this harness turns them into numbers.

WHAT IS MEASURED: evidence recall. For each cross-document golden case, the
chunks that a correct answer must quote from are known (the golden citations
name them). We then ask, for each retrieval strategy, whether those chunks
reached the prompt at all. A chunk that never reaches the prompt cannot be
cited, so this is a hard ceiling on answer quality that no model can climb.

WHAT IS NOT MEASURED: answer quality. No LLM runs here. A case that scores
1.00 recall says the evidence was available, not that a model would use it
well. That is deliberate — this number must not move when a model changes.

    uv run python -m scripts.eval_crossdoc
    uv run python -m scripts.eval_crossdoc --sweep
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evidence import EvidencePack, expand_context  # noqa: E402
from app.multihop import MAX_EVIDENCE_CHUNKS, PER_QUERY_TOP_K  # noqa: E402
from app.schemas import Settings  # noqa: E402
from app.store import Store  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
GOLDEN_PATH = EVAL_DIR / "golden_crossdoc.json"


def load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text("utf-8"))


# A retrieval measurement is only meaningful when retrieval has to CHOOSE.
# The golden corpus alone is 4 documents of one chunk each; with the default
# topK=6 a single search returns the entire corpus and scores a perfect 1.00
# without discriminating at all. These distractors are plausible BRF material
# on neighbouring topics, so the index has to rank rather than enumerate.
DISTRACTOR_TOPICS = [
    ("Trivselregler.pdf", "Tvättstugan bokas via tavlan och städas efter varje pass av den boende."),
    ("Energideklaration.pdf", "Byggnadens energiprestanda uppgår till 118 kWh per kvadratmeter och år."),
    ("Brandskyddspolicy.pdf", "Systematiskt brandskyddsarbete följs upp av styrelsen två gånger per år."),
    ("Parkeringsavtal.pdf", "Parkeringsplats hyrs ut till medlem för 650 kr per månad med tre månaders uppsägning."),
    ("Stadgar.pdf", "Föreningen har till ändamål att i föreningens hus upplåta bostäder åt medlemmarna."),
    ("Arsredovisning2024.pdf", "Föreningens rörelseintäkter uppgick till 4820000 kr under räkenskapsåret."),
    ("Sophamtning.pdf", "Hämtning av hushållsavfall sker på tisdagar och matavfall på fredagar."),
    ("Ventilationsprotokoll.pdf", "Obligatorisk ventilationskontroll utfördes utan anmärkning i samtliga lägenheter."),
    ("Forsakringsbrev.pdf", "Fastighetsförsäkringen omfattar bostadsrättstillägg för samtliga lägenheter."),
    ("Tradgardsgrupp.pdf", "Trädgårdsgruppen ansvarar för planteringar och gemensamma arbetsdagar på våren."),
]


def _distractor_pages(count: int) -> list[tuple[str, list[str]]]:
    """`count` filler documents, each three lines of on-topic Swedish prose."""
    docs: list[tuple[str, list[str]]] = []
    for i in range(count):
        name, lead = DISTRACTOR_TOPICS[i % len(DISTRACTOR_TOPICS)]
        suffix = "" if i < len(DISTRACTOR_TOPICS) else f" (bilaga {i // len(DISTRACTOR_TOPICS) + 1})"
        docs.append((
            name.replace(".pdf", f"{suffix}.pdf") if suffix else name,
            [
                lead,
                f"Handlingen upprättades av styrelsen och arkiverades i föreningens pärm nummer {i + 3}.",
                "Frågor besvaras av styrelsen via föreningens ordinarie kontaktväg.",
            ],
        ))
    return docs


def build_store(
    golden: dict,
    data_dir: Path,
    settings: Settings | None = None,
    *,
    distractors: int = 0,
) -> Store:
    """The golden corpus, optionally padded with distractor documents."""
    # Imported lazily: pdf_fixtures lives under tests/, which is not a runtime
    # dependency of the app and must not be imported when this module is only
    # being introspected.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tests.pdf_fixtures import build_pdf

    store = Store(data_dir=data_dir)
    for doc in golden["corpus"]:
        lines = [(text, 72, 100 + 14 * i) for i, text in enumerate(doc["lines"])]
        store.add_document(doc["name"], build_pdf([lines]))
    for name, texts in _distractor_pages(distractors):
        lines = [(text, 72, 100 + 14 * i) for i, text in enumerate(texts)]
        store.add_document(name, build_pdf([lines]))
    store.update_settings(settings or Settings(minRelevance=0.05, topK=6))
    return store


def required_chunk_ids(store: Store, case: dict) -> set[str]:
    """The chunks a correct answer for this case must be able to quote from.

    Derived from the golden citations' `contains` needles — the same anchors
    the golden runner uses, so the measurement and the assertion agree on
    what "the evidence" means.
    """
    needed: set[str] = set()
    for citation in case.get("citations", []):
        needle = citation["contains"]
        match = next((cid for cid, c in store.chunks.items() if needle in c.text), None)
        if match is None:
            raise SystemExit(f"{case['id']}: ingen chunk innehåller {needle!r}")
        needed.add(match)
    return needed


def single_evidence(store: Store, question: str) -> set[str]:
    """What the unchanged single-search path would put in front of the model."""
    s = store.settings
    hits = store.index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=s.candidateCount,
        top_k=s.topK,
        min_confidence=0.0,
    )
    return {h.chunk_id for h in hits}


def planned_evidence(
    store: Store,
    case: dict,
    *,
    per_query_top_k: int = PER_QUERY_TOP_K,
    max_chunks: int = MAX_EVIDENCE_CHUNKS,
    expand: bool = True,
) -> set[str]:
    """What the planned fan-out puts in front of the model.

    Uses the case's own subqueries — the planner is not re-run, so this
    measures the RETRIEVAL strategy in isolation rather than the model's
    ability to write good subqueries. Those are separate failures and mixing
    them would make a regression unattributable.
    """
    s = store.settings
    pack = EvidencePack(question=case["question"])
    for i, sub in enumerate(case.get("subqueries", [])):
        hits = store.index.search(
            sub,
            weight=s.searchWeighting / 100.0,
            candidates=s.candidateCount,
            top_k=per_query_top_k,
            min_confidence=0.0,
        )
        pack.add_query(sub, hits, plan_index=i)
    if expand:
        room = max(0, max_chunks - len(pack.hits))
        if room:
            expand_context(pack, store.chunks, store.documents, max_added=room)
    return {h.chunk_id for h in pack.hits[:max_chunks]}


@dataclass
class CaseResult:
    id: str
    kind: str
    required: int
    single_found: int
    planned_found: int
    single_size: int
    planned_size: int

    @property
    def single_recall(self) -> float:
        return self.single_found / self.required if self.required else 1.0

    @property
    def planned_recall(self) -> float:
        return self.planned_found / self.required if self.required else 1.0


@dataclass
class Report:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def scored(self) -> list[CaseResult]:
        """Cases with required evidence. Clarify and no-evidence cases assert
        a REFUSAL, so 'recall' is not meaningful for them."""
        return [r for r in self.results if r.required > 0]

    def mean(self, attr: str) -> float:
        rows = self.scored
        return sum(getattr(r, attr) for r in rows) / len(rows) if rows else 0.0

    @property
    def mean_evidence_size(self) -> tuple[float, float]:
        rows = self.scored
        if not rows:
            return (0.0, 0.0)
        return (
            sum(r.single_size for r in rows) / len(rows),
            sum(r.planned_size for r in rows) / len(rows),
        )


def measure(
    store: Store,
    golden: dict,
    *,
    per_query_top_k: int = PER_QUERY_TOP_K,
    max_chunks: int = MAX_EVIDENCE_CHUNKS,
    expand: bool = True,
) -> Report:
    report = Report()
    for case in golden["cases"]:
        required = required_chunk_ids(store, case)
        if not required:
            report.results.append(CaseResult(case["id"], case["kind"], 0, 0, 0, 0, 0))
            continue
        single = single_evidence(store, case["question"])
        planned = planned_evidence(
            store, case, per_query_top_k=per_query_top_k, max_chunks=max_chunks, expand=expand
        )
        report.results.append(
            CaseResult(
                id=case["id"],
                kind=case["kind"],
                required=len(required),
                single_found=len(required & single),
                planned_found=len(required & planned),
                single_size=len(single),
                planned_size=len(planned),
            )
        )
    return report


def _print(report: Report) -> None:
    print(f"{'fall':6} {'shape':32} {'krävs':>6} {'enkel':>7} {'planerad':>9} {'utdrag e/p':>12}")
    print("-" * 78)
    for r in report.results:
        if r.required == 0:
            print(f"{r.id:6} {r.kind:32} {'—':>6} {'(vägransfall)':>28}")
            continue
        flag = "  ←" if r.planned_found > r.single_found else ""
        print(
            f"{r.id:6} {r.kind:32} {r.required:>6} "
            f"{r.single_recall:>7.2f} {r.planned_recall:>9.2f} "
            f"{r.single_size:>5}/{r.planned_size:<6}{flag}"
        )
    s_size, p_size = report.mean_evidence_size
    print("-" * 78)
    print(
        f"{'medel':39} {'':>6} {report.mean('single_recall'):>7.2f} "
        f"{report.mean('planned_recall'):>9.2f} {s_size:>5.1f}/{p_size:<6.1f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Mät bevisrecall: enkel sökning vs planerad fan-out.")
    ap.add_argument("--sweep", action="store_true", help="svep PER_QUERY_TOP_K och expansion")
    ap.add_argument(
        "--distractors", type=int, default=20,
        help="antal utfyllnadsdokument (0 = bara golden-korpusen, där varje sökning "
             "returnerar allt och mätningen inte säger något)",
    )
    args = ap.parse_args()

    import tempfile

    golden = load_golden()
    with tempfile.TemporaryDirectory() as tmp:
        store = build_store(golden, Path(tmp), distractors=args.distractors)
        print(
            f"korpus: {len(store.documents)} dokument, {len(store.chunks)} chunkar "
            f"(topK={store.settings.topK})\n"
        )
        if not args.sweep:
            report = measure(store, golden)
            _print(report)
            return 0

        # Squeeze the prompt budget. The interesting question is not "who wins
        # when everything fits" — with a wide topK the whole corpus reaches
        # the model and both strategies trivially score 1.00. It is where each
        # one BREAKS as the budget tightens.
        print(f"{'budget':>7} {'enkel':>7} {'planerad':>9} {'utdrag e/p':>13}")
        print("-" * 40)
        for budget in (1, 2, 3, 4, 6, 8):
            store.update_settings(store.settings.model_copy(update={"topK": budget}))
            rep = measure(
                store, golden,
                # Give the planned path the SAME total prompt budget as the
                # single path — otherwise fan-out "wins" merely by being
                # allowed more excerpts, which proves nothing.
                per_query_top_k=max(1, budget // 2),
                max_chunks=budget,
            )
            s_size, p_size = rep.mean_evidence_size
            print(
                f"{budget:>7} {rep.mean('single_recall'):>7.2f} "
                f"{rep.mean('planned_recall'):>9.2f} {s_size:>5.1f}/{p_size:<7.1f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
