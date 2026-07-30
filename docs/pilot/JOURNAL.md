# Pilotjournal — kontrollerad Fedora-pilot

Plan: [PILOTPLAN.md](PILOTPLAN.md) · Instruktion: [RUNBOOK-PILOT.md](RUNBOOK-PILOT.md)

**Produkten har ingen telemetri.** Varje mätvärde piloten kommer att kunna visa
upp finns bara därför att det skrivs in här, av operatören, efter passet. En rad
som inte skrivs är ett mätvärde som inte finns — det går inte att rekonstruera i
efterhand. Journalraden är därför sista steget i sessionschecklistan, inte något
som görs "när det finns tid".

Journalen är inte en dagbok. Den ska gå att läsa av någon som inte var med, som
underlag för BP4-avstämningarna och för BP5.

---

## Piloten i siffror

| | |
| --- | --- |
| Artefakt | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm`, SHA-256 `6ba028fb…` |
| Arkiv | `~/pilot-artefakter/` (utanför `dist/`, skrivskyddat, med `SHA256SUMS`) |
| `deliveryTree` | `a702a337…` |
| Korpus som filer | `~/pilot-korpus/` (fem PDF:er + `korpus.sha256`) |
| Modelltjänst | Gemma 4 12B på `agenntserver` via `ssh -N -L 8000:127.0.0.1:8000` |
| Modelladress i appen | `http://127.0.0.1:8000/v1` |

---

## Mätvärden (pilotplanen §7)

Uppdateras efter varje pass. `—` betyder att inget pass ännu kunnat mäta det.
Kolumnen **Slinga 3** är XS-56:s tre pass; per-pass-uppdelningen står i
[`slinga3-upprepade-arbetspass.md`](../evidence/pilot/slinga3-upprepade-arbetspass.md) §6.

| # | Mätvärde | Slinga 2 (XS-55, baslinje) | Slinga 3 (XS-56, tre pass) |
| --- | --- | --- | --- |
| M1 | Pass startade från applikationsmenyn utan terminalarbete utöver tunneln | **3 av 3 starter** — alla tre via systemd `app-BRF…@….service`, dvs. menyvägen (två under passet, en vid efterpassets återupptagande). Ingen start från terminal | **4 av 4 starter** (1 + 1 + 2), alla via KDE:s programstartare mot `.desktop`-posten, samma enhetsform `app-BRF…@….service`. Ingen start från terminal |
| M2 | Terminalingripanden under pass, och vad de gällde | **2 sanktionerade + diagnostik.** Sanktionerat: SSH-tunneln (§7 undantar den) — vid återupptagandet krävde den dessutom **ombekräftelse av Tailscale SSH i webbläsare**, en följd av värdomstarten och inte av produkten. Sanktionerat: kopiering av säkerhetskopian till annan media, vilket runbookens efterpass kräver. Diagnostiska, utförda av agenten och utan verkan på produkten: `kbuildsycoca6` (menycache — obehövlig, posten låg redan i menyn), `journalctl --user`, skrivskyddade `sqlite3`-frågor och a11y-avläsningar. **Noll terminalingripanden krävdes för att använda produkten** | **0 krävdes för att använda produkten** i alla tre passen. Sanktionerat: SSH-tunneln (§7 undantar den) — samt att stänga och öppna den i pass 2, vilket *är* felinjektionen, och att döda backenden i pass 3, likaså. Verktyg utan verkan på produkten: `ydotoold` (input-daemon), pekarprofilen på den virtuella enheten (satt + återställd), a11y- och loggavläsningar |
| M3 | Startmisslyckanden (felfönster) per pass | **0** — inget felfönster, båda instanserna nådde `status: ready` | **0 / 0 / 0.** Alla fyra instanserna nådde `status: ready`. Felfönstret i pass 3 räknas **inte** hit: det var svaret på en dödad backend, inte en misslyckad start |
| M4 | Oväntade backend-dödsfall per pass | **0** — pidbytet var en andra menystart; instans 1 avslutades rent (systemd loggade ingen `Failed`, ingen signal, ingen core-dump). Instans 2 upphörde när **värddatorn** gick ned 07:19:21; det räknas **inte** som M4, och skälet är utskrivet i avvikelsetabellen | **0 oförklarade / 0 / 0** — i pass 3 dödades backenden **avsiktligt** (`kill -TERM`, signal 15) som felinjektion C4. Stoppkriterium 7 kräver tre **oförklarade** dödsfall i samma pass |
| M5 | Fragment-faktafrågor besvarade med korrekt löst citat | **10 av 10** — samtliga citat verifierade mot extraherad sidtext | **10/10 · 10/10 · 10/10.** Två kontroller per fråga, separerade: löser citatet, *och* är svaret rätt mot facit |
| M6 | Felaktiga avvisningar | **0** — ingen fråga med stöd i korpusen avvisades | **0 / 0 / 0.** Avvisningen under leverantörsbortfallet i pass 2 är korrekt beteende, inte en felaktig avvisning |
| M7 | Fabricerade källhänvisningar | **0** — oberoende verifierat: alla 13 citat har stöd i den citerade sidan, och `arvode`/`radon` finns bevisligen inte i korpusen. **Måste förbli 0** (stoppkriterium 4) | **0 / 0 / 0** — **42 av 42** citat lösta mot extraherad sidtext över tre pass. **Måste förbli 0** (stoppkriterium 4) |
| M8 | Backup/restore-övningar och om data stämde efteråt | — *(slinga 4)* | Kopia **skapad** i pass 3 genom Appinställningar och verifierad post för post (16 filer, `unzip -t` rent, index 5/13), kopierad till annan media med matchande SHA-256. **Återställning är inte prövad** — det är slinga 4 |
| M9 | Av-/ominstallationscykler med bevarad data | — *(slinga 4)* | — *(slinga 4)* |
| M10 | Tid från okonfigurerad maskin till första grundade svar | **Mätt men ogiltigt.** Rå: 7 h 50 min 04 s — kontaminerad av ~7 h nattlig paus. Observerad **aktiv** tid till färdig installation med korpus: **≈ 35 min**, varav 7 min 30 s för att hitta menyposten. Se sönderdelningen under Pass. Omtagning kräver ny okonfigurerad installation — BP4-beslut | inte ommätt — kräver en ny okonfigurerad installation, vilket slinga 3 inte gör |

---

## Frågeuppsättningen (pilotplanen §6.3)

Femton frågor, körda genom appens AI-chatt. Första körningen **sätter** baslinjen;
därefter jämförs varje körning mot den. Ett tapp ska förklaras. En fabricerad
källhänvisning är alltid ett stopp, från första körningen.

