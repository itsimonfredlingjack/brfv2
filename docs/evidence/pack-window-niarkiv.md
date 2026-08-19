# Fönsterpackning mot hela handlingen — niarkivsinstrumentet — 2026-08-18

**Host:** agenntserver · **inte paketerat** · ingen ändring i `backend/app/document_ask.py`, `ops/pins.json` eller RPM · embedder `minishlab/potion-multilingual-128M` (produkt, XS-77: bytet skedde inte) · `BRF_LLM=fake` · llama.cpp `/tokenize` för prefix, `n_ctx=65536`, effektivt tak `65536 − 512 − 1800 = 63224`.

Samma 863 rader som `e5-large-retrieval.md` / `kblab-sbert-retrieval.md`. Nivå B redovisas inte.

Dokumentvägen packar i dag varje stycke i de valda handlingarna. Den här körningen rör **hur mycket** av en redan vald handling som packas, inte vilken handling som väljs. Urvalet är instrumentets: handlingen som toppträffen ligger i.

Tre armar, en ingestion:

| arm | packning | N |
| --- | --- | --- |
| hel | alla stycken i den valda handlingen (dagens dokumentväg) | — |
| fast | sammanhängande fönster runt högst rankade stycket i den handlingen | 7 stycken |
| adaptiv | samma centrum, upp till taket, men aldrig hela handlingen om den är längre än 7 stycken (högst hälften, minst 7) | — |

N=7 landar i samma storleksordning som de elva fallens vinnande enkeldokument (2 100–2 500 token) när handlingen är lång. Grannstycken följer sid- och ordföljd **inuti handlingen**, även över sidgräns — inte den sidlokala expansionen i `evidence.py` (XS-76:s berikningssteg).

Taket band **aldrig**. Största hel-prefix 36 004 mot 63 224. Adaptiv ≠ hel enbart på grund av «aldrig hela den långa handlingen», inte för att fönstret tog slut.

## Det som avgör

Protokoll- och avtalscellerna **rör sig inte**. 13 % och 7 % mot slump 34 % och 19 %. Packning efter urval kan inte lyfta en cell som förlorar på *vilken* handling som ligger överst.

När protokoll **väl** väljs är handlingen redan kort: 5 408 token, 12,7 stycken. Fast fönster tar den till 3 088. Det är inte 47–54k → 2,1–2,5k. De 12 255 token som protokollcellen visar i snitt är de 211 missarna, som packar en *annan* lång handling.

Avtalets enda träff är tre stycken, 1 868 token. Fönster = hela handlingen.

Årsredovisning och underhållsplan är där koncentrationen syns: rätt vald årsredovisning packar 21 208 token hel, 3 375 fast, 11 392 adaptiv. Gold@5 på de träffarna faller 62 % → 40 % → 48 %. Flera sidor behövs, och det fasta fönstret släpper dem.

12B-klassen och NoLiMa mäts inte här. Det här instrumentet har facit på handlingstyp, inte på svar. Prefix och gold@5 är kostnaden och täckningen. Svarssteget är inte kört.

## Publicerad cell (inte B) — urval

Samma 863 rader. Slump identisk. Δ mot hel (den här körningens hela-handling-baslinje). Utfall är toppträffens typ.

| | hel | fast | adaptiv | slump | Δ fast | Δ adaptiv | rader |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| alla (inte B) | 46 % (397/863) | 46 % | 46 % | 24 % | **—** | **—** | 863 |
| stadgar | 69 % (266/387) | 69 % | 69 % | 15 % | **—** | **—** | 387 |
| protokoll | 13 % (33/252) | 13 % | 13 % | 34 % | **—** | **—** | 252 |
| årsredovisning | 46 % (74/160) | 46 % | 46 % | 30 % | **—** | **—** | 160 |
| underhållsplan | 38 % (15/40) | 38 % | 38 % | 17 % | **—** | **—** | 40 |
| avtal | 7 % (1/14) | 7 % | 7 % | 19 % | **—** | **—** | 14 |
| ordningsregler | 80 % (8/10) | 80 % | 80 % | 18 % | **—** | **—** | 10 |

Sju publicerade rader skiljer sig från den reproducerade potion-armen (394/863). Den här körningen sökte hela poolen för att kunna räkna gold@5; potion-armen tog `top_k=1` ur `candidateCount=100`. Protokoll 33/252 i båda. Ingestionen identisk (0 handlingar ändrade, 195 357 ord). En tunn handling: Faran/`protokoll-3.pdf`.

## Prefix per cell

Medel / median, publicerad cell. Kostnaden syns här, inte i träffkvoten.

| | hel medel | fast medel | adaptiv medel | Δ fast | Δ adaptiv | hel median | fast median | adaptiv median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| alla (inte B) | 13 029 | 3 388 | 7 091 | **−9 641** | **−5 938** | 11 448 | 3 473 | 5 995 |
| stadgar | 11 914 | 3 504 | 6 434 | **−8 409** | **−5 479** | 11 448 | 3 534 | 5 912 |
| protokoll | 12 255 | 3 210 | 6 819 | **−9 045** | **−5 436** | 10 762 | 3 298 | 5 663 |
| årsredovisning | 16 488 | 3 417 | 8 853 | **−13 071** | **−7 635** | 16 249 | 3 468 | 8 612 |
| underhållsplan | 15 384 | 3 477 | 8 274 | **−11 907** | **−7 110** | 11 937 | 3 534 | 6 242 |
| avtal | 15 221 | 3 117 | 8 304 | **−12 104** | **−6 916** | 13 590 | 3 244 | 6 978 |
| ordningsregler | 7 864 | 2 968 | 4 733 | **−4 896** | **−3 131** | 5 301 | 3 189 | 3 413 |

