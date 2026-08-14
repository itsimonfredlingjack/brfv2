# Beslut — planerad fan-out skeppas inte i MVP (2026-08-13)

Gren `feat/brf-1-cross-document` @ `03623e9`. **Redaktion:** endast siffror.
Underlag: [`planner-vs-real-model.md`](planner-vs-real-model.md) (XS-62,
mätning mot riktig modell), [`crossdoc-fanout.md`](crossdoc-fanout.md)
(hämtningsstrategin), [`cold-review-brf1.md`](cold-review-brf1.md) (XS-64).

> **Siffrorna nedan är mätta 2026-08-13 före tilläggen 2 och 3.** Fyra av dem
> har rört sig sedan dess: falsk `clarify` 4 → 0 (läget är borttaget ur
> kontraktet), kontrollrecall 0.91 → 1.00, överutlösning 14 → 12 av 46, och
> **r01 tillbaka på 0.00** — motivfallet vände en tredje gång, på en
> promptändring som inte rör ordförrådsglappet. Skäl 3 nedan ("skör mekanism")
> är därmed mätt tre gånger i stället för en; skäl 1 och 2 är däremot åtgärdade.
> Se `planner-vs-real-model.md`, tilläggen 2 och 3. Grindbeslutet är inte
> omprövat här. Villkor B är dessutom besvarat i tilläggen 4 och 5: de extra
> sökningarna köper ingen recall — och kostar heller ingen svarskvalitet, mätt
> med riktig syntes på alla tolv överutlösande fall.

## Beslut

**Den planerade multi-vägen är av som produktväg i MVP.** Koden ligger kvar,
dubbelgrindad och onåbar; ingen konfiguration ändrades för att fatta beslutet,
eftersom vägen redan var stängd.

Beslutet gäller **planeraren**, inte hämtningsstrategin. Den skillnaden är hela
poängen med underlaget nedan.

## Frågan

BRF-1 byggde `fråga → plan → gränsad fan-out → bevispåse → syntes → befintlig
citat- och sifferverifiering`. `crossdoc-fanout.md` mätte hämtningsstrategin med
fallens **handskrivna** delfrågor och visade 0.00 → 1.00 på r01, det enda
verkliga fall där en enkel sökning missar allt.

Det lämnade den frågan som avgör om funktionen är en produkt: **väljer en riktig
modell rätt läge, och skriver den delfrågor som översätter till dokumentens
språk?** XS-62 mätte det. Det här dokumentet är grinden.

## Vad som mättes

`backend/scripts/eval_planner.py` kör den riktiga `ask_planned` mot
`gemma-4-12b-it` UD-Q4_K_XL på llama.cpp genom produktionens
`OpenAICompatProvider`. Bara syntesanropet är kanonsvarat. Sökningar räknas där
`HybridIndex.search` anropas, alltså observerat, inte härlett ur läget.

Två populationer:

- **13 tvärdokumentsfall** ur `eval/golden_crossdoc.json`.
- **46 enkelsökningsfrågor** ur `eval/golden.json` som **negativa kontroller** —
  samma golden produkten redan mäts mot, inte en lista skriven för experimentet.
  Där är `multi` en kostnad, inte ett resultat.

Alla siffror nedan är med **sorterad dokumentkatalog** (`03623e9`). Avkodningen
är girig, så en körning per fall är hela sanningen för en given prompt; r01
kördes tre gånger som kontroll och gav samma resultat varje gång.

## Resultat

| | Tvärdokument (13) | Negativa kontroller (46) |
|---|---:|---:|
| Recall, planerarens delfrågor | **0.91** | **0.91** |
| Recall, enkel sökning (baslinje) | 0.86 | **1.00** |
| Andel som valde `multi` | 38 % | **30 % (14 av 46)** |
| Medelantal sökningar (idealet 1.0) | 1.7 | **1.50** |
| Fall med `clarify` och noll sökningar | 1 (rätt: x02) | **4 (fel: g21, g23, g33, g43)** |