| Datum | Fragment-fakta (av 10) | Prosa (av 2) | Obesvarbara avvisade (av 3) | Fabricerade | Anmärkning |
| --- | --- | --- | --- | --- | --- |
| **2026-07-30** | **10** | **2** besvarade med stött citat | **2** | **0** | **BASLINJEN.** u05 gav kvalificerat icke-svar med *stött* citat i stället för noll citat — avvikelse mot villkoret, inte fabricering. g17/g31/g44 överinkluderande men korrekt citerade |
| 2026-07-30 *(slinga 3, pass 1)* | **10** | **2** | **3** | **0** | 14 av 14 citat lösta. u05 avvisade nu **utan** citat → 3/3. g31 inte längre överinkluderande. **g24 svarade `SBC …`, dvs. rätt företag** — baslinjens `Driftia` var fel, se avvikelsetabellen |
| 2026-07-30 *(slinga 3, pass 2 — efter leverantörsbortfall)* | **10** | **2** | **3** | **0** | Kört **efter** att tunneln stängts och öppnats igen. Identiskt med pass 1, inklusive vilka två frågor som blir överinkluderande (g17, g44) |
| 2026-07-30 *(slinga 3, pass 3 — efter backendens död och omstart)* | **10** | **2** | **3** | **0** | Kört **efter** omstarten, medvetet placerat där (skälet i evidensfilen §5.7). Identiskt med pass 1 och 2 |

---

## Passmall

Kopiera blocket, fyll i, lägg överst under "Pass".

```
### Pass N — ÅÅÅÅ-MM-DD

Syfte:
Före passet:  tunnel uppe [ ]  probe svarar [ ]  leveransträdet a702a337… [ ]
Vad som gjordes:
Frågeuppsättning:  fragment-fakta _/10 · prosa _/2 · obesvarbara _/3 · fabricerade _
M1 start från menyn: ja/nej
M2 terminalingripanden: antal — vad de gällde
M3 felfönster: _   M4 backend-dödsfall: _
Avvikelser (S1/S2/S3):
Efter passet: säkerhetskopia skapad [ ] flyttad till annan media [ ] pgrep tomt [ ] tunnel stängd [ ]
```

---

## Avvikelser och incidenter

| Datum | Klass | Vad | Åtgärd | Status |
| --- | --- | --- | --- | --- |
| 2026-07-29 | **S2** | Korpusen uppladdad **två gånger**. Indexet innehåller 10 poster / 26 chunks i stället för 5 / 13. Två satser, 21:32–21:33 och 21:42–21:45, med bit-identiskt innehåll (samma SHA-256 per par) men olika dokument-id | Baslinjekörningen (B5) **pausad**. Dubbletterna måste bort genom produktens egen väg innan frågeuppsättningen körs, annars mäts baslinjen mot en korpus som inte är den dokumenterade | **Öppen** |
| 2026-07-29 | S3 | Produkten tog emot fem bit-identiska dubbletter utan varning eller dedupliceringsfråga | Noteras som erfarenhetsåterföring; ingen åtgärd i piloten | Öppen |
| 2026-07-29 | S3 | Pid bytte `380658` → `389858` och `backend.log.1` skapades. Operatören hade inte utfört någon omstart och kunde riktigt nog inte dra slutsatsen att processen dött | **Orsaken fastställd ur systemd-användarjournalen, inte gissad:** en **andra start från applikationsmenyn** kl. 21:41:50 (`app-BRF\x20Dokument\x2dAI@f39609c4….service`). Instans 1 avslutades **rent** 21:41:58 — systemd loggade `Consumed 29.110s CPU time over 27min 5.646s wall clock`, och **ingen** `Failed`, ingen signal, ingen core-dump. **Ingen krasch: M4 = 0** | **Stängd** |
| 2026-07-29 | S3 | `logs/backend.log` skriver rader **utan tidsstämpel**. M10:s `T1` går därför inte att läsa ur produktens egen logg | Systemd-användarjournalen fångar samma stdout **med** tidsstämpel och användes i stället. Utan den hade M10 inte kunnat mätas alls — värt att åtgärda, eftersom journalen inte är en produktgaranti | Öppen |
| 2026-07-29 | S3 | Instans 1 nådde **2,1 GB minnestopp och 787,8 MB swap** under 27 minuter (systemd `Consumed`-raden) | Noteras mot begränsning 5 (stort paket). Ingen påverkan på den här maskinen; relevant för framtida måldatorer | Öppen |
| 2026-07-30 | **S3 / F** | **Shift+Enter skickar meddelandet i stället för att radbryta.** Smoke-steg 2 underkänt. Verifierat i källkod: chattrutan är `<input type="text">` (enradig, kan inte hålla radbrytning) och `onKeyDown` saknar `shiftKey`-kontroll — `App.jsx:1522–1526` och `1107–1111`. Flerradig inmatning finns inte implementerad | **Får inte åtgärdas under piloten** — `brfv2-mockup/src` ligger i `REPRO_DELIVERY_PATHS` och en ändring skulle upphäva BP2. Klass **F**: uppföljning efter piloten. Blockerar att B3 stängs som helt godkänd, men är inget stoppkriterium | **Öppen — blockerar B3** |
| 2026-07-30 | S3 | Smoken utfördes delvis med en **input-daemon**, inte enbart fysiska knapptryck. Verktyget tappade `å`, `ö` och `?` | Två följder: (1) begränsning 3:s premiss att Wayland-injektion inte är automatiserbar motsägs delvis och bör omprövas i BP4; (2) evidensklassen är **operatörsattestering med verktygsstöd**, inte renodlad fysisk attestering, och ska stå så i BP5 | Öppen |
| 2026-07-30 | **S2 — omfångsavvikelse** | **Verkliga personuppgifter i pilotinstallationen.** Pilotplanen §2 säger `Personuppgifter \| Inga`, men installationsadministratörskontot innehåller operatörens **verkliga namn och e-postadress** (`data/auth.db`). Det var oundvikligt: uppstartsdialogen kräver namn och e-post för att skapa kontot, och piloten har en verklig operatör | **Följd för evidenshanteringen, inte för korpusen.** Korpusen är fortfarande helt syntetisk, men runbookens S1-rutin påstår att `data-snapshot` går att spara och dela *"just därför att korpusen är syntetisk"*. Det stämmer inte längre utan förbehåll: `auth.db` och varje säkerhetskopia innehåller en personuppgift. **Datakatalogen och säkerhetskopian får därför inte committas eller delas okontrollerat**, och runbookens formulering bör kvalificeras. Ingen personuppgift har nått Git — verifierat: adressen förekommer inte i `HEAD` och inte i någon evidensfil | **Öppen — dokumenterad** |
| 2026-07-29 | S3 (positivt) | Efter omstarten saknas de två `ERROR`-raderna om `BRF_LLM_BASE_URL`, eftersom adressen nu är sparad. Den självhostade klienten initierades rent | Bekräftar att konfigurationen överlever omstart | Stängd |
| 2026-07-30 | **S2 — värddator** | **Pilotmaskinen gick ned 07:19:21, med passet öppet och efterpasskontrollerna ogjorda.** Journalen slutar mitt i normal drift: ingen avstängningssekvens, ingen panic/oops/MCE, ingen OOM, ingen coredump, inget fel loggat av appens systemd-enhet. Två avsiktliga omstarter följde (båda med ren `systemd-shutdown`), därefter stabil drift | **Orsaken går inte att fastställa ur loggarna och gissas inte.** Ingenting i materialet knyter nedgången till produkten: produktens sista loggrad ligger **1 h 06 min** före värdens sista journalrad, och backend startade aldrig om av sig själv (ingen `backend.log.2`). **M4 räknas inte upp** — en avslutning orsakad av att värden försvinner är inte ett backend-dödsfall i §7:s mening. Att §7 inte skiljer på dödsfall och värdorsakad avslutning är en verklig lucka i mätdefinitionen och **tillhör BP4**. Trettio återtagningskontroller före omstart: [`slinga2-atertagning-efter-vardkrasch.md`](../evidence/pilot/slinga2-atertagning-efter-vardkrasch.md) | **Öppen — dokumenterad** |
| 2026-07-30 | S3 | **Sessionen överlever krasch och omstart.** Vid efterpassets start visades varken uppstartsdialogen eller inloggningsrutan — produkten återställde sessionen och gick rakt in i dokumentvyn. Sessionsraden skapades 21:24 dagen innan med giltighet **fjorton dagar**, och cookie-filen överlevde nedgången | **Säkerhetsdimension:** en pilotmaskin som kraschar och startar om är fortfarande inloggad, utan att någon behöver kunna lösenordet. Inget fel mot skriven kravbild, men hör hemma i BP5-underlaget för en produkt vars poäng är att data stannar lokalt. Följd här: inloggningsvägen prövades **separat** efteråt — gammal session togs bort, ny skapades, data oförändrad. En start med *utgången* session är fortfarande oprövad | Öppen |
| 2026-07-30 | S3 (positivt) | **Tillståndet överlevde nedgången intakt.** `auth.db` `integrity_check ok`, exakt en förening, ett administratörskonto, **5 dokument / 13 chunks**, dokumenten bit-identiska med `~/pilot-korpus/`, modelladressen kvar, `rpm --verify` = 0, leveransträdet `a702a337…`, Btrfs noll fel | Baslinjen kördes därför **inte** om — villkoret för omkörning är faktisk skada på data eller index, och ingen av de trettio kontrollerna visade sådan | Stängd |

