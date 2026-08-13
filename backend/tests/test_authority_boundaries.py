"""BRF-5: authority- och säkerhetskriterier för BRF-1 (XS-61).

Jira BRF-5 beställer uttryckliga acceptanskriterier för de gränser den
planerade tvärdokumentsvägen inte får försvaga. Det här är filen där de bor:
kriteriet står i klassens docstring och testet under den ÄR kriteriet.

Varför en testfil och inte ett dokument: ett kriterium vars enda stöd är
"koden ser rätt ut" räknas inte som uppfyllt (XS-61). Flera av gränserna
nedan hölls redan i praktiken innan den här filen fanns — men härlett ur
kodläsning, inte bevisat av något som skulle fela om gränsen bröts.

Vakuositet är den återkommande felmoden i det här arbetet, så varje lås här
är brutet på riktigt och sett fela; körningarna ligger i
docs/evidence/authority-boundaries.md. Två fällor som styrde utformningen:

  * **Det lånade canary-testet.** "Fråga i förening A returnerar inte A:s
    hemlighet ur B" är VAKUÖST i den här arkitekturen. Varje tenant har sin
    egen `Store` med sitt eget `HybridIndex`; det finns inget delat index att
    läcka igenom, så assertionen hade varit grön oavsett isolering. Den
    egenskap som faktiskt kan gå sönder är *store-upplösningen* — kan något
    klientstyrt fält peka ut en annan förening? Det är vad K1 låser.
  * **Grinden som aldrig prövades.** Ett skrivlås mot ett tomt träd, eller
    mot en fråga som föll tillbaka till enkelsökning, bevisar ingenting. K5
    hävdar därför först att korpusen finns, att planen blev `multi` och att
    bevis nådde prompten — och mäter skrivningar först sedan.

Kriterier som redan bevisas av befintliga tester citeras vid namn i stället
för att skrivas om (K3, K4, K7).
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from app.llm import FakeLLM
from app.multihop import ask_planned
from app.schemas import AskRequest, AskResponse, Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf

AVTAL = [
    ("Snöröjningsavtalet gäller från 1 oktober 2025 till 30 september 2026.", 72, 100),
    ("Leverantör är Vinterservice AB med organisationsnummer 556677-8899.", 72, 114),
    ("Ersättning utgår med 1250 kr per påbörjad timme.", 72, 128),
]
PROTOKOLL = [
    ("Styrelsen beslutade att godkänna snöröjningsavtalet vid mötet.", 72, 100),
    ("Beslutet fattades enhälligt av en styrelse på sju ledamöter.", 72, 114),
    ("Ordföranden fick i uppdrag att underteckna handlingen.", 72, 128),
]


@pytest.fixture()
def store(tmp_path) -> Store:
    st = Store(data_dir=tmp_path)
    st.add_document("Snöröjningsavtal.pdf", build_pdf([AVTAL]))
    st.add_document("Styrelseprotokoll.pdf", build_pdf([PROTOKOLL]))
    st.update_settings(Settings(minRelevance=0.05, topK=3))
    return st


def _multi_plan(subqueries: list[str]) -> dict:
    return {"mode": "multi", "clarification": "", "subqueries": subqueries}


def _chunk_id_containing(store: Store, needle: str) -> str:
    for cid, chunk in store.chunks.items():
        if needle in chunk.text:
            return cid
    raise AssertionError(f"ingen chunk innehåller {needle!r}")


# ---------- K1: strukturell tenant-isolering ----------


class TestK1TenantIsolationIsStructural:
    """K1 — Ingen klientstyrd inmatning får avgöra VILKEN förenings handlingar
    den planerade vägen läser.

    Isoleringen ärvs: `api_ask` löser upp exakt en `Store` ur sökvägens
    `brf_id` plus medlemskapet, och `ask_planned` läser bara den. Det som kan
    gå sönder är inte indexet — det är att någon adderar ett fält eller en
    parameter som gör tenantvalet klientstyrt.
    """

    def test_ask_planned_takes_a_store_not_a_tenant_identifier(self):
        """En identifierarparameter vore en andra väg till en förening,
        vid sidan av den upplösta storen. Det finns ingen."""
        params = inspect.signature(ask_planned).parameters
        assert "store" in params
        forbidden = {"brf_id", "tenant", "tenant_id", "brf", "data_dir", "data_root"}
        assert not (forbidden & set(params)), (
            f"ask_planned tog en tenantidentifierare: {sorted(forbidden & set(params))} — "
            "isoleringen ska ärvas genom den redan upplösta storen, inte väljas om här."
        )

    def test_ask_request_carries_no_tenant_selecting_field(self):
        """Frusen fältmängd. Ett nytt fält på förfrågan är inte i sig fel —
        men ett som pekar ut en förening är det, och den här assertionen
        tvingar fram beslutet i stället för att låta det glida igenom."""
        assert set(AskRequest.model_fields) == {"question", "planned"}, (
            "AskRequest har ändrat form — kontrollera att inget nytt fält kan "
            "styra vilken förenings handlingar som läses, och uppdatera sedan låset."
        )

    def test_cross_tenant_planned_ask_is_refused_before_any_inference(
        self, two_tenant_app, monkeypatch
    ):
        """Den starkaste av de tre: en medlem i A som ber om B:s handlingar
        med den planerade vägen påslagen ska avvisas INNAN någon modell ser
        frågan. Fångar en refaktorering som planerar först och auktoriserar
        sedan — då hade B:s fråga nått inferens på A:s vägnar."""
        monkeypatch.setenv("BRF_PLANNED_ASK", "1")
        stub = FakeLLM([])
        monkeypatch.setattr("app.llm.pick_provider", lambda: stub)
        monkeypatch.setattr("app.answer.pick_provider", lambda: stub)
        monkeypatch.setattr("app.multihop.pick_provider", lambda: stub)

        r = two_tenant_app.client.post(
            "/api/brf/brf-b/ask",
            json={"question": "Vad är den hemliga koden?", "planned": True},
            headers=two_tenant_app.admin_a_headers,
        )

        assert r.status_code == 404, "okänd förening ska ge 404, aldrig 403 (id får inte gå att sondera)"
        assert two_tenant_app.secret_b not in r.text
        assert stub.calls == [], "frågan nådde en modell trots att medlemskapet saknades"


# ---------- K2: suverän inferens ----------


class TestK2SovereignInference:
    """K2 — Den planerade vägen får inte införa en andra inferensväg.

    Adressvalideringen (bara loopback eller adress i det egna nätet, inga
    domännamn) ligger i `app/model_endpoint.py` och bevisas av
    `tests/test_model_endpoint.py`. Den täcker VILKEN endpoint som är
    tillåten. Vad den inte täcker är om BRF-1 tyst skaffade sig en egen:
    planeraren är ett extra modellanrop, och ett anrop som löser upp sin egen
    leverantör kan gå någon annanstans än svaret gör.
    """

    def test_planning_and_synthesis_share_one_resolved_provider(self, store, monkeypatch):
        calls = {"n": 0}
        fake = FakeLLM([
            _multi_plan(["leverantör snöröjning", "styrelsens beslut"]),
            {
                "answer": "Vinterservice AB.",
                "citations": [
                    {
                        "chunk_id": _chunk_id_containing(store, "Vinterservice AB"),
                        "quote": "Leverantör är Vinterservice AB",
                    }
                ],
                "insufficient_data": False,
            },
        ])

        def _counted():
            calls["n"] += 1
            return fake

        monkeypatch.setattr("app.multihop.pick_provider", _counted)
        monkeypatch.setattr("app.answer.pick_provider", _counted)

        ask_planned(store, "Vem är leverantör och godkände styrelsen avtalet?")

        assert len(fake.calls) == 2, "förväntade planeringsanrop + syntesanrop"
        assert calls["n"] == 1, (
            f"leverantören löstes upp {calls['n']} gånger — planering och syntes ska dela "
            "en och samma redan upplösta leverantör, annars kan de tala med olika endpoints."
        )


# ---------- K5: ingen modellauktoritet över pengar eller externa skrivningar ----------


def _tree_manifest(root: Path) -> dict[str, str]:
    """Innehållshash per fil under `root`. Storlek och mtime räcker inte —
    en skrivning som råkar behålla längden vore osynlig."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


