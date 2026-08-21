# Var "Rätt handling överst" står — handoff 2026-08-20

Skrivet så en ny session (grok-4.6, för att spara Claude-usage) slipper göra om det
här. Läs det här först. Simon är inte utvecklare — förklara plant, en sak i taget,
inga väggar av teori. Han blir less av för mycket Linear/process-prat; ge honom
konkreta enskilda nästa steg, inte fler ramverk.

## Läget på en rad

Linear-projektet **"brfv2 — Rätt handling överst"** (team `XS-automation-solutions`)
står i **BP5 (Genomförande)**, Loop 1 klar (XS-71, cross-encoder-omrankning, negativt
resultat). XS-74 (Recall@6) kördes just nu i den här sessionen — se nedan — men gav
ett resultat som inte reproducerar den låsta baslinjen exakt, så det enda öppna
beslutet är vad man gör med det.

## Det enda öppna beslutet

**P@1 reproducerade inte.** Låst baslinje: 46,1 % totalt. Den här körningen: **45,1 %**
(760/1687 rader). Kortets egen regel (XS-74-texten): "Gör den inte det mäter skriptet
något annat än förut" — alltså tekniskt ett underkänt icke-vakuositetstest.

Trolig orsak, inte bekräftad: `facit.json` på agenntserver har **131 fall** just nu.
XS-80 (filat 2026-08-19, öppet) flaggar redan att den låsta baslinjen citerar 105
frågor men det publicerade facit har 116. Nu syns ett tredje tal, 131. Något har
växt sedan låsningen — trolig root cause för P@1-glappet, men ingen har spårat exakt
vad eller när. **Det är det som behöver lösas innan Recall@6-siffrorna nedan kan
användas som facit och inte bara som en stark indikation.**

## Recall@6-resultatet (kört, verkligt, men se ovan för giltighet)

Skript: `matt-ratt-handling-recall6.py` (ny fil jag skrev, bredvid originalet
`matt-ratt-handling.py` — rörde inte originalet). Körd på agenntserver mot de nio
verkliga arkiven, `top_k=6` i stället för `1`. P@1 beräknas identiskt (`hits[0]`) för
jämförbarhet; nytt är recall@6 + position.

| typ | n | P@1 | Recall@6 |
|---|---|---|---|
| stadgar | 774 | 65,0 % | 94,1 % |
| arsredovisning | 288 | 42,0 % | 86,1 % |
| **protokoll** | **497** | **15,9 %** | **40,6 %** |
| underhållsplan | 70 | 38,6 % | 74,3 % |
| avtal | 22 | 9,1 % | 31,8 % |

**Protokoll, huvudsvaret XS-74 efterfrågade:** i 295 av 497 rader (59 %) finns rätt
protokoll inte ens bland de sex styckena modellen ser. **Det är ett hämtningsfel, inte
ett rankningsfel** — routing på handlingstyp (kodagentens förslag) löser fel problem,
för stycket saknas helt innan rankning ens händer. Kontextberikning vid ingestion
(motsökningens förslag, blir XS-76) är rätt spår.

Rådata: `resultat-recall6.json` i samma mapp på agenntserver, inte committad (se
Datadisciplin).

## Andra öppna issues i samma projekt, i den ordning deras egna beroenden kräver

1. **XS-80** — 105 vs 116 vs (nu synligt) 131 frågor i facit. Bör lösas först, det är
   samma rot som P@1-glappet ovan.
2. **XS-74** — tekniskt inte klarmarkerad (Backlog-status i Linear fortfarande) trots
   att den kördes här. Skriv resultatet ovan som kommentar när XS-80 är löst, eller
   tidigare om Simon vill ha siffrorna som de är.
3. **XS-79** (filat 2026-08-19) — ifrågasätter själva premissen: behöver en stor andel
   styrelsefrågor verkligen föreningens egna dokument? Simon har egna tankar om detta
   (extern research + en delad referenskorpus som alltid finns i databasen bredvid
   föreningens egna dokument, inte modellen som gissar fritt ur egen kunskap) — se
   `docs/research/2026-08-19-grok-bp5-best-practice.md` för bakgrund, men den
   rapporten är inte skriven mot detta projekts faktiska blockerare och ska läsas som
   bakgrund, inte en att-göra-lista.