| 2026-07-30 | **S3 / F** | **`Appinställningar` går inte att nå med tangentbordet.** Fokusringen i dokument-/chattvyn är en sluten cykel om sex element (uppmätt med 22 `Tab`-tryck); menyns ingång är en `<div className="user-profile">` **utan `tabIndex`** (`brfv2-mockup/src/App.jsx:863`). Menyposterna är fokuserbara först när menyn öppnats med pekare | En tangentbordsberoende operatör kan varken probe:a modelltjänsten, ändra modelladressen eller skapa säkerhetskopia. Ligger i `REPRO_DELIVERY_PATHS` → **får inte åtgärdas under piloten**. Klass **F**; BP4 bör klassa den uttryckligen | **Öppen** |
| 2026-07-30 | **S3** | **Baslinjens g24-post är sakligt fel.** XS-55 redovisade `Driftia Fastighetsservice AB` som svar på *"vilket företag sköter den **ekonomiska** förvaltningen?"* och godkände det med citatkontrollen "✓ `Driftia`". Sidan säger att Driftia sköter den **tekniska** förvaltningen och att `SBC Sveriges BostadsrättsCentrum AB` sköter den ekonomiska — vilket också är facit i `golden.json`. XS-56 svarade `SBC …` i alla tre passen | **Metodisk rot, inte tur:** citatupplösning bevisar att *citatet* har stöd, inte att *svaret* är rätt. XS-55 använde den ena slutsatsen som om den var den andra. XS-56 kör de två kontrollerna separat. Följd: XS-55:s `M5 = 10 av 10` ska läsas med förbehåll. **Inget stoppkriterium** — citatet var inte fabricerat och inget ostött svar presenterades som grundat. Rättelsen tillhör BP4 | **Öppen — BP4** |
| 2026-07-30 | S3 | **`OTILLRÄCKLIGT UNDERLAG` återanvänds som rubrik vid leverantörsfel.** Vid stängd tunnel svarade produkten `OTILLRÄCKLIGT UNDERLAG` + `Tekniskt fel vid svarsgenerering — försök igen om en stund.` Underlaget fanns; det var modellen som inte gick att nå | Beteendet är **säkert** (noll citat, inget påhittat svar) men rubriken kan få en operatör att tro att korpusen är otillräcklig när problemet är tunneln. Andra raden säger orsaken korrekt. Erfarenhetsåterföring; ingen produktändring under piloten | Öppen |
| 2026-07-30 | S3 | **`backend.log` innehåller ingen rad om backendens död.** Processen fick `SIGTERM` och hann inte skriva | Orsaken finns i produktens felfönster (`signal 15`) och i systemd-journalen, men inte i produktens egen logg. Ligger nära det öppna fyndet om saknade tidsstämplar i `backend.log` | Öppen |
| 2026-07-30 | S3 (positivt) | **Loggrotationen bevarade den kraschade instansens logg.** Efter dödandet var båda loggfilerna bit-identiska med före; vid omstarten blev den kraschade instansens `backend.log` (`4c08f922…`) till `backend.log.1` | Bevisat med SHA-256 före och efter, inte antaget. Betyder att en operatör kan läsa den döda instansens logg efter omstart, vilket felfönstret också hänvisar till | Stängd |
| 2026-07-30 | S3 | **Sessionen överlevde tre appstarter och en backendkrasch.** Ingen inloggning krävdes i något av de tre passen | Bekräftar och utökar XS-55:s observation: sessionsraden från 2026-07-29 har fjorton dagars giltighet och överlever nu även en backendkrasch. Ingen ny åtgärd; hör till BP5-underlaget | Öppen |
| 2026-07-30 | S3 *(mätmetod)* | **Sidindikatorn `Sida N av M` exponeras inte i AT-SPI**, så den klickade citatsidan kunde inte läsas som siffra | Sidan bevisades i stället genom highlight-overlayens renderingsvillkor: `PdfPane.jsx:82` renderar overlays endast när `highlightPage === clampedPage`. Begränsning i mätmetoden, inte i produkten | Öppen |
| 2026-07-30 | S3 *(miljö)* | **Pekarinjektion fungerade först efter omställning.** `ydotool`s virtuella enhet har bara relativa axlar (`EV=7`) och KDE:s adaptiva acceleration skalade rörelsen (`+100` → `88,33`, uppmätt i `libinput debug-events`). Tangentbordsinjektion fungerade direkt | Nyanserar pilotplanens begränsning 3: i den här miljön är **tangentbord** automatiserbart, **pekaren** bara efter att accelerationsprofilen satts platt på just den virtuella enheten. Inställningen återställdes och enheten finns inte längre. Rör inte produkten | Öppen |

