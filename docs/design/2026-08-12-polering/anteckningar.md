# Poleringsloppet 2026-08-12 — lärdomar

En post per lärdom, en rads sammanfattning överst i varje post. Rättelser och
bekräftade grepp, med varför de spelade roll. Läses om vid varje ny yta.

## Riggning: egen seedad backend, rör aldrig skrivvägen mot Simons data

Simons körande backend (:53473 → `backend/data`) är hans riktiga data — vite på
:5173 pekar dit. Allt som muterar (import, godkännanden, riggade tillstånd) går
mot en egen `app.desktop --seed-demo` i scratchpad-dataroten, med egen vite på
:5199. Fönstermåtten som gäller: 1440×920 standard, 860×620 minimum
(src-tauri/src/main.rs:39–42) — granska i 1440 och spot-checka 1024/860.
`app.desktop` har ingen `--port`; porten är slumpad per start, så vite måste
startas om med ny `BRF_BACKEND_URL` efter varje backend-omstart.

## Rättelse: döda aldrig processer på PID ur minnet

Jag körde `kill 26982` i tron att det var min vite — det var Simons (:5173).
Dessutom självdödade `pkill -f "vite --port 5199"` mitt eget bash-anrop
(kommandoraden matchar mönstret). Båda återställda inom minuten, ingen data
rörd. Regel: verifiera PID→kommandorad i samma anrop som dödar, och lägg
`grep -v` för det egna mönstret i pkill.

## Sticky inuti panelkedjan kräver min-height: max-content

Hela panelkedjan (.tab-content → .invoices → .invoice-case) är viewporthöga
lådor vars innehåll svämmar ut med overflow: visible — målningen fungerar, men
en position: sticky-remsa slutar följa med efter ~825px eftersom dess
inneslutande block är förälderns låda, inte innehållet. `min-height:
max-content` på .invoice-case gav stickyn hela läsningen. Dessutom:
.main-content har padding-top --s6, så `top: 0` fastnar en paddingsteg ned —
remsan behöver `top: calc(-1 * var(--s6))`.

## Design-locket läser även CSS-kommentarer

Spacing-låset regexar `gap:`/`margin:` var de än står — en prosa-kommentar
("No flex gap: … 24px …") föll i låset. Skriv kommentarer utan `<egenskap>:`
följt av skalvärden, eller formulera om med tokennamn (--s6) i stället för px.

## Mät scrollbarheten, inte utseendet

Fakturakön SÅG färdig ut men gick inte att rulla med hjulet: `.invoices-work`
var skärmens scroll-låda (kedjan .tab-content:has(.invoices) fyller fönstret)
men hade `overflow: hidden` kvar från kortet den en gång var — 900px kö
oåtkomlig utom via tangentbordsfokus. Skärmdumpar avslöjar inte detta; räkna
`scrollHeight - clientHeight` mot `overflow-y` på varje pane som ska rulla.

## Skärmbevis måste vara yngre än koden det påstås visa

Verifieraren (färsk kontext) underkände två av commitens påståenden för att
efter-bilderna togs mot en backend som ännu inte kört fixarna. Rätt rutin:
efter varje backendändring, starta om den seedade backenden FÖRE
bevis-skärmdumparna, och demonstrera lagrings-beteenden (t.ex. _klipp) genom
att trigga en ny händelse — gamla lagrade strängar läker aldrig.

## Instrumentet släcks avsiktligt under 780px fönsterhöjd

Instrument.css: `@media (max-height: 780px) { .instrument { display: none } }`
— "plåten ger upp sin fasta höjd före arbetet". Vid 860×620 saknas alltså
bandets mätare; det är beslutet, inte en bugg. Rör den inte.

## Systematiska läckor genom hela produkten, en klass i taget

Poleringen var till 80 % samma fyra fel om och om igen, tvärs ytor:
1. **Rått datum** (ISO `2026-09-15`) där en styrelse ska läsa "15 sep." —
   fanns i fakturaärende, fakturakö, inkommande, bevakningar, uppgifter,
   dokumentläsare, hemsidans versionslista. Lösning: `datum()`/`datumTid()`
   (frontend), och en delad `svenskt_datum()` i backend/terms.py för prosa
   (rubriker, härledningar, signalmeningar) — maskinfälten behåller ISO.
2. **Privat knappvokabulär** vid egen geometri, vars inaktiva läge blev en grå
   kloss (`opacity: 0.5` på fylld bläckknapp). Fanns i anslutningar, login,
   setup, inställningar, inkommande, uppgifter. Lösning: `.ui-btn`-primitiven
   + nytt lås (Beslut 12b) för den tysta inaktiva primären.
3. **Rått användar-id** (`c36ab380d399`) som aktör i händelseströmmar. En
   `display_actor()` i auth.py (namn→e-post→id) vid alla VISNINGS-poster;
   OAuth/enhetsinloggningens kopplingsposter behåller id.
4. **Engelska/maskinord** i svensk läsning: "triennial", "Systembearbetning",
   "1 sidor"/"1 bilaga(or)"-plural. En delad `RECURRENCE_HUMAN`, mänskliga
   etiketter, riktig singular/plural-böjning.
Leta efter alla fyra på varje ny yta — de sitter aldrig ensamma.

## Regelversionsvakten fångar backend-prosaändringar

När compare.py/terms.py ändras (t.ex. NBSP, minustecken, svenska datum) faller
`test_invoice_rules_version` med rätta: fynd stämplade med gamla
ANALYSIS_ENGINE_VERSION skulle annars påstå att de skrevs av de nya reglerna.
Höj versionen i app/invoices/models.py och kör
`.venv/bin/python -m app.invoices.rules --write`.

## Riggning efter en omstart: seeda om och läs om aktörsnamn

Efter datorstart var min seedade dataroot halvtömd (auth.db kvar, tenants tomt)
och gav 401. Rätt återställning: radera dataroten, starta `--seed-demo` på ny,
och kör HELA riggen via produktens egen API med curl+cookie-jar (login →
importera fakturor → importera .eml → watch-scan → godkänn förslag via
`/watches/{id}/decision` med `{"status":"approved"}` → skapa uppgift). Chatten
kräver dessutom en riktig modell: `BRF_LLM_BASE_URL`/`_MODEL`/`_RUNTIME_LABEL`
som env vid backend-start räcker INTE — desktop.py:s `apply_model_runtime`
skriver över env med den lagrade (tomma) configen, så konfigurera via
`PUT /api/desktop/model-runtime` som installationsadmin (Anna är det i seeden).
Modellen når agenntserver-lan:8000 (vLLM, gemma-4-12b) via en `ssh -L`-tunnel;
loopback-adressen godkänns av endpoint-policyn.

## Belopp är ett ord: NBSP hela vägen

"1 450,00 / SEK"-brytet kom från två håll: frontends formatAmount (vanligt
mellanslag före valutan) och backends money() i compare.py (vanliga mellanslag
även som tusentalsavgränsare). Båda satta till NBSP (\u00A0); tre backend-test
uppdaterade. testing-librarys getByText normaliserar NBSP→space, så
frontendtester berörs inte.
