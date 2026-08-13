"""Upptäcker en RIKTIG modell ordförrådsglappet — och hur ofta överutlöser den?

XS-62. `scripts/eval_crossdoc.py` kör fallens egna, handskrivna delfrågor och
kör ingen modell alls. Det är ett medvetet val: hämtning och planering ska
kunna fela var för sig. Följden är att allt vi vet om fan-outens värde gäller
HÄMTNINGSSTRATEGIN. Om en riktig modell väljer `multi` när frågan har ett
ordförrådsglapp, och om den skriver delfrågor som ÖVERSÄTTER till dokumentens
språk i stället för att hacka upp frågans egna ord, är omätt.

Tre tal per fall, över N körningar:

  1. bevisrecall när planerarens EGNA delfrågor används
  2. andelen körningar som valde `multi`
  3. antalet sökningar som faktiskt utfördes

Tal 3 är OBSERVERAT, inte härlett ur läget: `HybridIndex.search` räknas där
den anropas. En härledd siffra ("multi ⇒ 3 sökningar") hade missat att
`ask_planned` faller tillbaka på ytterligare en sökning när fan-outen inte gav
någon träff, vilket är precis den kostnad som är värd att se.

**`multi` är inte ett betyg.** Fan-out är neutral eller sämre på fyra av sex
golden-fall och kostar ett extra modellanrop plus tre sökningar
(docs/evidence/crossdoc-fanout.md). Överutlösning är en verklig regression.
Därför körs enkelsökningspopulationen ur `eval/golden.json` med som NEGATIVA
KONTROLLER, där en hög multi-andel är ett underkännande, inte ett resultat.

Mätningen är icke-deterministisk till sin natur och grindar aldrig CI: den har
ingen exit-kod som beror på siffrorna.

    BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
        uv run python -m scripts.eval_planner --runs 10
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.indexer import HybridIndex  # noqa: E402
from app.multihop import ask_planned  # noqa: E402
from app.query_plan import PLANNER_CONTRACT  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import fresh_store, golden_span, load_golden as load_golden_a  # noqa: E402
from scripts.eval_crossdoc import (  # noqa: E402
    build_store,
    load_golden as load_golden_crossdoc,
    required_chunk_ids,
    single_evidence,
)

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

# Kanonsvaret för syntessteget. Se PlannerOnlyProvider.
_CANNED_SYNTHESIS = '{"answer": "", "citations": [], "insufficient_data": true}'


# --------------------------------------------------------------------------
# Observerad sökräkning
# --------------------------------------------------------------------------

_local = threading.local()


def install_search_counter() -> None:
    """Räkna varje `HybridIndex.search` som sker under en mätkörning.

    Trådlokal och opt-in per körning: räknaren är avstängd (None) tills en
    körning nollställer den, så korpusbygge och baslinjesökningar inte
    smittar av sig på siffran.
    """
    original = HybridIndex.search

    def counting(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        n = getattr(_local, "searches", None)
        if n is not None:
            _local.searches = n + 1
        return original(self, *args, **kwargs)

    HybridIndex.search = counting  # type: ignore[method-assign]


class PlannerOnlyProvider:
    """Riktig modell för PLANERINGEN, kanonsvar för syntesen.

    XS-62 frågar vad planeraren beslutar och vad beslutet hämtar. Att låta
    modellen skriva svaret också hade kostat ett andra modellanrop per körning
    och blandat in svarskvalitet i en hämtningssiffra — samma sammanblandning
    som `eval_crossdoc.py` undviker genom att inte köra någon modell alls.

    Anropen skiljs på systemprompten, inte på ordningen: `plan_query` skickar
    `PLANNER_CONTRACT` ordagrant. En ordningsbaserad regel hade tyst börjat
    mäta fel anrop den dag någon la till ett modellanrop före planeringen.
    """

    name = "selfhosted"

    def __init__(self, inner) -> None:  # noqa: ANN001
        self._inner = inner
        self.model = getattr(inner, "model", "") or ""
        self.planner_calls = 0
        self.synthesis_calls = 0

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        if system == PLANNER_CONTRACT:
            self.planner_calls += 1
            return self._inner.complete(system, user, max_tokens=max_tokens, model=model)
        self.synthesis_calls += 1
        return _CANNED_SYNTHESIS


@dataclass
class Run:
    mode: str
    subqueries: list[str]
    searches: int
    retrieved: set[str]
    degraded: bool
    seconds: float


def one_run(store: Store, question: str, provider, *, catalogue_seed: int | None = None) -> Run:
    """En körning genom den RIKTIGA `ask_planned`.

    `catalogue_seed` blandar om dokumentkatalogens ordning innan planeringen.
    Ordningen är en verklig produktionsvariabel — `ask_planned` läser
    `documents.values()`, vars ordning följer uppladdningsordningen — och den
    är den enda variationskälla som finns kvar när avkodningen är girig
    (temperature=0). Utan den mäter N körningar av samma prompt ingenting.
    """
    if catalogue_seed is not None:
        keys = list(store.documents)
        random.Random(catalogue_seed).shuffle(keys)
        store.documents = {k: store.documents[k] for k in keys}

    p = PlannerOnlyProvider(provider)
    _local.searches = 0
    t0 = time.time()
    try:
        result = ask_planned(store, question, p)
    finally:
        searches = getattr(_local, "searches", 0)
        _local.searches = None
    elapsed = time.time() - t0

    # Icke-vakuositet: exakt ett planeraranrop per körning. Noll betyder att
    # planeringen aldrig kördes (tom korpus, degraderad väg) och att siffrorna
    # nedan då beskriver något annat än planeraren.
    if p.planner_calls != 1:
        raise SystemExit(
            f"planeraren anropades {p.planner_calls} gånger för {question!r} — "
            "mätningen mäter inte det den påstår"
        )

    return Run(
        mode=result.plan.mode,
        subqueries=list(result.plan.subqueries),
        searches=searches,
        retrieved={h.chunk_id for h in result.pack.hits},
        degraded=result.plan.degraded,
        seconds=elapsed,
    )


# --------------------------------------------------------------------------
# Fallmängderna
# --------------------------------------------------------------------------


@dataclass
class Case:
    id: str
    kind: str
    question: str
    required: set[str]
    # Hur `required` ska poängsättas. Tvärdokumentsfallen kräver ALLA ankare
    # (de ligger i olika handlingar och svaret behöver båda); golden.json:s
    # fall pekar ut ETT stycke, vars chunkar är alternativ till varandra.
    conjunctive: bool
    expect_mode: str
    baseline: float = 0.0
    baseline_size: int = 0

    def recall(self, retrieved: set[str]) -> float | None:
        if not self.required:
            return None
        found = self.required & retrieved
        if self.conjunctive:
            return len(found) / len(self.required)
        return 1.0 if found else 0.0


def crossdoc_cases(store: Store, golden: dict) -> list[Case]:
    cases = []
    for c in golden["cases"]:
        required = required_chunk_ids(store, c)
        case = Case(
            id=c["id"],
            kind=c["kind"],
            question=c["question"],
            required=required,
            conjunctive=True,
            expect_mode=c.get("expect_mode", ""),
        )
        single = single_evidence(store, case.question)
        case.baseline = case.recall(single) or 0.0
        case.baseline_size = len(single)
        cases.append(case)
    return cases


def negative_cases(store: Store, golden: dict, limit: int | None = None) -> list[Case]:
    """Enkelsökningspopulationen: en fråga, ett stycke, en handling.

    Här är `multi` inte en vinst utan en kostnad. Fallen kommer ur den golden
    som produkten redan mäts mot, inte ur en lista skriven för det här
    experimentet — annars hade urvalet kunnat väljas för att ge rätt svar.
    """
    cases: list[Case] = []
    rows = golden["answerable"][:limit] if limit is not None else golden["answerable"]
    for qa in rows:
        target = golden_span(store, qa)
        if target is None:
            print(f"  hoppar över {qa['id']}: golden-stycket går inte att lösa upp", file=sys.stderr)
            continue
        doc_id, page, (w0, w1) = target
        required = {
            cid
            for cid, c in store.chunks.items()
            if c.document_id == doc_id and c.page == page and c.word_start <= w1 and c.word_end >= w0
        }
        if not required:
            print(f"  hoppar över {qa['id']}: ingen chunk täcker stycket", file=sys.stderr)
            continue
        case = Case(
            id=qa["id"],
            kind="single_document",
            question=qa["question"],
            required=required,
            conjunctive=False,
            expect_mode="single",
        )
        single = single_evidence(store, case.question)
        case.baseline = case.recall(single) or 0.0
        case.baseline_size = len(single)
        cases.append(case)
    return cases


# --------------------------------------------------------------------------
# Mätning och rapport
# --------------------------------------------------------------------------


@dataclass
class CaseMeasurement:
    case: Case
    runs: list[Run] = field(default_factory=list)

    @property
    def multi_share(self) -> float:
        return sum(1 for r in self.runs if r.mode == "multi") / len(self.runs)

    @property
    def mode_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.runs:
            out[r.mode] = out.get(r.mode, 0) + 1
        return out

    @property
    def mean_searches(self) -> float:
        return statistics.fmean(r.searches for r in self.runs)

    @property
    def recalls(self) -> list[float]:
        return [v for v in (self.case.recall(r.retrieved) for r in self.runs) if v is not None]

    @property
    def mean_recall(self) -> float | None:
        rs = self.recalls
        return statistics.fmean(rs) if rs else None

    @property
    def recall_range(self) -> tuple[float, float] | None:
        rs = self.recalls
        return (min(rs), max(rs)) if rs else None

    @property
    def distinct_plans(self) -> int:
        return len({(r.mode, tuple(r.subqueries)) for r in self.runs})


def measure(
    store: Store,
    cases: list[Case],
    provider,
    *,
    runs: int,
    shuffle_catalogue: bool,
    label: str,
) -> list[CaseMeasurement]:
    out: list[CaseMeasurement] = []
    total = len(cases) * runs
    done = 0
    t0 = time.time()
    for case in cases:
        m = CaseMeasurement(case=case)
        for i in range(runs):
            m.runs.append(
                one_run(store, case.question, provider, catalogue_seed=i if shuffle_catalogue else None)
            )
            done += 1
        out.append(m)
        rate = (time.time() - t0) / max(done, 1)
        print(
            f"  [{label}] {case.id:5} {done:>4}/{total}  "
            f"multi {m.multi_share:.0%}  sökn {m.mean_searches:.1f}  "
            f"recall {'—' if m.mean_recall is None else f'{m.mean_recall:.2f}'}  "
            f"(~{rate * (total - done):.0f}s kvar)",
            file=sys.stderr,
        )
    return out


def print_table(title: str, note: str, measurements: list[CaseMeasurement], runs: int) -> None:
    print(f"\n### {title}\n")
    print(note + "\n")
    print("| fall | shape | förväntat | valda lägen | recall (planerarens delfrågor) | multi-andel | sökningar | recall (enkel, baslinje) | olika planer |")
    print("|---|---|---|---|---:|---:|---:|---:|---:|")
    for m in measurements:
        c = m.case
        recall = "—" if m.mean_recall is None else f"{m.mean_recall:.2f}"
        rng = m.recall_range
        if rng and rng[0] != rng[1]:
            recall += f" ({rng[0]:.2f}–{rng[1]:.2f})"
        baseline = "—" if not c.required else f"{c.baseline:.2f}"
        modes = " ".join(f"{k}×{v}" for k, v in sorted(m.mode_counts.items()))
        print(
            f"| {c.id} | {c.kind} | {c.expect_mode or '—'} | {modes} | {recall} | "
            f"{m.multi_share:.0%} | {m.mean_searches:.1f} | {baseline} | {m.distinct_plans} |"
        )

    scored = [m for m in measurements if m.mean_recall is not None]
    if scored:
        mean_recall = statistics.fmean(m.mean_recall for m in scored)  # type: ignore[misc]
        mean_baseline = statistics.fmean(m.case.baseline for m in scored)
    else:
        mean_recall = mean_baseline = 0.0
    print(
        f"| **medel** | | | | **{mean_recall:.2f}** | "
        f"**{statistics.fmean(m.multi_share for m in measurements):.0%}** | "
        f"**{statistics.fmean(m.mean_searches for m in measurements):.1f}** | "
        f"**{mean_baseline:.2f}** | |"
    )
    print(f"\n{runs} körningar per fall.")


def as_json(measurements: list[CaseMeasurement]) -> list[dict]:
    rows = []
    for m in measurements:
        rows.append(
            {
                "id": m.case.id,
                "kind": m.case.kind,
                "question": m.case.question,
                "expect_mode": m.case.expect_mode,
                "required_chunks": len(m.case.required),
                "conjunctive": m.case.conjunctive,
                "baseline_single_recall": round(m.case.baseline, 4),
                "runs": len(m.runs),
                "mode_counts": m.mode_counts,
                "multi_share": round(m.multi_share, 4),
                "mean_searches": round(m.mean_searches, 3),
                "mean_recall": None if m.mean_recall is None else round(m.mean_recall, 4),
                "recall_range": m.recall_range,
                "distinct_plans": m.distinct_plans,
                "plans": sorted({(r.mode, " | ".join(r.subqueries)) for r in m.runs}),
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Mät planeraren mot en riktig modell (XS-62).")
    ap.add_argument("--runs", type=int, default=10, help="körningar per fall (minst 8 för att se stabilitet)")
    ap.add_argument("--distractors", type=int, default=20, help="utfyllnadsdokument i tvärdokumentskorpusen")
    ap.add_argument("--negatives", type=int, default=None, help="antal negativa kontroller (default: alla)")
    ap.add_argument("--skip-negatives", action="store_true")
    ap.add_argument(
        "--catalogue",
        choices=("fixed", "shuffled", "both"),
        default="both",
        help="fixed = identisk prompt varje körning; shuffled = dokumentkatalogens ordning blandas",
    )
    ap.add_argument("--out", default=str(EVAL_DIR / "last_planner_run.json"))
    args = ap.parse_args()

    from app.llm import pick_provider

    provider = pick_provider()
    if provider.name in ("fake", "none"):
        print(
            f"Ingen riktig modell tillgänglig (provider={provider.name}). "
            "Sätt BRF_LLM_BASE_URL och BRF_LLM=selfhosted.",
            file=sys.stderr,
        )
        return 2

    install_search_counter()

    variants = ["fixed", "shuffled"] if args.catalogue == "both" else [args.catalogue]
    payload: dict = {
        "provider": provider.name,
        "model": getattr(provider, "model", "") or "(serverns default)",
        "runs_per_case": args.runs,
        "variants": {},
    }

    with tempfile.TemporaryDirectory() as tmp:
        golden_x = load_golden_crossdoc()
        store_x = build_store(golden_x, Path(tmp) / "crossdoc", distractors=args.distractors)
        cases_x = crossdoc_cases(store_x, golden_x)
        print(
            f"tvärdokumentskorpus: {len(store_x.documents)} dokument, {len(store_x.chunks)} chunkar, "
            f"{len(cases_x)} fall",
            file=sys.stderr,
        )

        store_n = None
        cases_n: list[Case] = []
        if not args.skip_negatives:
            golden_a = load_golden_a()
            store_n = fresh_store(golden=golden_a)
            cases_n = negative_cases(store_n, golden_a, limit=args.negatives)
            print(
                f"negativ kontrollkorpus: {len(store_n.documents)} dokument, "
                f"{len(store_n.chunks)} chunkar, {len(cases_n)} fall",
                file=sys.stderr,
            )

        for variant in variants:
            shuffled = variant == "shuffled"
            mx = measure(
                store_x, cases_x, provider,
                runs=args.runs, shuffle_catalogue=shuffled, label=f"tvär/{variant}",
            )
            mn: list[CaseMeasurement] = []
            if cases_n and store_n is not None:
                mn = measure(
                    store_n, cases_n, provider,
                    runs=args.runs, shuffle_catalogue=shuffled, label=f"neg/{variant}",
                )

            head = (
                "Identisk prompt varje körning."
                if not shuffled
                else "Dokumentkatalogens ordning blandas per körning (en verklig produktionsvariabel)."
            )
            print_table(
                f"Tvärdokumentsfall — katalog: {variant}",
                head + " `multi` är inte ett betyg; kolumnen visar vad planeraren valde.",
                mx, args.runs,
            )
            if mn:
                print_table(
                    f"Negativa kontroller (enkelsökningsfall ur golden.json) — katalog: {variant}",
                    head + " Här är en hög multi-andel en REGRESSION: frågan besvaras av en sökning.",
                    mn, args.runs,
                )
            payload["variants"][variant] = {
                "crossdoc": as_json(mx),
                "negative_controls": as_json(mn),
            }

    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    print(f"\nRådata → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