Klasserna S1/S2/S3 definieras i pilotplanen §12. En S1 stoppar piloten och får en
egen anteckning under `docs/evidence/pilot/incident-<datum>/`.

---

## Pass

### Slinga 3 — 2026-07-30 · tre arbetspass i pilotens egen installation (XS-56)

Full evidens:
[`slinga3-upprepade-arbetspass.md`](../evidence/pilot/slinga3-upprepade-arbetspass.md).
Startpunkt `c6db95a`. Arbetskopia `brfv2-desktop-xs56`.

**Före pass 1** — artefakten och körmiljön oförändrade sedan XS-55, vilket är
varför **C5 inte utlöstes**: `webkit2gtk4.1 2.52.5-1.fc44` och
`gtk3 3.24.52-2.fc44` är samma versioner som slinga 1 och 2 noterade, så den
formella acceptansen kördes **inte** om. Vidare: arkiv-RPM `6ba028fb…`,
`rpm --verify` = 0, `deliveryTree` = `a702a337…`, leveransträdet i repot
`a702a337…`, `inspect_payload --installed` 45 kontroller / 0 fynd, korpusens fem
PDF:er OK, index 5 dokument / 13 chunks, modelladress `http://127.0.0.1:8000/v1`.
XS-55:s säkerhetskopia på annan media återkontrollerad: SHA-256 `3ec8b4c3…`
oförändrad, katalog `700`, fil `600`.

**Evidensklass.** Passen kördes av agenten genom produktens **verkliga fönster**
(start via KDE:s programstartare, frågetext via urklipp + Ctrl+V, Enter, läsning
ur a11y-trädet). Ingen fråga gick genom API:et. Det är **inte**
operatörsattestering och ska inte läsas som det; XS-55:s tangentbordssmoke står
oförändrad och är inte omprövad.

| | Pass 1 · normalt | Pass 2 · tunneln stängd (C3) | Pass 3 · backenden dödad (C4) |
| --- | --- | --- | --- |
| Start | 12:13:43 | 12:46:39 | 12:56:35 (+ omstart 12:58:49) |
| Frågeuppsättning | 10/10 · 2/2 · 3/3 · 0 fabr. | 10/10 · 2/2 · 3/3 · 0 fabr. | 10/10 · 2/2 · 3/3 · 0 fabr. |
| Citat lösta | 14/14 | 14/14 | 14/14 |
| M1 | ja (1/1) | ja (1/1) | ja (2/2) |
| M2 | 0 krävdes | 0 krävdes | 0 krävdes |
| M3 / M4 | 0 / 0 | 0 / 0 | 0 / 0 oförklarade *(1 avsiktligt)* |

**Pass 2 — leverantörsbortfall.** Tunneln stängdes 12:48:07 med passet öppet;
port 8000 slutade lyssna och `curl` gav `000`. En fråga **med stöd i korpusen**
(g35, samma som pass 1 besvarade med löst citat) gav då `OTILLRÄCKLIGT UNDERLAG`
+ `Tekniskt fel vid svarsgenerering — försök igen om en stund.`, **noll citat**,
inget grundat-utseende svar och ingen fabricerad källhänvisning. Produktens logg:
`ERROR brf.answer: … Kunde inte nå LLM-servern (http://127.0.0.1:8000/v1):
ConnectError`. **Ingen annan värd kontaktades** — samtliga URL:er i loggen är
`http://127.0.0.1:8000`. Tunneln öppnades 12:48:54, proben i Appinställningar
kördes om (`200 OK`), och uppsättningen gav samma utfall som pass 1. Ingen
dataskada: 5/13, `auth.db` `ok`, fem av fem PDF:er bit-identiska.

**Pass 3 — backenden dödad.** `kill -TERM` mot pid `139757`, alltså den process
som *är* backenden (`app.desktop`, ägare av lyssnaren på `127.0.0.1:39105`) —
inte skalet. Utfall: arbetsfönstret **stängdes**, skalprocessen levde vidare och
visade produktens **eget** felfönster med titeln `BRF Dokument-AI — kunde inte
starta`, rubriken *Applikationen tappade sin bakgrundstjänst* och under **TEKNISK
ORSAK** meningen *"Bakgrundstjänsten avslutades av **signal 15**"* — den faktiska
orsaken, inte en generisk text — jämte påståendet att data ligger kvar, sökvägen
till loggen och tre steg vidare. Loggarna var **bit-identiska** med före
(`4c08f922…`, `c979d759…`), och vid omstarten bevarade rotationen den kraschade
instansens logg som `backend.log.1`. Hela `data/`-trädets SHA-256 var
**oförändrat** (`23e27246…`): föreningen, kontot, de fem dokumenten och de tretton
chunkarna låg kvar in på byten. Efter omstart från menyn gav g19
`Årets resultat blev -142 000 kronor.` med citat till Årsredovisning 2025 s. 2,
oberoende löst mot sidans extraherade text; klick på citatet öppnade rätt dokument
med markeringen renderad.

**Varför uppsättningen kördes efter omstarten i pass 3.** Före dödandet hade den
mätt om samma tillstånd en tredje gång. Efter omstarten prövar den passets enda
egentliga fråga: kommer produkten tillbaka *hel* — och hela uppsättningen mot alla
fem dokumenten är ett starkare belägg för att indexet är oskadat än ett enstaka
lyckat svar. Skälet står också i evidensfilen §5.7.

**Inget stoppkriterium i §8 inträffade.** Alla sju prövades var för sig; tabellen
står i evidensfilen §7.1. Särskilt: 42 av 42 citat lösta (kriterium 4), `0 fynd`
i `inspect_payload --installed` (kriterium 3), och enbart
`http://127.0.0.1:8000` i loggarna (kriterium 2).

**Efter passen:** fönstren stängda med produktens egen `Close`,
`pgrep -f brfv2-desktop` tomt, systemd-enheterna borta, tunneln stängd,
input-daemonen stoppad. Säkerhetskopia skapad i pass 3 genom Appinställningar
(`brfv2-backup-20260730-110753-c54d.zip`, 16 filer, `unzip -t` rent, index 5/13)
och kopierad till annan media (`agenntserver:~/pilot-sakerhetskopior/`, katalog
`700`, fil `600`) med **matchande SHA-256 lokalt och på fjärrsidan**
(`e7fd00d4…`). Kopian är **inte** committad. Återställning är oprövad — det är
slinga 4.

