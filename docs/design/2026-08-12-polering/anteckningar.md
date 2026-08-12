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

## Belopp är ett ord: NBSP hela vägen

"1 450,00 / SEK"-brytet kom från två håll: frontends formatAmount (vanligt
mellanslag före valutan) och backends money() i compare.py (vanliga mellanslag
även som tusentalsavgränsare). Båda satta till NBSP (\u00A0); tre backend-test
uppdaterade. testing-librarys getByText normaliserar NBSP→space, så
frontendtester berörs inte.