4. **XS-75/76/77/78** — väntar alla på XS-74/XS-80.

## Kärnprincip att aldrig kompromissa med

Produktens enda förtroendekälla: **varje svar spårbart till en exakt sida i en
verklig handling, aldrig modellens egen sannolikhetsgenererade kunskap.**
`refusal-diagnosis.md` visade att korrekta vägran är en funktion, inte en bugg — en
styrelseledamot måste kunna lita på att ett svar antingen är ett dokumentfaktum eller
ett tydligt "det står inte här". Om domänfinjustering (Simons idé, sparad för senare)
någonsin görs: mät "gold leak" (AbstentionBench-metoden) explicit, och träna aldrig på
en specifik förenings privata dokument — bara offentligt/generiskt material. Det
skulle annars läcka en förenings data in i en annan förenings svar, vilket bryter
per-tenant-isoleringen som redan är adversariellt testad och är en verklig styrka.

## Vad som gjordes i den här omgången (utöver XS-74-körningen)

- `docs/evidence/ask-hits-niarkiv.md` — 5 av 32 `insufficient_data`-vägran lästa mot
  sina protokoll. Citatverifieringsgrinden (`answer.py:355–358`) är strukturellt
  onåbar för alla 32 när modellen själv sätter `insufficient_data: true` — verifierat
  mot koden. 4/5 lästa fall arkivfakta, 1/5 ordförrådsglapp fråga↔handling.
- `docs/research/2026-08-19-grok-bp5-best-practice.md` — Grok-genererad best
  practice-rapport. Den enda siffran hela dess LoRA-rekommendation hänger på
  (LongCite Llama-3.1-8B 19,7→72,0 citat-F1) verifierad mot primärkällan
  (arXiv:2409.02897, Table 2, ordagrant) via ett separat grok-4.6-sökanrop.
- Committat lokalt som `48dd945` — **inte pushat**. Push blockerades av
  auto-mode-klassificeraren tidigare i sessionen; kräver Simons explicita go-ahead.

## Datadisciplin — samma regel som BRF-1

Det verkliga arkivet (`~/brf-corpus-public/` på agenntserver) och mätscripten i
`matning/` får **aldrig committas** till detta repo. Endast redigerad metrics-JSON,
om något, hör hemma i `docs/evidence/`. `resultat-recall6.json` ligger kvar på
agenntserver, inte här.

## Var saker faktiskt ligger

- **Repo (den här maskinen):** `/home/aidev/Projects/brfv2`
- **Agenntserver:** `ssh agenntserver-lan` (LAN-aliaset — Tailscale-varianten blockerar
  på interaktiv auth). Backend + venv: `~/brfv2/backend` (`source .venv/bin/activate`).
  Korpus: `~/brf-corpus-public/arkiv/<förening>/*.pdf`. Mätning:
  `~/brf-corpus-public/matning/` (`facit.json`, `matt-ratt-handling.py` original,
  `matt-ratt-handling-recall6.py` ny, `resultat.json` / `resultat-recall6.json`
  utdata).
- **Linear:** team `XS-automation-solutions`, projekt "brfv2 — Rätt handling överst".
  Övriga fem brfv2-relaterade Linear-projekt är stängda eller separata produktlinjer
  (Fedora app shell, Styrelsearbetsyta, ursprungspiloten, BRF-1) — rör dem inte utan
  att fråga, de är inte den här grindens ansvar.
- **Grok-CLI på den här maskinen:** `~/.grok/bin/grok`, redan autentiserad.
  `grok -p "..." -m grok-4.6 --reasoning-effort high --output-format json` för
  enstaka sökanrop; sök på som standard. Riktiga sökanrop tar >120s — kör i
  bakgrunden, vänta inte synkront.