**BP4-3-rekommendation: passera och gå vidare till slinga 4.** Fyra punkter som
BP4 bör *besluta* om, inte bara notera: rättelsen av g24 plus metodregeln att
citatupplösning och svarsriktighet är två kontroller; villkoret för obesvarbara
frågor; klassningen av tangentbordsotillgängligheten i Appinställningar; och en
`M4`-definition som skiljer oförklarade dödsfall från förklarade. Motiveringen
står i evidensfilen §9.

---

### Slinga 2 / Pass 1 — 2026-07-29 · första start (PÅGÅENDE)

**Status: öppen.** Raden är skriven före första start, som pilotplanen §7 kräver —
mätvärdena finns bara om de skrivs ned, och de kan inte rekonstrueras i efterhand.
Fälten nedan fylls i under passets gång. Ett fält som står `—` är inte mätt, och
får inte fyllas i från minnet.

Syfte: B1–B5 i pilotplanen §5 — från okonfigurerad maskin till första grundade
svar, utan terminalarbete utöver SSH-tunneln.

**Före passet** *(verifierat 19:31–19:34, evidens:
[`slinga2-forstastart.md`](../evidence/pilot/slinga2-forstastart.md) B0/B1)*:

- [x] tunnel uppe — `127.0.0.1:8000` lyssnar, `ExitOnForwardFailure=yes`
- [x] probe svarar — `/v1/models` annonserar `gemma-4-12b-it-UD-Q4_K_XL.gguf`
- [x] leveransträdet `a702a337…` oförändrat
- [x] `rpm --verify` = 0 · `deliveryTree` = `a702a337…` · skal `d3cb3c02…`
- [x] `inspect_payload --installed` 45 kontroller / 0 fynd
- [x] arkivet `6ba028fb…` OK · korpusen fem PDF:er OK
- [x] **datakatalogen saknas** — starten är en genuin förstagångsstart
- [x] `webkit2gtk4.1 2.52.5-1.fc44`, `gtk3 3.24.52-2.fc44` (oförändrade sedan slinga 1)
- [x] **formell pilotacceptans grön (§6.1)** — exitkod 0, 129,9 s, alla fyra faser
      (`uiJourney`, `lifecycle`, `securityBoundary`, `failureSurfaces`),
      `modelService.baseUrl` = `http://127.0.0.1:8000/v1` med Gemma 4 12B,
      `bundle.deliveryTree` = `a702a337…`

Därmed är §11:s engångschecklista inför pilotstart avbockad i sin helhet.
Acceptansen kördes **19:38:43–19:40:53**, före första start, efter beslut av
operatören. Den kunde köras utan att förbruka förstagångsstarten därför att den kör
i ett eget `XDG_DATA_HOME` under `/tmp/brfv2-acceptance-*`
(`desktop_acceptance.py:378,1861`). Kontrollerat efteråt: datakatalogen saknades
fortfarande och den isolerade katalogen var uppstädad.

A3-åtgärden bekräftad i skarp körning: evidensen namngavs
`xs55-slinga2-installed-*` av `--run-label` och rörde inte den committade
`xs49-*`-evidensen.

**M10-klockan.** Två tidpunkter förs, därför att de mäter olika saker och att
blanda ihop dem vore att överdriva precisionen:

| | Definition | Värde |
| --- | --- | --- |
| `T0_förberedd` | Alla kontroller gröna, tunneln uppe, acceptansen grön, journalen skriven, operatören vid tangentbordet med handen på menyn | **2026-07-29 21:07:22 +02:00** |
| `T0_operatör` | Operatören startar faktiskt appen från menyn. Avläses objektivt ur datakatalogens skapelsetid | **2026-07-29 21:14:52.838** |
| `T1` | Första grundade svaret med löst citat i gränssnittet | **2026-07-30 04:57:26** |

### M10 — värdet går inte att använda som friktionsmått, och det ska stå så

| Definition | Värde |
| --- | --- |
| `T1 − T0_förberedd` (goalens definition) | **7 h 50 min 04 s** |
| `T1 − T0_operatör` | 7 h 42 min 34 s |

**Båda talen är kontaminerade av en nattlig paus och mäter förfluten tid, inte
operatörsfriktion.** Att redovisa 7 h 50 min som "tid från okonfigurerad maskin
till första grundade svar" vore vilseledande. Händelsekedjan, avläst ur
systemd-journalen och filsystemet, visar var tiden faktiskt låg:

| Klockslag | Händelse | Källa |
| --- | --- | --- |
| 21:07:22 | `T0_förberedd` | stämplad |
| 21:14:52 | start från applikationsmenyn (instans 1) | systemd `app-BRF…@0e6ef76f…` |
| 21:14:53 | readiness-kontraktet `status: ready`, port 55319 | stdout |
| ~21:24 | förening skapad (`tenants/fredling`) | katalogens mtime |
| 21:25:38 | modelladress satt + probe `200 OK` | journal |
| 21:32:44–21:33:14 | fem dokument uppladdade (sats 1) | `documents.json` |
| 21:41:50 | andra start från applikationsmenyn (instans 2) | systemd `app-BRF…@f39609c4…` |
| 21:41:58 | instans 1 avslutas rent | systemd `Consumed …` |
| 21:42:13–21:42:45 | fem dokument uppladdade (sats 2 — dubbletterna) | `documents.json` |
| *(≈7 h 15 min utan aktivitet)* | passet vilade över natten | — |
| 04:57:26 | **första grundade svaret** (smoke steg 7) | journal, `POST /v1/chat/completions 200 OK` |

**Observerad aktiv tid från förberedd maskin till färdig installation med korpus:
≈ 35 minuter** (21:07:22 → 21:42:45), varav 7 min 30 s gick till att hitta
menyposten.

Det är den siffran som säger något om friktion. Den är däremot **inte** M10 som
pilotplanen §7 definierar den, och den får inte redovisas som om den vore det.
M10 mäts en enda gång i slinga 2, och den möjligheten är nu förbrukad utan ett
användbart värde. **M10 redovisas därför som "mätt men ogiltigt"**, med
komponenterna ovan, och beslutet om en omtagning tillhör BP4 — inte den här
sessionen.

`M10` rapporteras som `T1 − T0_förberedd` (goalens definition) **och** som
`T1 − T0_operatör` (den tid operatören faktiskt arbetade). Skillnaden är väntetid
på människan och ska inte döljas i ett enda tal.

*Notering om `T0_förberedd` — två omstämplingar, båda redovisade:*

| Stämpel | Satt | Varför den ersattes |
| --- | --- | --- |
| 19:35:29 | efter B0/B1 | Operatören beslutade att den formella acceptansen skulle köras före första start. Acceptansen (129,9 s) är förberedelse, inte konfiguration |
| 19:52:07 | efter att acceptansen lästs som grön (körd 19:38:43–19:40:53) | Operatören var ännu inte vid tangentbordet; mellanliggande tid är väntan på människan, inte arbete med produkten |
| 20:28:39 | operatören anmälde sig redo | **Underkänd av operatören.** Mellan stämpeln och första knapptryck låg felsökning av menyposten och väntan på agentsvar i chatten. Den tiden är inte operatörens arbete med produkten och får inte belasta M10 |
| **21:07:22** | operatören med handen på menyn, omedelbart före första knapptryck | **Gällande.** Härifrån mäts M10 |