Två fall bär hela vinsten på tvärdokumentsmängden: **r01** går 0.00 → 1.00 och
**x06** 0.50 → 1.00. Ett fall förlorar: **v01** 1.00 → 0.00.

## Fyra skäl att inte skeppa

**1. På den population som dominerar verklig användning är vägen sämre.**
Styrelser ställer i huvudsak frågor som en sökning besvarar. Där ligger
baslinjen på 1.00 — enkel sökning hittar beviset varje gång — och den planerade
vägen på 0.91, till 50 % fler sökningar plus ett modellanrop per fråga. Det är
inte en avvägning. Det är en regression med en räkning.

**2. Förlusten är en vägran att leta, inte en latenskostnad.**
Uppdelningen är entydig: **ingen recallförlust kom från en `multi`.** Varje
förlust är en `clarify` — planeraren ställer en motfråga och gör noll
sökningar. Fyra besvarbara frågor drabbas, bland dem "När hålls nästa
styrelsemöte?" och "Hur stort är det samlade underhållsbehovet?", båda med
baslinje 1.00.

Det är den felmod produkten är byggd för att undvika, uppnådd från fel håll:
inte ett påhittat svar, utan en vägran att leta efter ett svar som ligger en
sökning bort. Överutlösning kostar beräkning. Falsk `clarify` kostar svaret.
De två är inte jämförbara.

**3. Vinsten vilar på ett verkligt fall med en skör mekanism.**
r01 fungerar: 1.00 mot enkelsökningens 0.00, tre av tre. Men bron mellan
`sophämtning` och `sophantering` är **dokumentets filnamn, avskrivet ur
katalogen** — inte svensk morfologi. Två följder:

- En förening med `Scan_2022_004.pdf` har ingen bro att låna. Vinsten
  generaliserar inte till ett dåligt namngivet arkiv, och det är arkiven som
  finns.
- Resultatet vände på en sorteringsändring. Marginalen är tunn nog att en
  promptdetalj avgör den.

Inget annat fall i korpusen visar samma sak oberoende. Ett fall är ett fall.

**4. `clarify` är en spärr utan tröskel.**
`PLANNER_CONTRACT` säger "Är du osäker: välj single". Regeln gäller valet mellan
`single` och `multi` och säger ingenting om när `clarify` är befogat. Läget kan
alltså sänka recall genom sin konstruktion, och det gjorde det. Det är ett
designfel i kontraktet, inte en inställning som går att skruva på.

## Vad som INTE är skälet

**Hämtningsstrategin är inte problemet.** Handskrivna delfrågor når 1.00 på r01.
Gränsad fan-out gör det den ska. Det som fattas är en planerare som väljer rätt
läge och översätter frågan till handlingarnas ordförråd — och den finns inte
ännu, i den här modellen, med det här kontraktet.

Beslutet är därför inte "fan-out fungerar inte". Det är **"planeraren är inte
klar, och en halv planerare är sämre än ingen"**.

## Vad som konkret måste vara sant för att slå på den

Fyra villkor. Alla mätbara med harnesset som redan finns; inget av dem är en
bedömningsfråga.

| # | Villkor | Mäts med |
|---|---|---|
| **A** | **Noll** falska `clarify` på de 46 negativa kontrollerna. Strukturellt, inte genom promptjustering: `clarify` måste bli ett beslut **efter** hämtning, eller lämna kontraktet. Ett läge som kan sänka recall genom sin konstruktion får inte finnas i produktionsvägen. | `eval_planner --runs 1` |
| **B** | Överutlösning ≤ 2 av 46, **eller** bevis för att de extra sökningarna köper recall på något mätt fall. Idag: 14 av 46 till 1.50 sökningar, recall oförändrad. | `eval_planner --runs 1` |
| **C** | Ordförrådsvinsten reproducerad på **minst tre verkliga fall**, varav minst ett där handlingens filnamn **inte** innehåller det överbryggande ordet. Det är vad XS-66 ska vägas mot — inte mot "kan lyfta r01", som redan är avgjort åt båda hållen. | verkliga arkivet, lokalt, endast siffror ut |
| **D** | Den kvarvarande grindasymmetrin stängd: den planerade vägen **omrankar inte** ens när omrankning är påslagen och tillgänglig. Felet höjs numera när omrankaren saknas, men när den finns hoppas den tyst över. | läst i `app/answer.py`; inget lås finns ännu, och ett lås som fäster nuvarande beteende vore fel lås. Det skrivs när asymmetrin stängs. |

