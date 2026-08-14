"""Blir SVARET sämre när fan-outen byter ut bevispåsen?

`eval_fanout_delta.py` visade att en överutlösande `multi` lägger till utdrag
som inte bär svaret och tränger undan några av enkelsökningens — 27 in och 18 ut
på de 12 kontrollfallen, noll av dem svarsbärande åt något håll. Recall ser
ingenting av det, och varje mätning hittills har kanonsvarat syntesen, så
**svarskvalitet under utbytt bevispåse har aldrig mätts**. Det är också varför
villkor B i docs/evidence/fan-out-mvp-beslut.md inte går att falsifiera som det
står.

Den här mätningen kör RIKTIG syntes två gånger per fall, på samma fråga och
samma korpus, och skiljer bara på vilken bevispåse modellen får se:

  baslinje   `answer.ask` — enkelsökningens topK, den oförändrade vägen
  fan-out    `multihop.ask_planned` med den plan `eval_planner` spelade in

Måttet är produktens EGET, från `scripts/eval.py`: citerade den rätt handling,
och pekar markeringen på rätt sida och ruta. Ingen ny poängskala uppfanns för
det här experimentet — en sådan hade kunnat väljas så att den ger rätt svar.

Avkodningen är girig, så en körning per påse är hela sanningen för den prompten;
skillnader mellan kolumnerna beror på bevispåsen och ingenting annat.

    cd backend
    ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan &      # OBS: -lan
    BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
        uv run python -m scripts.eval_fanout_answer

24 modellanrop, ett par minuter. Kör den inte parallellt med pytest-sviten.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import ask  # noqa: E402
from app.multihop import ask_planned  # noqa: E402
from app.query_plan import PLANNER_CONTRACT  # noqa: E402
from app.schemas import AskResponse  # noqa: E402
from app.store import Store  # noqa: E402
from scripts.eval import fresh_store, load_golden as load_golden_a, rect_match  # noqa: E402

RUN_JSON = Path(__file__).resolve().parent.parent / "eval" / "last_planner_run.json"


class Recorder:
    """Spelar in syntesanropets användarprompt utan att ändra på den.

    Icke-vakuositet: hela experimentet vilar på att de två vägarna visar
    modellen OLIKA utdrag. Gör de inte det jämför tabellen enkelvägen med sig
    själv, och "identiskt svar" betyder ingenting. Prompten observeras därför
    i stället för att antas.
    """

    def __init__(self, inner) -> None:  # noqa: ANN001
        self._inner = inner
        self.name = inner.name
        self.model = getattr(inner, "model", "") or ""
        self.user = ""

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        if system != PLANNER_CONTRACT:
            self.user = user
        return self._inner.complete(system, user, max_tokens=max_tokens, model=model)


class PlanFromRecord:
    """Inspelad plan till planeraren, RIKTIG modell till syntesen.

    Motsatsen till `eval_planner.PlannerOnlyProvider`, och av samma skäl:
    experimentet ska hålla planen fast och mäta svaret, inte tvärtom. Anropen
    skiljs på systemprompten, inte på ordningen.
    """

    def __init__(self, inner, plan: dict) -> None:  # noqa: ANN001
        self._inner = inner
        self._plan = json.dumps(plan, ensure_ascii=False)
        self.name = inner.name
        self.model = getattr(inner, "model", "") or ""
        self.synthesis_calls = 0
        self.user = ""

    def complete(self, system: str, user: str, *, max_tokens: int, model: str) -> str:
        if system == PLANNER_CONTRACT:
            return self._plan
        self.synthesis_calls += 1
        self.user = user
        return self._inner.complete(system, user, max_tokens=max_tokens, model=model)


def score(resp: AskResponse, qa: dict, doc_id: str | None) -> dict:
    """Produktens eget mått, ordagrant samma villkor som scripts/eval.py."""
    cited_correct_doc = correct_highlight = False
    for c in resp.citations:
        if c.document_id == doc_id:
            cited_correct_doc = True
            if c.page == qa["page"] and any(
                rect_match(cr, gr) for cr in c.rects for gr in qa["rects"]
            ):
                correct_highlight = True
    return {
        "answer": resp.answer.strip(),
        "refused": resp.refusal,
        "reason": resp.refusal_reason or "",
        "verified": len(resp.citations),
        "rejected": len(resp.rejected_citations),
        "doc": cited_correct_doc,
        "highlight": correct_highlight,
    }


def cell(s: dict) -> str:
    if s["refused"]:
        return f"VÄGRAN ({s['reason']})"
    marks = ("✓" if s["doc"] else "✗") + ("✓" if s["highlight"] else "✗")
    return f"{marks} {s['verified']}v/{s['rejected']}a"


def main() -> int:
    from app.llm import pick_provider

    provider = pick_provider()
    if provider.name in ("fake", "none"):
        print(f"Ingen riktig modell (provider={provider.name}).", file=sys.stderr)
        return 2
    if not RUN_JSON.exists():
        print(f"saknar {RUN_JSON} — kör scripts.eval_planner först", file=sys.stderr)
        return 2

    variants = json.loads(RUN_JSON.read_text("utf-8"))["variants"]
    v = variants.get("fixed") or next(iter(variants.values()))
    planned = {r["id"]: r for r in v["negative_controls"] if r["mode_counts"].get("multi")}

    golden = load_golden_a()
    store: Store = fresh_store(golden=golden)
    by_name = {m.name: m.id for m in store.documents.values()}
    cases = [qa for qa in golden["answerable"] if qa["id"] in planned]
    if not cases:
        print("inga överutlösande fall i körningen — ingenting att mäta", file=sys.stderr)
        return 1

    print("\n### Svarskvalitet: enkelsökningens påse mot fan-outens\n")
    print("Kolumnerna är `dokument`/`markering` följt av verifierade/avvisade citat.\n")
    print("| fall | utdrag i prompten | baslinje (enkel) | fan-out | måttet | texten |")
    print("|---|---|---|---|---|---|")

    totals = {"base_doc": 0, "fan_doc": 0, "base_hl": 0, "fan_hl": 0, "base_ref": 0, "fan_ref": 0}
    changed = text_changed = 0
    for qa in cases:
        doc_id = by_name.get(qa["document"])
        rec = Recorder(provider)
        base = score(ask(store, qa["question"], rec), qa, doc_id)

        subqueries = planned[qa["id"]]["plans"][0][1].split(" | ")
        p = PlanFromRecord(provider, {"mode": "multi", "subqueries": subqueries})
        result = ask_planned(store, qa["question"], p)
        # Icke-vakuositet: om planen inte kom fram som `multi`, eller om
        # syntesen aldrig kördes, jämför tabellen enkelvägen med sig själv.
        if result.plan.mode != "multi":
            raise SystemExit(f"{qa['id']}: planen kom fram som {result.plan.mode!r}")
        if p.synthesis_calls != 1 and not result.response.refusal:
            raise SystemExit(f"{qa['id']}: {p.synthesis_calls} syntesanrop — mätningen mäter inte svaret")
        if rec.user and p.user and rec.user == p.user:
            raise SystemExit(
                f"{qa['id']}: de två vägarna skickade IDENTISK prompt — mätningen "
                "jämför enkelvägen med sig själv och säger ingenting om bevispåsen"
            )
        excerpts = (rec.user.count("\n["), p.user.count("\n["))
        fan = score(result.response, qa, doc_id)

        for key, s in (("base", base), ("fan", fan)):
            totals[f"{key}_doc"] += s["doc"]
            totals[f"{key}_hl"] += s["highlight"]
            totals[f"{key}_ref"] += s["refused"]
        delta = "" if cell(base) == cell(fan) else "**ändrat**"
        changed += bool(delta)
        # Skiljer "påsen spelade ingen roll" från "måttet ser inte skillnaden":
        # bytte prompten svarstexten alls?
        same_text = base["answer"] == fan["answer"]
        text_changed += not same_text
        if same_text:
            text = "identisk"
        else:
            text = f"{len(base['answer'])}→{len(fan['answer'])} tecken"
        print(f"| {qa['id']} | {excerpts[0]} → {excerpts[1]} | {cell(base)} | {cell(fan)} | "
              f"{delta or 'lika'} | {text} |")

    n = len(cases)
    print(
        f"| **{n} fall** | | {totals['base_doc']} dok / {totals['base_hl']} mark / "
        f"{totals['base_ref']} vägran | {totals['fan_doc']} dok / {totals['fan_hl']} mark / "
        f"{totals['fan_ref']} vägran | {changed} ändrade | {text_changed} olika text |"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