Stämplarna redovisas i stället för att tyst skrivas över. M10 ska mäta tiden från
en förberedd men okonfigurerad maskin till första grundade svar — inte
acceptansens körtid och inte väntan på att operatören ska bli ledig. Att alla tre
står här är det som gör att en läsare kan kontrollera att inget gömts undan.

**Avvikelse mot goalens stegordning (dokumenterad, inte tyst).** Goalen listar
tangentbordssmoken (steg 6) före uppladdningen (steg 7). Runbookens egna smoke-steg
gör den ordningen fysiskt omöjlig: steg 6 kräver en PDF-vy och steg 7 ett citat som
löser till en sida, och ingetdera finns innan dokument är uppladdade. Smoken delas
därför vid sin naturliga skarv:

1. uppstartsdialog → 2. smoke steg **1–5 och 8** → 3. uppladdning av fem PDF:er →
4. smoke steg **6–7** → 5. frågeuppsättningen.

Ingen smoke-punkt utgår; två flyttas efter uppladdningen därför att de annars inte
går att utföra. Skälet är observerat i runbookens text, inte antaget.

### Frågeuppsättningen — baslinjekörning (B5)

Facit nedan är läst ur `backend/eval/golden.json` och stämmer med pilotplanen
§6.3 för alla femton. Sidnumren är kontrollerade mot PDF:erna: Stadgar 3 s.,
Årsredovisning 3 s., Protokoll 2 s., Snöröjningsavtal 2 s., Underhållsplan 3 s. —
varje citerad sida finns.

Körd 2026-07-30 av operatören genom appens AI-chatt. Kolumnen **Citat verifierat**
är agentens oberoende kontroll: sidans text rekonstruerades ur
`data/tenants/fredling/extract/<id>.json` (ord med koordinater) och den citerade
uppgiften söktes i den. Det är alltså inte operatörens bedömning som avgör om ett
citat har stöd.

| id | Facit | Svar (kort) | Citerat dokument | Sida | Citat verifierat | Utfall |
| --- | --- | --- | --- | --- | --- | --- |
| g09 | Stadgar s. 2 | lägst 3, högst 5 ledamöter + högst 2 suppleanter | Stadgar | 2 | ✓ `ledamöter`, `suppleant` | **✅** |
| g17 | Årsredovisning s. 1 | etapp 1 = 1 850 000 kr; etapp 2 beräknad 1 900 000 kr | Årsredovisning; Underhållsplan | 1; 2 | ✓ `1 850 000`, `relining` | **✅** *(överinkluderande)* |
| g19 | Årsredovisning s. 2 | −142 000 kr | Årsredovisning | 2 | ✓ `142 000` | **✅** |
| g24 | Årsredovisning s. 1 | Driftia Fastighetsservice AB | Årsredovisning | 1 | ✓ `Driftia` | **✅** |
| g28 | Protokoll s. 1 | Måleri Väst AB | Styrelseprotokoll | 1 | ✓ `Måleri Väst` | **✅** |
| g31 | Protokoll s. 2 | 96 000 kr (Chargepark); tog även upp fasadoffert 450 000 kr | Styrelseprotokoll | 2; 1 | ✓ `96 000`, `Chargepark` | **✅** *(överinkluderande)* |
| g35 | Snöröjningsavtal s. 1 | utryckning vid 5 cm snödjup | Snöröjningsavtal | 1 | ✓ *"snödjup om 5 centimeter"* | **✅** |
| g37 | Snöröjningsavtal s. 2 | 1 250 kr/tim exkl. moms | Snöröjningsavtal | 2 | ✓ `1 250` | **✅** |
| g44 | Underhållsplan s. 3 | år 2032 | Underhållsplan | 3 och 1 | ✓ `2032`, `stambyte` | **✅** *(överinkluderande)* |
| g45 | Underhållsplan s. 3 | 8 500 000 kr | Underhållsplan | 3 | ✓ `8 500 000` | **✅** |
| g05 | Stadgar s. 2 *(prosa)* | skriftligt samtycke från styrelsen | Stadgar | 2 | ✓ `samtycke`, `andra hand` | **✅** |
| g25 | Underhållsplan s. 1 *(prosa)* | revideras vart tredje år | Underhållsplan | 1 | ✓ `tredje` | **✅** |
| u02 | *obesvarbar* | **OTILLRÄCKLIGT UNDERLAG** — inget arvode anges | inget citat | – | ✓ `arvode` **finns inte i korpusen** | **✅** |
| u05 | *obesvarbar* | "inget specifikt datum framgår; stämman hålls årligen före juni månads utgång" | Stadgar | 3 | ✓ *"§ 11 … hålls årligen före juni månads utgång"* | **⚠️ avvikelse** |
| u08 | *obesvarbar* | **OTILLRÄCKLIGT UNDERLAG** — radonresultat saknas | inget citat | – | ✓ `radon` **finns inte i korpusen** | **✅** |

### Baslinjen

| Kategori | Utfall | Krav |
| --- | --- | --- |
| Fragment-fakta med korrekt löst citat | **10 / 10** | alla 10 |
| Prosakontroller | **2 / 2 besvarade med stött citat** | fick avvisas — behövde inte |
| Obesvarbara avvisade med noll citat | **2 / 3** | 3 |
| **Fabricerade källhänvisningar** | **0** | måste vara 0 |

### u05 — avvikelsen, och varför den inte är ett fel i produkten

Testfallet kräver `OTILLRÄCKLIGT UNDERLAG` och **noll citat**. Produkten gav i
stället ett kvalificerat icke-svar med ett citat.

Kontrollen av Stadgar s. 3 visar att citatet har **fullt stöd**:

```
§ 11 Föreningsstämma
Ordinarie föreningsstämma hålls årligen före juni månads utgång.
```

Produkten hittade alltså inte på något. Den sa uttryckligen att **datumet för
2026 inte framgår** — vilket är sant, det finns inte i korpusen — och redovisade
den regel som faktiskt står där, med korrekt sidhänvisning.

**Stoppkriterium 4 utlöstes inte.** Ingen fabricerad källhänvisning, inget
ostött svar presenterat som grundat.

Men uppsättningen ska köras **oförändrad** (pilotplanen §6), och dess
godkännandevillkor för obesvarbara är noll citat. Utfallet räknas därför som
**2 av 3**, inte 3 av 3. Att i efterhand omdefiniera villkoret till "avvisad
eller kvalificerad med stött citat" vore precis den sortens efterrationalisering
§6 finns för att förhindra. **Frågan om villkoret bör skrivas om tillhör BP4** —
den kan inte avgöras av den som just körde testet.