Cellmedel blandar träff och miss. Delat på utfall, samma publicerade rader:

| cell | utfall | n | hel | fast | adaptiv | stycken i vald handling |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| protokoll | träff | 33 | 5 408 | 3 088 | 3 400 | 12,7 |
| protokoll | fel | 211 | 13 307 | 3 219 | 7 352 | 31,5 (fel handling) |
| avtal | träff | 1 | 1 868 | 1 868 | 1 868 | 3,0 |
| avtal | fel | 13 | 16 248 | 3 213 | 8 799 | 37,5 (fel handling) |
| årsredovisning | träff | 74 | 21 208 | 3 375 | 11 392 | 48,9 |
| årsredovisning | fel | 65 | 11 807 | 3 422 | 6 381 | 27,9 |
| underhållsplan | träff | 15 | 15 657 | 3 540 | 8 454 | 42,1 |
| stadgar | träff | 266 | 12 075 | 3 622 | 6 508 | 27,0 |

Fast fönster packade hela handlingen i 7 % av de publicerade raderna (korta träffar). Adaptiv likaså 7 % — samma korta dokument. Hel packade 100 % hela.

## Gold@5 när rätt handling låg överst

Andel av facit-typens fem högst rankade stycken i arkivet som låg i paketet, bara rader med `utfall=träff`. Hel kan missa stycken som ligger i *en annan* handling av samma typ (flera protokoll i samma arkiv).

| | hel | fast | adaptiv |
| --- | ---: | ---: | ---: |
| stadgar (266) | 100 % | 53 % | 70 % |
| protokoll (33) | 70 % | 52 % | 57 % |
| årsredovisning (74) | 62 % | 40 % | 48 % |
| underhållsplan (15) | 87 % | 60 % | 71 % |
| avtal (1) | 60 % | 60 % | 60 % |

Årsredovisning och underhållsplan tappar spridd evidens i det fasta fönstret. Protokoll tappar också, men från en lägre bas: de fem bästa protokolstyckena ligger inte alltid i den enda valda filen. Avtalets enda träff ryms i fönstret.

## `diff.py` mot den senast körda armen (KBLab)

Lång A+M, 754 rader. KBLab är senaste retrieval-armen, en annan embedder. Skillnaden är **inte** packning.

| | KBLab | hel (potion, den här körningen) | skillnad | rader |
| --- | ---: | ---: | ---: | ---: |
| alla lång | 51 % | 48 % | **−3 pp** | 754 |
| protokoll | 16 % | 13 % | **−3 pp** | 231 |
| årsredovisning | 67 % | 50 % | **−17 pp** | 112 |
| stadgar | 67 % | 69 % | **+1 pp** | 387 |

118 av 754 rader bytte utfall mot KBLab. Det är samma riktning som `kblab-sbert-retrieval.md` (KBLab mot potion). Ingestionen identisk.

Mot den reproducerade potion-armen är lång form 47 % mot 48 %. Sju publicerade rader skiljer sig, se ovan. Packningsarmarna skiljer sig inte åt i `utfall`.

## Nollprov

Tolv neutrala frågor × nio arkiv = 108. Samma urval i alla tre packningar. Under tröskeln 0,18: 37/108, medelkonfidens 0,21 — samma som potion-armen.

| handlingstyp | hel / fast / adaptiv |
| --- | --- |
| årsredovisning | 33/108 (31 %) |
| stadgar | 25/108 (23 %) |
| underhållsplan | 18/108 (17 %) |
| ordningsregler | 17/108 (16 %) |
| protokoll | 6/108 (6 %) |
| informationsbrev | 6/108 (6 %) |
| energideklaration | 3/108 (3 %) |
| avtal | 0/108 (0 %) |

Prefix på nonsens: hel 14 296, fast 3 123, adaptiv 7 858. Magneten är orörd. Protokoll på nonsens 6 %, samma som potion.

## Armar

| | hel | fast | adaptiv |
| --- | --- | --- | --- |
| urval | toppträffens handling (potion) | samma | samma |
| packning | hela handlingen | 7 stycken runt fröet | ≤ 50 % av lång handling, minst 7 |
| prefix publicerad cell, medel | 13 029 | 3 388 | 7 091 |
| utdata | `resultat-pack-hel.json` | `resultat-pack-fast.json` | `resultat-pack-adaptiv.json` |

Väggklocka 500 s, en ingestion. `ops/pins.json` orörd.

Elva frågor mot ett arkiv kördes inte. 6/11 vid 47–54k mot 9/10 vid 2,1–2,5k när rätt handling var packad är fortfarande det enda svarssteget. Den här körningen säger vad niarkivsinstrumentet kan säga: urvalet är densamma, prefixet krymper, och spridd evidens i årsredovisning och underhållsplan ramlar ur det fasta fönstret.