Villkor A och B mäts i samma femminuterskörning. C kräver arbete.

**D är inte en enradsfix, och därför inte gjord här.** `rerank_chunks(question,
hits, s.topK)` skär till `topK`. På den planerade vägen skulle det klippa
bevispåsen från upp till `MAX_EVIDENCE_CHUNKS` (10) ner till `topK` (6) och tyst
kasta fan-outens egna utdrag — en hämtningsändring, inte en grindparitet. Den
behöver mätas, inte antas, och hör därför ihop med A–C snarare än med de tre
luckor som stängdes i `03623e9`.

## Vad som ändå gjordes, och varför

Grindpariteten fixades trots att vägen är av (`03623e9`). En kodväg där systemet
svarar utan att kunna vägra motsäger produktens hela värdelöfte och ska inte
ligga latent i koden och vänta på att någon sätter en flagga.

Tre luckor var stängda, alla med lås som brutits på riktigt och setts falla:

- `minRelevance` beräknades aldrig på den planerade vägen — `low_relevance=False`
  var hårdkodat, så fan-outens egna utdrag var relevanta per konstruktion.
- rerank-`LLMError` låg **efter** bevisgrenen och var därför onåbar med en
  bevispåse. En vägran som en kodväg kan gå runt är ingen grind.
- `append_linked_table_legends` kördes inte. Beslut: den ska köras. En kodrad
  ("B12.3.4 … B") är oläsbar utan legenden som definierar bokstaven, och varken
  citatupplösaren eller sifferkontrollen fångar felet — citatet är ordagrant och
  den falska uppgiften är ett **ord**, inte ett tal.

Dokumentkatalogen sorteras nu också. Ordningen var uppladdningsordning, alltså
en odesignad produktionsvariabel: 22 av 59 fall bytte läge när den blandades.

## Grindarnas tillstånd

Ingen konfiguration ändrades. Båda grindarna var redan stängda, och en av dem
har ingen producent alls:

| Grind | Var | Tillstånd |
|---|---|---|
| `BRF_PLANNED_ASK` (server) | sätts inte i `ops/demo.sh`, `backend/.env.example`, `app/desktop.py` eller RPM-specen | osatt ⇒ `planned_ask_enabled()` falskt |
| `AskRequest.planned` (klient) | `brfv2-mockup/src/api.js:50` skickar `{ question }`; ingen träff på `planned` i mobilklienten heller | fältet skickas aldrig |

Antingen ensam räcker. Att båda är stängda är avsiktligt och inte redundans att
städa bort.

## Sviter

Backend **1344 passed, 3 skipped**. Isolering/auth/livscykel **49 passed**.
Kanonisk frontend **258 passed**. Mätningen har ingen exitkod som beror på
siffrorna och grindar aldrig CI.

## Omprövning

```bash
cd backend
ssh -N -L 8000:127.0.0.1:8000 agenntserver-lan &      # OBS: -lan, inte tailnet-aliaset
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM=selfhosted \
  uv run python -m scripts.eval_planner --runs 1 --catalogue fixed
```

Ungefär fem minuter. Kör den inte parallellt med pytest-sviten. Villkor A och B
läses direkt ur de två tabellerna; C och D kräver arbete utanför harnesset.