### Överinkludering — g17, g31, g44

Tre svar tog upp mer än frågan bad om (angränsande offert, etapp 2, extra
sidhänvisning). Samtliga tillagda uppgifter var **korrekt citerade och stödda**.
Det är alltså inte fabricering, men det är ett brusmönster värt att följa: en
operatör som frågar om laddstolpar får också fasadmålning i svaret. Klass **S3**,
underlag till erfarenhetsåterföringen.

### Tangentbordssmoke — operatörsattestering (B3)

Evidensklass: **operatörsattestering**, inte automatkörning. Ska stå så även i
BP5-underlaget (pilotplanen §6.4).

| Steg | Vad | Utfall | Attestering |
| --- | --- | --- | --- |
| 1 | Fråga + Enter skickar | **GODKÄND** | Frågan skickades som ett enda meddelande, fältet tömdes, svar kom. Ingen radbrytning, ingen försvunnen text. Teststrängen återgavs `Vad ar jourperioden_` — verktygsartefakt i layouten, se nedan; Enter-beteendet var entydigt |
| 2 | Skift+Enter ger radbrytning | **UNDERKÄND** | `Frsta raden` skickades omedelbart som användarmeddelande, fältet tömdes, modellen svarade. Reproducerat. **Bekräftat i källkoden** — se fyndet nedan |
| 3 | Tab: synlig fokusring, begriplig ordning | **GODKÄND** | Ordning: chattinmatning/skicka → `Dokument` → `AI-chatt`. Båda navigationsknapparna fick tydlig blå fokusring |
| 4 | Escape stänger dialog | **GODKÄND** | Raderingsdialogen för `Snöröjningsavtal 2026.pdf` öppnad (a11y-trädet: `Ta bort dokument?`), Escape stängde den. Tabellen hade fortfarande rubrikrad + fem dokumentrader — **inget raderades** |
| 5 | Markering + Ctrl+C följer med till annan app | **GODKÄND** | Del av AI-svaret markerad, Ctrl+C, inklistrad i KWrite med Ctrl+V. UTF-8 följde med korrekt, inklusive `löper` och `från` |
| 6 | Zoom i PDF-vyn ändrar zoomnivå | **GODKÄND** | `Snöröjningsavtal 2026.pdf` öppnad, `100 %` → knappen **Zooma ut** → `90 %`, sidan skalades synligt om, därefter återställd till `100 %` |
| 7 | Klickat citat visar rätt sida med markering | **GODKÄND** | Frågan *"Vilka datum gäller för snöröjningsjouren?"* gav *"Jourperioden löper från den 15 november till den 15 april."* med klickbart citat till `Snöröjningsavtal 2026.pdf` s. 1. Klick öppnade rätt dokument på **sida 1 av 2**, citerad mening orange-markerad |
| 8 | ≈1000×700: ingen horisontell scroll | **GODKÄND** | Fönstret satt till exakt 1000×700. Innehållet flödade om, chattfältet förblev synligt, **ingen horisontell rullning**. Endast normal vertikal rullning. Återställt till 1440×920 efteråt |

Attesterad av: Simon Fredling Jack · datum: 2026-07-30 · **7 av 8 godkända**

### Fynd: Shift+Enter skickar i stället för att radbryta

**Klass: produktbrist, verifierad i källkod. Inte ett stoppkriterium.**

Operatörens observation ifrågasattes först, eftersom steg 2 är det enda som beror
på en modifierartangent och injektionsverktyget bevisligen tappade tecken
(`å` → `a`, `ö` → borta, `?` → `_`). Om Shift inte levererats hade appen sett ett
rent Enter och skickat *korrekt*. Kontrollen gjordes därför i koden i stället:

`brfv2-mockup/src/App.jsx:1522–1526` (allmänna AI-chatten) och `1107–1111`
(dokumentbunden chatt):

```jsx
<input
  type="text"
  value={chatInput}
  onKeyDown={(e) => e.key === 'Enter' && executeGeneralChat(chatInput)}
```

Två oberoende orsaker, båda strukturella:

1. **Kontrollen är `<input type="text">`, inte `<textarea>`.** Ett enradigt fält
   kan inte innehålla en radbrytning — det finns ingen plats att lägga den.
2. **Handlaren saknar `shiftKey`-kontroll.** Varje `Enter` skickar, oavsett
   modifierare. (Jämför rad 289, där `e.shiftKey` *används* korrekt för
   Tab-navigering — mönstret finns i kodbasen, men inte här.)

Att lägga till en `shiftKey`-kontroll skulle alltså inte ge en radbrytning, bara
göra att ingenting händer. **Flerradig inmatning finns inte implementerad.**

Runbookens smoke-steg 2 beskriver därmed en förmåga produkten inte har och,
givet `<input type="text">`, aldrig har haft. Antingen är runbookens förväntan
felskriven eller så saknas flerradig inmatning. Det är en fråga för BP4, inte för
den här sessionen.

**Får inte åtgärdas under piloten.** `brfv2-mockup/src` ligger i
`REPRO_DELIVERY_PATHS` (pilotplanen §4.1). En rättelse skulle flytta artefaktens
bytes och upphäva BP2-underlaget. Klassas som **F — uttrycklig uppföljning efter
piloten**.

### Evidensklassens gräns: injektionsverktyg, inte bara fysiskt tangentbord

Operatören använde en input-daemon för delar av smoken, inte enbart fysiska
knapptryck. Två konsekvenser som måste stå skrivna:

* **Begränsning 3 i pilotplanen §9 säger att fysisk Wayland-tangentbordsinjektion
  inte är automatiserbar i den här miljön.** Att injektion faktiskt gick att
  utföra motsäger den premissen delvis och bör omprövas i BP4.
* **Verktyget är samtidigt inte tillförlitligt nog att ersätta människan.** Det
  tappade `å`, `ö` och `?`. Steg 1 och 2:s teststrängar bär spår av det. För
  steg 2 spelar det ingen roll — källkoden avgör oberoende — men för övriga steg
  är evidensklassen **operatörsattestering med verktygsstöd**, inte renodlad
  fysisk attestering, och ska stå så i BP5-underlaget.

Steg 7 satte samtidigt `T1` för M10 — det är både smoke-evidens och mätpunkt.

**Vad som gjordes:** B1 tunnel + Gemma 4 12B verifierad · formell pilotacceptans
(§6.1) grön före första start · B2 genuin förstagångsstart från applikationsmenyn,
förening + installationsadministratör + modelladress `http://127.0.0.1:8000/v1`
med `200 OK`-probe · B3 tangentbordssmoke 7/8 · B4 fem dokument uppladdade genom
produktens egen väg (dubbletter upptäckta och åtgärdade) · B5 frågeuppsättningen
körd, baslinjen satt och citaten oberoende verifierade mot extraherad sidtext.

