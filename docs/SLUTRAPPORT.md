# Slutrapport — BRF Dokument-AI

**Datum:** 2026-07-28
**Granskad `main`-baslinje:** `37653d7679706edd5badd4fd7e8841c6b0f02d57`
**BP5-beslut:** `PASS BP5`, Simon, 2026-07-27
**BP6-rekommendation i den här rapporten:** `PASS BP6` (se §8 — beslutet är
Simons, inte agentens, per projektets granskningsprincip)

Källor: [Beslutslogg](https://linear.app/ai-sprints/document/beslutslogg-brfv2-663a4533845b),
[Projektplan](https://linear.app/ai-sprints/document/projektplan-brfv2-6793aff62a75),
[MVP — vad produkten kan göra nu](https://linear.app/ai-sprints/document/mvp-vad-produkten-kan-gora-nu-8b90b33ea56a),
[Drift-/förvaltningsplan](DRIFT-FORVALTNINGSPLAN.md),
[Erfarenhetsåterföring](ERFARENHETSATERFORING.md), git-historik och
`docs/evidence/`.

## 1. Ursprungligt problem, godkänd omfattning och levererat utfall

**Problemet** (BP1, Beslutslogg): BRF-styrelser sitter på stora mängder
dokument (stämmoprotokoll, underhållsplaner, avtal, årsredovisningar) och
saknar ett sätt att snabbt hitta och verifiera information i dem utan att
lita blint på ett AI-genererat svar.

**Godkänd omfattning** (BP3, samma logg): en avgränsad MVP-slinga —
**logga in → se föreningens dokument → ställ en fråga → få ett grundat svar
→ öppna exakt källa, sida och markerad passage → få tydlig vägran när
underlaget inte räcker** — med administratörsuppladdning och strukturellt
genomdriven tenant-isolering. Den bredare visionen (kalender, e-post,
fakturor, signering, arbetsflöden) var uttryckligen utanför.

**Levererat utfall:** exakt den avgränsade slingan ovan, verifierad både
automatiskt (deterministisk Playwright-acceptans) och live mot en verklig
självhostad 12B-modell och en skyddad verklig BRF-korpus. Ingenting utöver
den godkända omfattningen levererades som produktionsfunktion — global sök,
dokumentbunden chatt, kvalitetskontroll och bevakningar förblir dolda/
spärrade i pilotvyn ([MVP-dokumentet](https://linear.app/ai-sprints/document/mvp-vad-produkten-kan-gora-nu-8b90b33ea56a)).

## 2. Arkitektur och driftstopologi vid överlämning

Se [Drift-/förvaltningsplanen §1](DRIFT-FORVALTNINGSPLAN.md#1-topologi) för
den fullständiga bilden. I korthet:

- **Fedora** (`/home/aidev/Projects/brfv2`) är produkt- och
  utvecklingsvärd: FastAPI-backend (:8787), kanonisk `brfv2-mockup`-frontend
  (:5173, Vite/React), SQLite-auth och per-tenant JSON-lagring — allt i
  samma repo, ingen nästlad utcheckning.
- **Ubuntu-servern `agenntserver`** (RTX 4070) är enbart modellruntime: en
  llama.cpp-container som exponerar Gemma 4 12B på en OpenAI-kompatibel
  yta, nådd via en explicit SSH-forward — aldrig direkt exponerad.
- Retrieval är hybrid (BM25 + `model2vec`-embeddings), utan omrankning som
  standard (se §4 och §5). Citat är multi-span och verbatim-verifierade;
  highlight ritas från bevarad sida+bbox-metadata genom hela kedjan.

## 3. Verifierat produktbeteende och BP5-evidens

**Spårbar historik för den granskade leveransen:**
`f477d71` (kallgranskad av XS-35) → `710cf1c` (handover-hygien) → `c77f0c5`
(verbatim evidens) → `37653d7` (`--no-ff`-merge till `main`).

**Verifierat på den mergade `main`-baslinjen** (Projektplan, XS-36):

| Kontroll | Resultat |
|---|---:|
| Backend `pytest -q` | 537 passed, 5 skipped |
| Auth/isolering/livscykel | 48 passed |
| Kanonisk frontend Vitest | 14 passed |
| Frontend lint | exit 0 |
| Frontend produktionsbygge | exit 0 |
| Playwright-acceptans | 11 passed |
| Realkorpusgate (`model_readiness --network-audit`) | `VERDICT: READY`, exit 0, 0 externa anslutningar |
| Readiness-självtest (positivt) | exit 0 |
| Readiness-självtest (fabricerande) | exit 1 (korrekt avvisat) |

**Oberoende reproducerat av XS-35** (Opus 5, fräsch session, ingen
byggminne): ren checkout, hela användarresan (login → bibliotek → grundat
svar → källa → rätt PDF-sida och highlight), admin-uppladdningsresan, säker
vägran utan citat, och tenant-isolering utan existence-läcka.
Rekommendation: `PASS BP5`, inga blockerande fynd.

**Formellt beslut:** Simon beslutade `PASS BP5` 2026-07-27
(Beslutslogg).

## 4. Avvikelser från projektplanen

Alla avvikelser nedan var nödvändiga korrigeringar för att leverera den
godkända omfattningen, inte scope-glidning:

1. **Frontendkonsolidering.** `brfv2-mockup/` låg som ett separat,
   gitignorerat repo fram till juli 2026, vilket gjorde att en ren klon av
   huvudrepot inte kunde köra produkten. [XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)
   gjorde katalogen till vanliga spårade filer i huvudrepot; historiken
   finns kvar på `migration/brfv2-mockup/*`. Se
   [Erfarenhetsåterföring §2/§4](ERFARENHETSATERFORING.md).
2. **Fedora som primär miljö.** Utvecklingen flyttade från macOS till
   Fedora Linux (beslut 2026-07-27, Beslutslogg). Plattformsspecifik
   dokumentation och skript korrigerades i samma veva ([XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout),
   [XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery)).
3. **Extern Gemma-runtime.** Pilotgenerering kräver en extern Ubuntu-server
   (`agenntserver`) nådd via SSH-tunnel, i stället för en helt lokal
   modell. Detta är en accepterad, dokumenterad extern beroende — se
   [Drift-/förvaltningsplanen §7](DRIFT-FORVALTNINGSPLAN.md#7-kända-operativa-begränsningar) —
   inte en dold begränsning.
4. **Omrankning byggd men avstängd som standard.** En cross-encoder-
   omrankare implementerades och mättes ([XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee)),
   men introducerade fel-rad-svar på årsredovisningstabeller. Kvar avstängd
   tills semantisk etikettmatchning finns; parkerat, inte struket.

## 5. Accepterade begränsningar och parkerat arbete efter pilot

Listas som medvetna scope-beslut — **inte** ofullständiga BP6-åtaganden.
Samtliga ligger i milstolpen **Parkerat efter pilot** och blockerar inte
BP6 (Projektplan, BP6-kriterier):

- **[XS-21](https://linear.app/ai-sprints/issue/XS-21/efter-pilot-utvardera-token-for-token-sse-i-riktig-chat) — SSE-streaming.** Den synkrona `POST /ask` är bevisad
  tillräcklig för hela MVP-resan; token-för-token-strömning är inte
  byggd.
- **[XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee) — q_fee/omrankning.** Se §4 punkt 4.
- **[XS-37](https://linear.app/ai-sprints/issue/XS-37/post-pilot-attest-the-actual-runtime-model-identity) — runtime-identitetsattestering.** `/api/health`s `ready: true`
  är konfigurationsstatus, inte en oberoende verifierad serveridentitet.
- **OCR bortom den formella livegaten.** Skannad ingestion är verifierad
  som en isolerad smoke (7 dokument, 63 sidor), inte i den formella
  livefrågesviten, som kördes på de digitala dokumenten.
- **q01:s icke-ordagranna citat.** Känd, korrekt avvisad begränsning
  (`quote_not_found`); ingår inte i readinessgaten.
- **Reproducerbarhetsgräns för realkorpusgaten.** Kräver både den privata
  korpusen (`DONT_PUSH_brf_stuff/`, aldrig i git) och åtkomst till
  `agenntserver`. Accepterad och dokumenterad gräns, inte dolt tillstånd.

## 6. Förvaltning, ansvar och driftgränser

Fullständig plan: [Drift-/förvaltningsplanen](DRIFT-FORVALTNINGSPLAN.md).
Sammanfattat:

| Ansvarsområde | Ägare |
|---|---|
| Produktkod (backend, frontend, driftskript) | Simon Fredling Jack |
| Modellruntime (`agenntserver`, GPU) | **TBD — ägarbeslut krävs** |
| Korpus/evidens (kunddokument, GDPR-kontakt) | **TBD — ägarbeslut krävs** |
| Backup och restore-övning | **TBD — ägarbeslut krävs** (ingen backup-tjänst finns idag) |
| Incidenthantering | **TBD — ägarbeslut krävs** |
| Godkännande av produktionsändringar | **TBD — ägarbeslut krävs** |

**Driftgräns att komma ihåg:** det finns ingen extern databas — allt
tillstånd är filbaserat under `backend/data/`, och det finns **ingen
schema-migreringsmekanism**. En produktionsändring av datamodellen kräver
ett ägarbeslut innan den görs mot en riktig kundtenant (Drift-
/förvaltningsplanen §6).

## 7. Lärdomar från erfarenhetsåterföringen

Fullständig version med citat: [Erfarenhetsåterföring](ERFARENHETSATERFORING.md).
De sju reglerna för nästa projekt:

1. Konsolidera all produktkod i ett repo innan "ren klon kör produkten"
   hävdas.
2. Bygg tenant-isolering som separata objektgrafer från dag ett, inte
   filter.
3. Bevisa varje negativ (egress, fabricering, PII-läcka) med en tripwire
   eller fullständig korpuskorskörning, aldrig med enbart kodläsning.
4. Mät fel-svar-**introduktion**, inte återvinningsgrad, innan en
   rankningskomponent slås på.
5. Håll provider-/runtimekonfiguration bakom en en-rads env-växel från
   arkitekturbeslutet och framåt.
6. Schemalägg en oberoende, fräsch-kontext kall granskning före varje
   regulerat gate.
7. Registrera modell och effort per issue från BP1, inte efter halva
   genomförandet.

## 8. Återstående BP6-villkor och rekommendation

Projektplanens BP6-kriterier, ett i taget:

- ✅ Publicerad `main`-baslinje, dokumentation och evidens är konsekventa
  (verifierat i den här rapporten, §3–§5).
- ✅ Drift-/förvaltningsplanen är verifierad, ansvar/TBD tydliga ([XS-25](https://linear.app/ai-sprints/issue/XS-25/drift-forvaltningsplan), Done).
- ✅ Erfarenhetsåterföringen är evidensbaserad och användbar för nästa
  projekt ([XS-24](https://linear.app/ai-sprints/issue/XS-24/erfarenhetsaterforing), Done).
- ✅ Slutrapporten är färdig och ger ett spårbart BP6-beslutsunderlag
  (det här dokumentet).
- ✅ Projektmaterialet är arkiverat ([XS-26](https://linear.app/ai-sprints/issue/XS-26/dokumentation-och-arkivering-implementeringslage),
  Done sedan 2026-07-22; ingen dokumentation motsäger nuläget vid den här
  läsningen).

Ingen kvarstående post-pilot-post ([XS-21](https://linear.app/ai-sprints/issue/XS-21/efter-pilot-utvardera-token-for-token-sse-i-riktig-chat),
[XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee),
[XS-37](https://linear.app/ai-sprints/issue/XS-37/post-pilot-attest-the-actual-runtime-model-identity))
är ett dolt BP6-blockerare — de ligger uttryckligen i milstolpen "Parkerat
efter pilot" och kräver inget för att stänga Avslut-fasen.

De enda öppna ägarskaps-TBD:erna i §6 är verkliga och synliga, inte gissade
— de är ett medvetet Antagande-läge, inte ett gate-hinder: drift kan
fortsätta med Simon som enda tillgängliga ägare tills ett formellt
ägarbeslut fattas.

**Rekommendation: `PASS BP6`.**

Per projektets granskningsprincip (en agent godkänner aldrig sitt eget
gate) är detta en rekommendation grundad i ovanstående evidens — det
formella BP6-beslutet är Simons.

## 9. Arkivering

Se [XS-26](https://linear.app/ai-sprints/issue/XS-26/dokumentation-och-arkivering-implementeringslage)
för den ursprungliga dokumentationsstädningen (2026-07-22). Den här
rapporten, tillsammans med [Drift-/förvaltningsplanen](DRIFT-FORVALTNINGSPLAN.md)
och [Erfarenhetsåterföringen](ERFARENHETSATERFORING.md), utgör
BP6-arkivet och länkas från README. Ingen äldre lokal statusdokumentation
identifierades som motsägande vid den här läsningen (§8).

## 10. Inbokad effektkontroll

Effektmålen från Business Case ([XS-6](https://linear.app/ai-sprints/issue/XS-6/business-case-and-effektmal))
definierade **kategorier** av nytta att mäta (sparade analystimmar,
svarstid, andel svar med korrekt källa, färre missade tidsfrister) men
**inga fastställda numeriska trösklar** — det bekräftades inte i något
källdokument, så det redovisas här som en öppen punkt snarare än att ett
tal hittas på.

Effektmätningen sker i Effekt-fasen, efter BP6, genom:

- **[XS-27](https://linear.app/ai-sprints/issue/XS-27/mat-effektmalen) — Mät effektmålen:** faktisk användning, sparade analystimmar,
  andel svar med korrekt källa, svarstid, mot Business Case-kategorierna.
- **[XS-28](https://linear.app/ai-sprints/issue/XS-28/folj-upp-business-case-antagandena) — Följ upp Business Case-antagandena:** håller nyttan mot
  drift-/modellkostnaden i praktiken.
- **[XS-29](https://linear.app/ai-sprints/issue/XS-29/beslut-om-nasta-iteration) — Beslut om nästa iteration:** ingång till ett nytt
  Idé → Förstudie-varv (t.ex. multi-tenant/SaaS för flera BRF:er), styrt av
  pilotens faktiska användning snarare än den ursprungliga visionen.

**När:** namnges av Simon när pilotanvändning finns att mäta — inget datum
sätts här, i linje med principen att inte fabricera tidsuppskattningar.
**Vem som frågar:** Simon, som projektägare och styrgrupp i ett.

## 11. Verifieringslogg för den här rapporten

- Varje testresultat och commit-SHA i §3 är hämtat direkt ur Projektplanen
  och Beslutsloggen, inte omräknat eller uppskattat.
- Samtliga länkade Linear-issues (XS-6, XS-21, XS-23–XS-29, XS-31, XS-33–
  XS-37) och Linear-dokument (Beslutslogg, Projektplan, MVP-dokumentet)
  lästes i sin helhet för den här rapporten.
- §5 och §6 är direkta sammanfattningar av redan verifierat innehåll i
  [Drift-/förvaltningsplanen](DRIFT-FORVALTNINGSPLAN.md) och
  [Erfarenhetsåterföringen](ERFARENHETSATERFORING.md) — inga nya påståenden
  om driftbeteende gjordes utan att spåras dit.
- **Inte gjort:** ingen ny kod kördes eller ändrades för den här rapporten;
  inga tidigare gate-beslut (BP1–BP5) ifrågasattes eller kördes om.
