"""Vad HÄMTAR fan-outen som en enkel sökning inte hämtar — och vad tappar den?

`eval_planner.py` säger att recall är oförändrad när planeraren överutlöser.
"Oförändrad recall" har lästs som "slöseri men ofarligt", och det är en slutsats
måttet inte kan bära: recall mäter om beviset FINNS i påsen, inte vad som ligger
bredvid det. Två helt olika saker ser likadana ut i den siffran:

  A) fan-outen hämtar samma chunkar som enkelsökningen — `multi` är då
     verkningslöst på fallet, men prompten är densamma;
  B) fan-outen hämtar ANDRA chunkar, som inte bär svaret, och tränger undan
     några av enkelsökningens — prompten blir en annan, och sämre.

Skillnaden avgör om överutlösning är en kostnad i sökningar eller en risk för
svaret. Den här mätningen skiljer dem åt, per fall:

  nya        chunkar i fan-outens påse som enkelsökningen inte hade
  nya∩svar   av dessa, de som faktiskt bär det golden-fallet kräver
  tappade    chunkar enkelsökningen hade och som fan-outen INTE tog med
  därav svar av dessa, de som bar svaret — mekanismen bakom en recallFÖRLUST

Kör den RIKTIGA `ask_planned` med den plan `eval_planner` redan spelat in i
`eval/last_planner_run.json`, så ingen hämtningskod dupliceras här. **Inga
modellanrop**: planen är skriptad och syntesen kanonsvarad, så mätningen kan
köras utan tunnel och utan att fastna på att planeraren väljer om.

Sista kolumnen prövar en KANDIDAT till efterhämtningsfilter — "släpp igenom bara
utdrag vars confidence når enkelsökningens egen toppträff". Den är inte
implementerad någonstans; kolumnen finns för att kandidaten ska kunna avfärdas
eller motiveras på en siffra i stället för på en känsla.

    cd backend && uv run python -m scripts.eval_fanout_delta

Förutsätter att `eval/last_planner_run.json` kommer från samma kodversion —
planen är en funktion av prompten, och prompten har ändrats flera gånger.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.multihop import ask_planned  # noqa: E402
from app.query_plan import PLANNER_CONTRACT  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import fresh_store, load_golden as load_golden_a  # noqa: E402
from scripts.eval_crossdoc import (  # noqa: E402
    build_store,
    load_golden as load_golden_crossdoc,
    single_evidence,
)
from scripts.eval_planner import Case, crossdoc_cases, negative_cases  # noqa: E402

RUN_JSON = Path(__file__).resolve().parent.parent / "eval" / "last_planner_run.json"
_CANNED_SYNTHESIS = '{"answer": "", "citations": [], "insufficient_data": true}'


class ScriptedPlan:
    """Planeraren svarar med den inspelade planen; syntesen kanonsvaras.

    Skiljer anropen på systemprompten, inte på ordningen — samma skäl som
    `eval_planner.PlannerOnlyProvider`: en ordningsregel hade tyst börjat mäta
    fel anrop den dag ett modellanrop lades till före planeringen.
    """

    name = "selfhosted"
    model = ""

    def __init__(self, plan: dict) -> None:
        self._plan = json.dumps(plan, ensure_ascii=False)

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        return self._plan if system == PLANNER_CONTRACT else _CANNED_SYNTHESIS


def measure(store: Store, case: Case, subqueries: list[str]) -> dict:
    result = ask_planned(store, case.question, ScriptedPlan({"mode": "multi", "subqueries": subqueries}))
    # Icke-vakuositet: om planen inte kom fram som `multi` mäter raden nedan
    # en enkel sökning mot sig själv och varje delta blir noll.
    if result.plan.mode != "multi":
        raise SystemExit(f"{case.id}: planen kom fram som {result.plan.mode!r}, inte multi")

    fanout = {h.chunk_id for h in result.pack.hits}
    single = single_evidence(store, case.question)
    confidence = {h.chunk_id: h.confidence for h in result.pack.hits}
    s = store.settings
    single_top = max(
        (h.confidence for h in store.index.search(
            case.question, weight=s.searchWeighting / 100.0, candidates=s.candidateCount,
            top_k=s.topK, min_confidence=0.0)),
        default=0.0,
    )
    new, lost = fanout - single, single - fanout
    return {
        "id": case.id,
        "pack": len(fanout),
        "single": len(single),
        "new": len(new),
        "new_useful": len(new & case.required),
        "lost": len(lost),
        "lost_useful": len(lost & case.required),
        "new_above_single_top": sum(1 for c in new if confidence.get(c, 0.0) >= single_top),
        "recall": case.recall(fanout),
        "baseline": case.baseline,
    }


def report(label: str, store: Store, cases: list[Case], rows: list[dict]) -> None:
    by_id = {r["id"]: r for r in rows}
    print(f"\n### {label}\n")
    print("| fall | påse | nya | nya∩svar | tappade | därav svar | recall | baslinje | överlever golv |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    totals = {k: 0 for k in ("new", "new_useful", "lost", "lost_useful", "new_above_single_top")}
    n = 0
    for case in cases:
        row = by_id.get(case.id)
        if not row or not row["mode_counts"].get("multi"):
            continue
        _, subs = row["plans"][0]
        m = measure(store, case, subs.split(" | "))
        n += 1
        for k in totals:
            totals[k] += m[k]
        recall = "—" if m["recall"] is None else f"{m['recall']:.2f}"
        print(
            f"| {m['id']} | {m['pack']} | {m['new']} | {m['new_useful']} | {m['lost']} | "
            f"{m['lost_useful']} | {recall} | {m['baseline']:.2f} | {m['new_above_single_top']} |"
        )
    if not n:
        print("| *(inga multi-fall i körningen)* | | | | | | | | |")
        return
    print(
        f"| **{n} fall** | | **{totals['new']}** | **{totals['new_useful']}** | "
        f"**{totals['lost']}** | **{totals['lost_useful']}** | | | **{totals['new_above_single_top']}** |"
    )


def main() -> int:
    if not RUN_JSON.exists():
        print(f"saknar {RUN_JSON} — kör scripts.eval_planner först", file=sys.stderr)
        return 2
    variants = json.loads(RUN_JSON.read_text("utf-8"))["variants"]
    v = variants.get("fixed") or next(iter(variants.values()))

    with tempfile.TemporaryDirectory() as tmp:
        golden_x = load_golden_crossdoc()
        store_x = build_store(golden_x, Path(tmp) / "crossdoc", distractors=20)
        report("Tvärdokumentsfall", store_x, crossdoc_cases(store_x, golden_x), v["crossdoc"])

        golden_a = load_golden_a()
        store_n = fresh_store(golden=golden_a)
        report("Negativa kontroller", store_n, negative_cases(store_n, golden_a), v["negative_controls"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
