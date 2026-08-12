# Ger gränsad fan-out något? (BRF-5, första mätningen)

**Datum:** 2026-08-12 · **Harness:** `backend/scripts/eval_crossdoc.py` ·
**Gren:** `feat/brf-1-cross-document`

## Kort svar

**Nej — inte på nuvarande underlag, vid samma promptbudget.** Den planerade
fan-outen slår inte en enkel sökning på golden-korpusen. Den vinner bara när
den får fler utdrag än enkelsökningen, vilket inte är en vinst utan en större
nota.

Det ändrar inte att arkitekturen är riktig eller att `clarify` är värdefullt i
sig. Det betyder att **fan-outens nytta är obevisad**, och att
`PER_QUERY_TOP_K` och `MAX_EVIDENCE_CHUNKS` inte får trimmas på det här
underlaget.

## Vad som mäts

Bevisrecall, utan LLM: för varje golden-fall är de chunkar kända som ett
korrekt svar måste citera ur (golden-citaten pekar ut dem). Frågan är om de
chunkarna **når prompten över huvud taget**. En chunk som inte når prompten kan
inte citeras, så det är ett hårt tak på svarskvalitet som ingen modell kan
klättra över.

Ingen modell körs. Siffran ska inte röra sig när modellen byts.

## Resultat

Korpus: 4 golden-dokument + 40 distraktorer = 44 dokument/chunkar. Båda
strategierna får **samma totala promptbudget** — annars "vinner" fan-out bara
genom att få kosta mer.

| Budget (utdrag) | Enkel sökning | Planerad fan-out |
|---:|---:|---:|
| 1 | 0.50 | 0.38 |
| 2 | 0.88 | 0.62 |
| 3 | **1.00** | 0.62 |
| 4 | 1.00 | 1.00 |
| 6 | 1.00 | 1.00 |
| 8 | 1.00 | 1.00 |

Enkelsökningen når full recall vid budget 3; fan-outen behöver 4. Vid trång
budget är den **sämre**, för att den delar budgeten mellan delfrågor som ofta
hämtar överlappande chunkar.

## Varför — och vad som är fel på underlaget

Golden-fallen är skrivna så att **frågan själv innehåller termer ur varje
dokument den behöver**. "Vem är leverantör och har styrelsen godkänt det?"
matchar både avtalet och protokollet i en enda sökning. Fan-out löser problemet
att en fråga har en del *utan* lexikal överlappning mot sitt dokument — och den
sortens fall finns inte i korpusen ännu.

Två fällor jag gick i och som är värda att minnas:

1. **Första körningen gav 1.00/1.00 och såg ut som en framgång.** Korpusen var
   4 chunkar och `topK=6` — varje sökning returnerade hela korpusen. Mätningen
   diskriminerade ingenting. Därav distraktorerna, och
   `test_distractors_actually_make_retrieval_choose`.
2. **Att ge fan-outen egen budget döljer resultatet.** Med `topK=6` per delfråga
   mot 6 totalt för enkelsökningen ser fan-out bättre ut, men jämförelsen är
   meningslös. Svepet håller notan lika.

## Vad som borde göras härnäst

- **Skriv golden-fall som faktiskt kräver fan-out**: en fråga vars andra del är
  lexikalt disjunkt från sitt dokument. Utan sådana fall mäter BRF-5 fel sak.
- **Mät på riktig korpus**, inte fixturer med en chunk per dokument. Verkliga
  årsredovisningar och stadgar har många chunkar per dokument, vilket är där
  budgettrycket faktiskt uppstår.
- **Först därefter** trimma `PER_QUERY_TOP_K` / `MAX_EVIDENCE_CHUNKS`.

Tills dess: den planerade vägen ligger kvar bakom `BRF_PLANNED_ASK` och är
avstängd som default. Det är rätt läge för en funktion vars nytta ännu inte är
uppmätt.