class TestK5AskingIsReadOnly:
    """K5 — Att ställa en fråga får aldrig ändra något som finns kvar efteråt.

    Det är gränsen mot BRF-2 uttryckt som en mätbar egenskap. `multihop.py`
    hävdar i sin docstring "no persistent memory, and no state that outlives
    the request"; det här är påståendet som ett lås. Det skulle fela på ett
    svarscache, en frågelogg på disk, eller ett "lärt" minne mellan frågor —
    alltså på precis det steg som skulle ge modellen auktoritet över annat än
    sitt eget svar.
    """

    def test_a_planned_multi_ask_leaves_the_tenant_tree_byte_identical(self, store, tmp_path):
        fake = FakeLLM([
            _multi_plan(["leverantör snöröjning", "styrelsens beslut", "ersättning timme"]),
            {
                "answer": "Vinterservice AB, godkänt av styrelsen.",
                "citations": [
                    {
                        "chunk_id": _chunk_id_containing(store, "Vinterservice AB"),
                        "quote": "Leverantör är Vinterservice AB",
                    }
                ],
                "insufficient_data": False,
            },
        ])

        before = _tree_manifest(tmp_path)
        result = ask_planned(store, "Vem är leverantör och godkände styrelsen avtalet?", provider=fake)
        after = _tree_manifest(tmp_path)

        # Icke-vakuositet: allt det här måste vara sant för att mätningen
        # efteråt ska betyda något.
        assert before, "inget skrevs någonsin till trädet — låset mäter ingenting"
        assert len(store.documents) == 2, "korpusen försvann; frågan gick mot tomt underlag"
        assert result.plan.mode == "multi", f"planen blev {result.plan.mode}, inte multi — fan-outen kördes aldrig"
        assert result.pack.hits, "inga bevischunkar nådde prompten — vägen kortslöts före skrivrisken"
        assert not result.response.refusal, "svaret vägrades; syntesen kördes inte hela vägen"

        assert after == before, (
            "att ställa en fråga ändrade beständigt tillstånd: "
            f"nya/ändrade {sorted(set(after) - set(before)) or [k for k in after if after[k] != before.get(k)]}, "
            f"borttagna {sorted(set(before) - set(after))}"
        )