Frågeuppsättning: fragment-fakta **10**/10 · prosa **2**/2 · obesvarbara **2**/3 · fabricerade **0**
M1 start från menyn: **ja — 2 av 2 starter**, båda via systemd `app-BRF…@….service`
M2 terminalingripanden: **0 krävdes för att använda produkten.** SSH-tunneln (sanktionerad, §7) + två diagnostiska agentkommandon utan verkan (`kbuildsycoca6`, `journalctl`)
M3 felfönster: **0**   M4 backend-dödsfall: **0** *(värddatorns nedgång räknas inte in — se avvikelsetabellen)*
Avvikelser: **3 S2** (dubblerad korpus — åtgärdad · verkliga personuppgifter i installationen · värddatorn gick ned med passet öppet) · **9 S3** (Shift+Enter, verktygsberoende attestering, dubbletter utan varning, odokumenterade WebKit-kataloger, `ERROR`-nivå vid förväntat förstagångsläge, saknade tidsstämplar i `backend.log`, minnestopp 2,1 GB, överinkluderande svar, sessionen överlever krasch och omstart i fjorton dagar — plus två positiva: konfigurationen överlever omstart, tillståndet överlevde nedgången)
Efter passet: säkerhetskopia skapad [x] flyttad till annan media [x] pgrep tomt [x] tunnel stängd [x]

*Skrivet 2026-07-30 kl. ~06, medan passet fortfarande pågick — och medvetet
bevarat, eftersom det är anteckningen som gör kronologin läsbar:*

**Passet är inte formellt avslutat.** De fyra efterpasskontrollerna ovan
återstår och kräver operatören. Passet skapade ny data — fem dokument, ett konto,
en förening — så säkerhetskopian är obligatorisk enligt runbooken. Appen kördes
fortfarande under pid `389858` och tunneln var uppe när detta skrevs; avslutet är
operatörens beslut och görs inte av agenten.

**Efterpasset avbröts av att värddatorn gick ned 2026-07-30 07:19:21**, med appen
igång och tunneln uppe. Ingen av de fyra kontrollerna hann utföras: **ingen
säkerhetskopia fanns när maskinen försvann.** Det är passets verkliga risk
förverkligad — hade datakatalogen skadats hade B2–B5 fått göras om, och slinga 2:s
förstagångsstart går inte att göra om.

Den gick inte förlorad. Trettio kontroller före omstart visar tillståndet oskadat
(`5` dokument, `13` chunks, en förening, ett administratörskonto, modelladressen
kvar, leveransträdet `a702a337…`) — se
[`slinga2-atertagning-efter-vardkrasch.md`](../evidence/pilot/slinga2-atertagning-efter-vardkrasch.md).
**Nedgången knyts inte till produkten**, och **`M4` står kvar på `0`**: en
avslutning orsakad av att värden försvinner är inget backend-dödsfall i §7:s
mening, och det finns inget stöd för att backend dog dessförinnan. Efterpasset
återupptogs därifrån, inte om.

**Efterpasset genomfört 2026-07-30 09:30–09:55** *(evidens: samma fil, avsnitt 4)*:
tunneln åter uppe mot **samma modellsnapshot `d997c805…`** som B1 · start från
applikationsmenyn 09:36:50, `status: ready` · **uppstartsdialogen visades inte**,
och `auth.db` var orörd av starten · **inloggningsrutan visades inte heller** —
produkten återställde sessionen och gick rakt in i dokumentvyn (nytt S3) ·
säkerhetskopia skapad genom gränssnittet, verifierad post för post och kopierad
till `agenntserver:~/pilot-sakerhetskopior/` med `0700`/`0600` och **identisk
SHA-256** · inloggningsvägen därefter prövad separat och **godkänd** (gammal
session borttagen, ny skapad, data oförändrad) · appen stängd normalt, enheten
avslutad rent, `pgrep` tomt, tunneln stängd · regression **657/3** mot arkivets
RPM och A3-skyddet 7/7 · leveransträdet `a702a337…`.

**Passet är därmed formellt avslutat.** Kvar som öppen punkt är enbart B3:s
Shift+Enter-fel, som tillhör BP4.

**Kvarstående för att B3 ska kunna stängas:** Shift+Enter-felet är verifierat och
klassat **F** (uppföljning efter piloten, får inte åtgärdas nu — `brfv2-mockup/src`
ligger i `REPRO_DELIVERY_PATHS`). Beslutet om B3 kan godkännas med 7 av 8 tillhör
BP4.

---

### Slinga 1 — 2026-07-29 · miljön upprättad (inget pilotpass)

Detta är inget arbetspass med produkten: applikationen startades aldrig,
datakatalogen skapades inte och ingen fråga ställdes. Raden finns för att slingan
ska vara journalförd, inte för att den mätte något.

Utfört (evidens: [`docs/evidence/pilot/slinga1-startevidens.md`](../evidence/pilot/slinga1-startevidens.md)):

* **A1** — artefakten ombyggd i ren checkout av `84b6fc8`; SHA-256
  `6ba028fb…` identisk med den BP2 godkända; arkiverad skrivskyddad i
  `~/pilot-artefakter/` med kvitto och `SHA256SUMS`. Arkivets RPM-header är
  densamma som den installerade (`5fc97bce…`) — arkivet och installationen är
  samma artefakt.
* **A2** — baslinjekontrollerna omkörda: `rpm --verify` = 0, installationens
  `deliveryTree` = `a702a337…`, `inspect_payload --installed` 45 kontroller /
  0 fynd, ingen datakatalog ännu, 356 GB fritt. `webkit2gtk4.1 2.52.5-1.fc44`
  och `gtk3 3.24.52-2.fc44` noterade (risk R1).
* **A3** — acceptansens `xs49-*`-namngivning borta; evidensen namnges av
  `--run-label`, och committad evidens stoppar körningen om inte
  `--overwrite-evidence` anges. Leveransträdet oförändrat före och efter.
  Regression: 657/3 backend (baslinjens 650 + 7 nya tester för just det här
  skyddet), 21 frontend, 11 e2e, 5 Rust, lint rent.
* **A4** — korpusens fem PDF:er utskrivna till `~/pilot-korpus/`, deterministiskt
  (andra körningen: alla oförändrade), med `korpus.sha256`.
* **A5** — den här journalen upplagd.

M1–M10: inget mätt. Terminalingripanden räknas inte i slinga 1 — slingan *är*
terminalarbete, och den mäter inte operatörsfriktion.

Kvar innan första passet (slinga 2): SSH-tunneln uppe och Gemma 4 12B
annonserad, formell pilotacceptans grön (§6.1), mänsklig tangentbordssmoke
attesterad (§6.4). Ingen av dem kunde göras i slinga 1 — acceptansen kräver en
nåbar modelltjänst och tunneln var nere.