# ---------- K6: mänskliga godkännandegränser ----------


class TestK6TheAskSurfaceStaysAdvisory:
    """K6 — BRF-1 får inte ge frågevägen någon handlingsförmåga.

    De befintliga godkännandegränserna (fakturor, inkommande post,
    integrationer) ligger orörda och bevisas där de bor — t.ex.
    `tests/test_intake_queue.py::test_monitor_creates_an_approved_watch_not_a_proposal`.
    Vad som är NYTT med BRF-1 är en väg som läser flera handlingar och
    syntetiserar över dem, och risken är att den växer en åtgärdskant:
    ett svarsfält som utlöser något, eller en endpoint bredvid `/ask`.
    """

    def test_ask_response_exposes_no_actionable_field(self):
        """Frusen fältmängd på svaret. Varje fält här är text, citat eller
        proveniens — inget av dem beordrar något."""
        assert set(AskResponse.model_fields) == {
            "answer", "refusal", "refusal_reason", "warning", "citations",
            "rejected_citations", "retrieval", "provider", "model", "clarification",
        }, (
            "AskResponse har ändrat form — kontrollera att inget nytt fält kan utlösa "
            "en åtgärd utan att en människa godkänt den, och uppdatera sedan låset."
        )

    def test_brf1_added_no_endpoint_beside_ask(self, two_tenant_app):
        """Den planerade vägen delar endpoint med den vanliga frågan; den har
        medvetet ingen egen. En ny rutt här vore en ny auktoriseringsyta."""
        paths = {
            r.path for r in two_tenant_app.client.app.routes if "ask" in getattr(r, "path", "")
        }
        assert paths == {"/api/brf/{brf_id}/ask"}, (
            f"frågeytan har växt: {sorted(paths)} — en ny rutt behöver eget grindbeslut."
        )
