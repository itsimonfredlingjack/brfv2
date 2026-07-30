# Slinga 3 — upprepade arbetspass i pilotens egen installation (XS-56)

Plan: [PILOTPLAN.md](../../pilot/PILOTPLAN.md) §5 (slinga 3), §6.3 (frågeuppsättningen),
§7 (mätetal), §8 (stoppkriterier) · Instruktion:
[RUNBOOK-PILOT.md](../../pilot/RUNBOOK-PILOT.md) · Journal:
[JOURNAL.md](../../pilot/JOURNAL.md)

Startpunkt: commit `c6db95a55cdfa82898acc3f6dd5b663e90330fe3` (XS-55, fryst).
Arbetskopia: `brfv2-desktop-xs56`.

---

## 0. Vad den här filen bevisar — och vad den inte bevisar

**Bevisar:** att produkten beter sig som acceptansen lovar i pilotens *egen*
installation, med pilotens *egen* data, över **tre** på varandra följande
arbetspass; och att de två felinjektionerna (leverantörsbortfall, backendens död)
ger säkert beteende utan påhittade svar och utan dataskada.

**Bevisar inte:**

* att svaren håller mot verkliga stadgar och årsredovisningar — korpusen är
  syntetisk (pilotplanen §2, oförändrat);
* att en människa vid ett fysiskt tangentbord upplever samma sak. Passen kördes
  av agenten genom produktens verkliga fönster, se evidensklassen i §2;
* något om andra maskiner, andra OS eller bred distribution (§2 exkluderingar).

---

## 1. Baslinjekontroll före pass 1

Artefakten och körmiljön är **oförändrade** sedan XS-55. Därför utlöses **inte**
arbetspunkt C5 (omkörning av den formella acceptansen), vars villkor är att
`webkit2gtk4.1` eller `gtk3` bytt version.

| # | Kontroll | Kommando/källa | Utfall | Krav | ✓ |
| --- | --- | --- | --- | --- | --- |
| 1 | Arkiverad RPM | `sha256sum ~/pilot-artefakter/*.rpm` | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` | `6ba028fb…` | ✅ |
| 2 | Installerat träd = paket | `rpm --verify brf-dokument-ai` | exitkod `0`, ingen rad | `0` | ✅ |
| 3 | Installationens identitet | `BUNDLE.json.deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |
| 4 | Leveransträdet orört i repot | kommandot i pilotplanen §4.1 | `a702a337…` (identisk) | `a702a337…` | ✅ |
| 5 | Leverantörsgräns, installerat | `ops/inspect_payload.py --installed --scope installed` | `kontroller: 45 … fynd: 0` (4675 filer) | 45 / 0 fynd | ✅ |
| 6 | `webkit2gtk4.1` | `rpm -q` | `2.52.5-1.fc44` | = XS-55 | ✅ |
| 7 | `gtk3` | `rpm -q` | `3.24.52-2.fc44` | = XS-55 | ✅ |
| 8 | Korpus som filer | `sha256sum -c ~/pilot-korpus/korpus.sha256` | fem `OK` | fem OK | ✅ |
| 9 | Index i installationen | `documents.json` | **5 dokument / 13 chunks** | 5 / 13 | ✅ |
| 10 | Modelltjänst | `/v1/models` via tunneln | `gemma-4-12b-it-UD-Q4_K_XL.gguf` | Gemma 4 12B | ✅ |
| 11 | Modelladress i appen | Appinställningar → ADRESS | `http://127.0.0.1:8000/v1` | oförändrad | ✅ |
| 12 | Föregående säkerhetskopia, off-machine | `agenntserver:~/pilot-sakerhetskopior/` | `brfv2-backup-20260730-074335-fd3e.zip`, katalog `700`, fil `600`, SHA-256 `3ec8b4c331f063532ebd5bbca92fadbf3f7486e05740a76ee3dde0890d448719` | = XS-55:s summa | ✅ |

Punkt 12 är XS-55:s kopia, återkontrollerad — **inte** en ny. Summan är identisk
med den XS-55 skrev ned, vilket innebär att återställningspunkten piloten lutar
sig mot fortfarande finns och fortfarande är oskadad.

Dokumentens `chunks` per fil: Årsredovisning 3, Snöröjningsavtal 2, Stadgar 3,
Styrelseprotokoll 2, Underhållsplan 3 — summa **13**.

---

## 2. Metod och evidensklass

Passen kördes genom produktens **verkliga fönster** på pilotmaskinen. Ingen fråga
gick genom API:et; varje fråga skrevs in i AI-chattens fält och skickades med
**Enter**, och varje svar och citat lästes ur det renderade gränssnittet.

| Del | Hur | Varför så |
| --- | --- | --- |
| Start | KDE:s egen programstartare mot `/usr/share/applications/BRF Dokument-AI.desktop` | ger exakt den systemd-enhet menyvalet ger: `app-BRF\x20Dokument\x2dAI@<hex>.service` — samma form som XS-55:s tre starter |
| Inmatning av frågetext | urklipp (`wl-copy`) + **Ctrl+V**, därefter **Enter** | tangentbordsinjektion tappar `å`, `ö` och `?` i den här miljön (XS-55:s S3-fynd). Klistring gör frågetexten **byte-exakt**, vilket §6 kräver ("körd oförändrad"). Varje fråga kontrollerades i fältet före Enter — `field_verified` i rådata |
| Klick | `ydotool` (uinput) mot koordinater härledda ur AT-SPI + fönstrets verkliga läge | samma klass av input-daemon som XS-55 använde |
| Läsning | AT-SPI (a11y-trädet) på det körande fönstret | ingen läsning ur databasen och ingen ur API:et; det som redovisas är det som faktiskt stod på skärmen |
| Citatkontroll | oberoende, mot `data/tenants/fredling/extract/<id>.json` | produktens eget påstående används **aldrig** som bevis för sig självt |

**Evidensklass: agentkörning med verktygsstöd genom produktens gränssnitt.** Det
är inte operatörsattestering (XS-55:s klass för tangentbordssmoken) och ska inte
läsas som det. Det är också starkare än en API-körning, eftersom det är
gränssnittets egen väg som utövas.

### Två observationer om miljön, gjorda under uppsättningen

1. **Pekarinjektion behövde ställas om för att fungera.** `ydotool`s virtuella
   enhet har bara relativa axlar (`EV=7`, inget `EV_ABS`), och KDE:s
   *adaptiva* pekaracceleration skalade rörelsen (uppmätt `+100` → `88,33` i
   `libinput debug-events`). Med **platt** profil på just den virtuella enheten
   blev rörelsen 1:1 och klick landade där de skulle. Inställningen sattes på den
   virtuella enheten och **återställdes** efteråt. Detta rör inte produkten.
2. **`Appinställningar` går inte att nå med tangentbordet.** Fokusringen i
   dokument-/chattvyn är en sluten cykel om sex element (två förslagsknappar,
   chattfältet, `Skicka fråga`, `Dokument`, `AI-chatt`) — uppmätt genom 22
   `Tab`-tryck. Ingången till menyn är `<div className="user-profile">` **utan
   `tabIndex`** (`brfv2-mockup/src/App.jsx:863`), alltså inte fokuserbar. Menyns
   *poster* är fokuserbara när menyn väl är öppen, men den kan bara öppnas med
   pekare. Följd: en tangentbordsberoende operatör kan inte nå
   modelladressen eller säkerhetskopiorna. Klass **S3/F** — se §7.

---

## 3. Pass 1 — normalt arbetspass (C1, C2)

### 3.1 Start och probe

| | Värde | Källa |
| --- | --- | --- |
| Start | 2026-07-30 **12:13:43** +02:00 | agentens tidsstämpel före start |
| Enhet | `app-BRF\x20Dokument\x2dAI@4c730413c76a45e0b9e1fe86cbcb43cc.service` | `systemctl --user list-units 'app-BRF*'` |
| Skalprocess | `118459 /usr/bin/brfv2-desktop` | `pgrep -ax` |
| Backend | `118471 … -m app.desktop`, lyssnar `127.0.0.1:41167` | `ss -ltnp` |
| Startrad | `{"schema":"brfv2-desktop-startup/v1","status":"ready","host":"127.0.0.1","port":41167,…}` | systemd-användarjournalen |
| Felfönster | inget | M3 = 0 |

**Modelltjänstens nåbarhet, probad i Appinställningar** — inte en blick på
`ready` (pilotplanen §4.4):

* fälten visade `ADRESS http://127.0.0.1:8000/v1`, `MODELL gemma4:e12b`,
  `ETIKETT agenntserver`, `ÅTKOMSTTOKEN Ingen token`;
* `Spara och testa` svarade **`Modelltjänsten sparad.`**;
* och — det som gör det till nåbarhetsbevis — produktens egen logg skrev
  `INFO httpx: HTTP Request: GET http://127.0.0.1:8000/v1/models "HTTP/1.1 200 OK"`.

Gränssnittet visade genomgående `Gemma 4 12B / Self-hosted · agenntserver` och
`Alla dokument · 5 dokument`, med alla fem dokumenten `Färdigbehandlad`.

### 3.2 Frågeuppsättningen — körd oförändrad

Femton frågor ur `backend/eval/golden.json`, ordagrant som pilotplanen §6.3 anger.
Svarstid 10,8–14,4 s per fråga.

| id | Facit (dok, sida) | Svar (kort) | Citat i gränssnittet | Citat löst | Utfall |
| --- | --- | --- | --- | --- | --- |
| g09 | Stadgar s. 2 | lägst 3, högst 5 ledamöter, högst 2 suppleanter | Stadgar s.2 | ✅ exakt | **✅** |
| g17 | Årsredovisning s. 1 | etapp 1 = 1 850 000 kr; etapp 2 = 1 900 000 kr | Årsredovisning s.1 + Underhållsplan s.2 | ✅ båda exakt | **✅** *(överinkluderande)* |
| g19 | Årsredovisning s. 2 | −142 000 kr | Årsredovisning s.2 | ✅ exakt | **✅** |
| g24 | Årsredovisning s. 1 | **SBC Sveriges BostadsrättsCentrum AB** | Årsredovisning s.1 | ✅ alla tokens | **✅** |
| g28 | Styrelseprotokoll s. 1 | Måleri Väst AB | Styrelseprotokoll s.1 | ✅ exakt | **✅** |
| g31 | Styrelseprotokoll s. 2 | 96 000 kr, Chargepark AB | Styrelseprotokoll s.2 | ✅ exakt | **✅** |
| g35 | Snöröjningsavtal s. 1 | 5 centimeter | Snöröjningsavtal s.1 | ✅ exakt | **✅** |
| g37 | Snöröjningsavtal s. 2 | 1 250 kr/tim | Snöröjningsavtal s.2 | ✅ exakt | **✅** |
| g44 | Underhållsplan s. 3 | år 2032 | Underhållsplan s.3 + s.1 | ✅ båda exakt | **✅** *(överinkluderande)* |
| g45 | Underhållsplan s. 3 | 8 500 000 kr | Underhållsplan s.3 | ✅ exakt | **✅** |
| g05 | Stadgar s. 2 *(prosa)* | skriftligt samtycke från styrelsen | Stadgar s.2 | ✅ exakt | **✅** |
| g25 | Underhållsplan s. 1 *(prosa)* | revideras vart tredje år | Underhållsplan s.1 | ✅ exakt | **✅** |
| u02 | *obesvarbar* | `OTILLRÄCKLIGT UNDERLAG` — inget arvode anges | **inget citat** | — | **✅** |
| u05 | *obesvarbar* | `OTILLRÄCKLIGT UNDERLAG` — datumet framgår inte | **inget citat** | — | **✅** |
| u08 | *obesvarbar* | `OTILLRÄCKLIGT UNDERLAG` — radonresultat saknas | **inget citat** | — | **✅** |

| Kategori | Pass 1 | Krav |
| --- | --- | --- |
| Fragment-fakta med rätt uppgift **och** löst citat till facitsidan | **10 / 10** | alla 10 |
| Prosakontroller besvarade med stött citat | **2 / 2** | fick avvisas |
| Obesvarbara avvisade med **noll** citat | **3 / 3** | 3 |
| **Fabricerade källhänvisningar** | **0** *(14 av 14 citat lösta)* | måste vara 0 |

### 3.3 Citatkontrollen är oberoende, och gjord i två steg

Varje citatchip i gränssnittet bär dokumentnamn, sida och den citerade passagen.
Kontrollen rekonstruerar sidans text ur `extract/<id>.json` (ord med koordinater)
och söker passagen där. **Två skilda saker kontrolleras, därför att de kan gå
isär:**

1. **löser citatet?** — finns den citerade passagen på den citerade sidan;
2. **är svaret rätt?** — säger svaret den uppgift facit kräver.

Utfall: 14 av 14 citat löste (12 exakt, 1 med enbart avvikande blanksteg, samt
g09 där chipets a11y-namn skriver `12.pdfs.2` utan blanksteg — ett läsbarhetsfynd
i chipet, inte ett citatfel). Ingen citerad sida saknades, och ingen citerad
passage fanns någon annanstans än där den påstods finnas.

### 3.4 Jämförelse mot XS-55-baslinjen

| Kategori | XS-55 (baslinje) | XS-56 pass 1 | Bedömning |
| --- | --- | --- | --- |
| Fragment-fakta | 10 / 10 | **10 / 10** | oförändrat |
| Prosa | 2 / 2 | **2 / 2** | oförändrat |
| Obesvarbara med noll citat | **2 / 3** | **3 / 3** | **förbättring** — u05 avvisade nu utan citat |
| Fabricerade | 0 | **0** | oförändrat |
| Antal citat | 13 | 14 | fler, alla lösta |
| Överinkluderande svar | g17, g31, g44 | g17, g44 | g31 skärptes |

**Två avvikelser mot baslinjen, båda till det bättre — och en av dem är en
rättelse av baslinjen:**

**u05.** XS-55 fick ett kvalificerat icke-svar *med* ett stött citat till Stadgar
s. 3, vilket bröt villkoret "noll citat" och räknades som 2 av 3. XS-56 gav
`OTILLRÄCKLIGT UNDERLAG` **utan citat**. Villkoret är därmed uppfyllt utan att
uppsättningen skrivits om — vilket är precis den ordning §6 kräver. Frågan om
villkoret *borde* skrivas om tillhör fortfarande BP4, men den är inte längre
blockerande.

**g24 — XS-55:s baslinje innehåller ett sakfel som bör rättas.** Frågan är
"Vilket företag sköter den **ekonomiska** förvaltningen?". Sidan säger:

```
Den tekniska förvaltningen har under året skötts av Driftia Fastighetsservice AB
medan den löpande ekonomiska för- valtningen har skötts av
SBC Sveriges BostadsrättsCentrum AB.
```

XS-55 redovisade svaret **`Driftia Fastighetsservice AB`** och godkände det med
citatkontrollen "✓ `Driftia`". Men Driftia är den **tekniska** förvaltaren; facit
i `golden.json` är `SBC Sveriges BostadsrättsCentrum AB`. Citatet *löste* — ordet
`Driftia` står på den citerade sidan — men **svaret angav fel företag**.

XS-56 svarade `Den löpande ekonomiska förvaltningen har skötts av SBC Sveriges
BostadsrättsCentrum AB`, med citat till samma sida. Det är rätt.

Slutsatsen är inte i första hand att modellen blev bättre, utan **metodisk**:
XS-55:s kontroll bevisade att *citatet hade stöd*, och den slutsatsen användes
som om den också bevisade att *svaret var rätt*. Det gör den inte. Ett svar kan
peka på en sida som verkligen innehåller det citerade ordet och ändå besvara
frågan fel. Därför kontrollerar XS-56 de två sakerna var för sig (§3.3), och
därför bör XS-55:s `M5 = 10 av 10` läsas med det förbehållet. Detta är **inte**
ett stoppkriterium: ingen källhänvisning var fabricerad, och inget ostött svar
presenterades som grundat.

### 3.5 Mätvärden, pass 1

| # | Mätvärde | Pass 1 |
| --- | --- | --- |
| M1 | Start från applikationsmenyn utan terminalarbete utöver tunneln | **ja, 1 av 1** |
| M2 | Terminalingripanden | **0 krävdes för att använda produkten.** Sanktionerat: SSH-tunneln (§7 undantar den). Verktyg (agentens, utan verkan på produkten): `ydotoold`, pekarprofilen på den virtuella enheten (satt + återställd), läsning av a11y-träd och loggar |
| M3 | Startmisslyckanden (felfönster) | **0** — `status: ready`, 0 fel i `backend.log` |
| M4 | Oväntade backend-dödsfall | **0** — pid `118471` oförändrad hela passet, ingen `Failed`, ingen signal, ingen core-dump, `backend.log.1` orörd sedan 09:36 |
| M5 | Fragment-faktafrågor med korrekt löst citat | **10 / 10** |
| M6 | Felaktiga avvisningar | **0** |
| M7 | Fabricerade källhänvisningar | **0** |

**Efter passet:** fönstret stängt med produktens egen `Close`; `pgrep -f
brfv2-desktop` **tomt**; systemd-enheten borta; tunneln stängd. Data efter passet:
**5 dokument / 13 chunks** oförändrat, korpusens PDF:er orörda, `auth.db` orörd.
Den enda fil som skrevs under passet var `data/desktop-config.json`, omskriven av
proben med **identiskt innehåll** (`http://127.0.0.1:8000/v1`, `gemma4:e12b`,
`agenntserver`, tom nyckel) — alltså ingen ny persistent data och inget
endpointbyte.

---

## 4. Pass 2 — leverantörsbortfall mitt i passet (C3)

### 4.1 Före passet

Tunneln uppe och `/v1/models` annonserade `gemma-4-12b-it-UD-Q4_K_XL.gguf`;
leveransträdet `a702a337…`; `rpm --verify` = 0; `deliveryTree` = `a702a337…`;
5 dokument / 13 chunks; `webkit2gtk4.1 2.52.5-1.fc44`, `gtk3 3.24.52-2.fc44`.

| | Värde |
| --- | --- |
| Start | 2026-07-30 **12:46:39** +02:00 |
| Enhet | `app-BRF\x20Dokument\x2dAI@b5d9a28c142c428d860a16f602525fe9.service` |
| Skalprocess / backend | `134511` / `134523` (`127.0.0.1:34057`) |
| Startrad | `status: ready` |
| Probe i Appinställningar | `Modelltjänsten sparad.` + `GET /v1/models "HTTP/1.1 200 OK"` |

### 4.2 Injektionen

Tunneln stängdes **12:48:07** medan passet var öppet och appen körde:

```
port 8000: 0 listeners
curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/v1/models  →  000
```

Därefter ställdes en fråga som **bevisligen har stöd i korpusen** — g35, samma
fråga som i pass 1 gav ett löst citat till Snöröjningsavtal s. 1.

### 4.3 Vad produkten gjorde

| Vad | Observerat i gränssnittet |
| --- | --- |
| Svarstext | `OTILLRÄCKLIGT UNDERLAG` följt av `Tekniskt fel vid svarsgenerering — försök igen om en stund.` |
| Citat | **noll** |
| Grundat-utseende svar | **nej** — ingen uppgift ur korpusen påstods |
| Fabricerad källhänvisning | **nej** |
| Svarstid | 8,2 s |

Produktens egen logg namnger orsaken, och namnger den rätt:

```
ERROR brf.answer: Svarsgenerering misslyckades:
      Kunde inte nå LLM-servern (http://127.0.0.1:8000/v1): ConnectError
```

**Ingen annan värd kontaktades.** Samtliga URL:er i `backend.log` för passet är
`http://127.0.0.1:8000` — stoppkriterium 2 (utgående anslutning till annan värd)
och stoppkriterium 3 (värdbaserad leverantör) utlöstes alltså inte, och det är
kontrollerat och inte antaget.

**En anmärkning som hör till erfarenhetsåterföringen (S3):** rubriken
`OTILLRÄCKLIGT UNDERLAG` är i det här läget inte riktigt sann — underlaget fanns,
det var *modellen* som inte gick att nå, vilket den andra raden säger korrekt.
Att återanvända avvisningsrubriken för ett leverantörsfel riskerar att en
operatör drar slutsatsen att korpusen är otillräcklig när problemet är tunneln.
Beteendet är säkert; formuleringen är förbättringsbar. Ingen produktändring görs
under piloten (`brfv2-mockup/src` ligger i `REPRO_DELIVERY_PATHS`).

### 4.4 Återhämtning

Tunneln öppnades igen **12:48:54**. Proben i Appinställningar kördes **om** och
svarade `Modelltjänsten sparad.` med `GET /v1/models "HTTP/1.1 200 OK"` i loggen.
Därefter kördes hela frågeuppsättningen: **10/10 fragment-fakta, 2/2 prosa,
3/3 obesvarabara med noll citat, 0 fabricerade** — 14 av 14 citat lösta, alltså
**identiskt med pass 1**. Överinkluderingen låg på samma två frågor (g17, g44) med
samma extra sidor. Svarstid 10,7–14,4 s.

Ingen dataskada:

| Kontroll | Efter bortfall + återhämtning |
| --- | --- |
| Dokument / chunks | **5 / 13** |
| `auth.db` `PRAGMA integrity_check` | `ok` |
| Konton / medlemskap / sessioner | 1 / 1 / 1 |
| Korpusens fem PDF:er mot `~/pilot-korpus/` | **5 av 5 bit-identiska** |

### 4.5 Mätvärden, pass 2

| # | Mätvärde | Pass 2 |
| --- | --- | --- |
| M1 | Start från menyn | **ja, 1 av 1** |
| M2 | Terminalingripanden | **0 krävdes för att använda produkten.** Sanktionerat: tunneln — samt att stänga och öppna den, vilket *är* experimentet |
| M3 | Startmisslyckanden | **0** |
| M4 | Oväntade backend-dödsfall | **0** — pid `134523` oförändrad; ingen `Failed`, ingen signal, ingen core-dump |
| M5 | Fragment-faktafrågor med korrekt löst citat | **10 / 10** |
| M6 | Felaktiga avvisningar | **0** — avvisningen under bortfallet är *korrekt* beteende, inte en felaktig avvisning |
| M7 | Fabricerade källhänvisningar | **0** |

Exakt **ett** `ERROR` i passets logg, och det är det injicerade. Loggrotationen
bevarade pass 1:s logg i `backend.log.1`.

---

## 5. Pass 3 — backendprocessen dödas (C4)

### 5.1 Före passet och start

Alla förepasskontroller gröna (`/v1/models` annonserar Gemma 4 12B,
`rpm --verify` = 0, `deliveryTree` = `a702a337…`, 5 dokument / 13 chunks,
`webkit2gtk4.1 2.52.5-1.fc44`, `gtk3 3.24.52-2.fc44`).

| | Värde |
| --- | --- |
| Start | 2026-07-30 **12:56:35** +02:00 |
| Enhet, instans 1 | `app-BRF\x20Dokument\x2dAI@bedacb3d445041e5a65647d1fce2a3b1.service` |
| Skalprocess | `139745 /usr/bin/brfv2-desktop` |
| **Backend** | `139757 … -m app.desktop`, `127.0.0.1:39105` |
| Probe | `Modelltjänsten sparad.` + `GET /v1/models "HTTP/1.1 200 OK"` |

**Vid start gick appen rakt in i dokumentvyn** — varken uppstartsdialog eller
inloggningsruta. Sessionen från 2026-07-29 (fjorton dagars giltighet) lever
alltså vidare även över tre appstarter och en backendkrasch. Det är samma
observation XS-55 gjorde och den kvarstår oförändrad; den hör till BP5-underlaget
för en produkt vars poäng är att data stannar lokalt.

Fingeravtryck **före** injektionen, tagna för att kunna bevisa att inget rörs:

```
data/ (hela trädet, sha256)  23e2724658b914487c3baf58cd94324108fff484ad70fcd33ceb2f32341b5b49
logs/backend.log             4c08f92254ff2af3d3cd31994d2d3f1b2b985edcfca5c1fa5f69f71fa2003312
logs/backend.log.1           c979d759da27f45d88f08c183b2bfe8cf76ad66143a25ca075258cdae8d907fb
```

### 5.2 Injektionen — den verkliga backenden, inte skalet

`kill -TERM 139757` **12:57:30**. Det är processen som *är* backenden: den kör
`app.desktop` och äger lyssnaren på `127.0.0.1:39105`. Skalprocessen `139745`
rördes inte.

| Vad | Observerat |
| --- | --- |
| Backendprocessen | **borta** |
| Skalprocessen | **lever** (`139745`) — den äger felfönstret |
| Arbetsfönstret | **stängt** |
| Fönstertitel efter | `BRF Dokument-AI — kunde inte starta` |

### 5.3 Felfönstret är produktens eget, och det namnger orsaken

Läst ur a11y-trädet på det verkliga fönstret:

| Del | Text |
| --- | --- |
| Rubrik | **Applikationen tappade sin bakgrundstjänst** |
| Brödtext | *Applikationen kunde inte starta sin lokala bakgrundstjänst. Ingen data har ändrats eller skickats någonstans.* |
| **TEKNISK ORSAK** | *Bakgrundstjänsten avslutades av **signal 15**. Inga data har gått förlorade — dina dokument och inställningar ligger kvar lokalt. Stäng fönstret och starta BRF Dokument-AI igen.* + sökväg till `logs/backend.log` |
| SÅ HÄR KOMMER DU VIDARE | tre numrerade steg: starta om · installera om `brf-dokument-ai` och kontrollera `tesseract`/`webkit2gtk4.1` om felet återkommer · data ligger kvar under `~/.local/share/se.brfdokumentai.desktop` |

Det avgörande är att fönstret säger **signal 15** — vilket är exakt den signal som
skickades. Det är inte en generisk feltext utan den faktiska orsaken, och den
följs av ett korrekt påstående om att data ligger kvar, plus var loggen finns.

### 5.4 Loggarna bevarades — och rotationen bevarade den döda instansens logg

Direkt efter dödandet var **båda** loggfilerna bit-identiska med före:

```
backend.log    4c08f922…   (oförändrad)
backend.log.1  c979d759…   (oförändrad)
```

Ingenting trunkerades. Vid omstarten roterade produkten, och rotationen
**bevarade den kraschade instansens logg**:

```
efter omstart:  backend.log    2200d522…   (den nya instansen)
                backend.log.1  4c08f922…   ← den kraschade instansens logg
```

Att `backend.log.1` efter omstarten *är* filen som fanns före kraschen är bevisat
med SHA-256, inte antaget.

**En anmärkning (S3):** loggen innehåller ingen rad om själva dödsfallet. Det är
väntat — processen fick `SIGTERM` och hann inte skriva — men konsekvensen är att
en granskare som *bara* läser `backend.log` inte kan se att backenden dog.
Orsaken finns i felfönstret och i systemd-journalen, inte i produktens egen logg.
Det ligger nära XS-55:s öppna fynd om att `backend.log` saknar tidsstämplar.

### 5.5 Data låg kvar — bevisat med hela trädets summa

| Kontroll | Efter dödandet |
| --- | --- |
| `data/` hela trädet, sha256 | **`23e27246…` — bit-identiskt med före** |
| Dokument / chunks | **5 / 13** |
| `auth.db` `PRAGMA integrity_check` | `ok` |
| Konton / medlemskap / sessioner | 1 / 1 / 1 |
| `tenant_meta.json` | `{"corpus_origin": "customer"}` |

Kontrollen är gjord på hela katalogträdet, inte bara på antal poster. Föreningen,
kontot, de fem dokumenten och de tretton chunkarna var alltså **oförändrade in på
byten**.

### 5.6 Omstart och ett grundat svar, verifierat mot rätt dokument och sida

Omstart **12:58:49** från applikationsmenyn.

| | Värde |
| --- | --- |
| Enhet, instans 2 | `app-BRF\x20Dokument\x2dAI@3234e8f2802a492c8b04afd5a25cbd81.service` |
| Skalprocess / backend | `141153` / `141165` (`127.0.0.1:54249`) |
| Startrad | `status: ready`, inget `ERROR`, inget felfönster |

Det obligatoriska enskilda kontrollsvaret:

| | |
| --- | --- |
| Fråga | g19 *"Vad blev årets resultat 2025?"* — texten kontrollerad i fältet före Enter |
| Svar | **`Årets resultat blev -142 000 kronor.`** (12,3 s) |
| Citat i gränssnittet | `[1] "Årets resultat blev -142 000 kronor." — Årsredovisning 2025.pdf s.2` |
| Oberoende upplösning | **RESOLVED (exakt på citerad sida)** — passagen finns ordagrant på sida 2 i `extract/`-texten |
| Citatet klickat | öppnade `Årsredovisning 2025.pdf` (`3 sidor`) med overlayen **`Markerat källcitat`** renderad |

Att den visade sidan verkligen är sida 2 följer av produktens egen kod:
`brfv2-mockup/src/components/PdfPane.jsx:82` renderar overlays endast när
`highlightPage === clampedPage`. Att overlayen finns i trädet betyder alltså att
den renderade sidan är citatets sida. (Sidindikatorn `Sida 2 av 3` är en
`<span>` som inte exponeras i AT-SPI — därför bevisas sidan på det här sättet i
stället för genom att läsa siffran. Det är en läsbarhetsbegränsning i
mätmetoden, inte i produkten.)

### 5.7 Frågeuppsättningen kördes **efter** omstarten — och varför just där

Uppsättningen kördes en gång i pass 3, placerad **efter** återstarten. Skälet,
skrivet ut därför att placeringen är ett metodval och inte en tillfällighet:

* **Före dödandet hade den mätt om samma sak en tredje gång.** Passets tillstånd
  före injektionen är detsamma som pass 1 och pass 2 redan mätt två gånger med
  identiskt utfall. En tredje mätning där hade inte prövat något nytt.
* **Efter omstarten prövar den den enda frågan som pass 3 faktiskt ställer:**
  kommer produkten tillbaka *hel* efter att backenden dött — inte bara "startar
  den igen", utan svarar den fortfarande rätt, på samma data, med citat som löser
  till rätt sida.
* **Ett enda svar räcker inte som bevis för det.** C4 kräver att data ligger kvar;
  hela uppsättningen mot hela korpusen är ett starkare belägg för att indexet är
  oskadat än ett enstaka lyckat svar, eftersom den rör alla fem dokumenten och
  alla tretton chunkarna.

Utfall efter omstarten:

| Kategori | Pass 3 (efter omstart) |
| --- | --- |
| Fragment-fakta med rätt uppgift **och** löst citat till facitsidan | **10 / 10** |
| Prosakontroller med stött citat | **2 / 2** |
| Obesvarbara avvisade med noll citat | **3 / 3** |
| **Fabricerade källhänvisningar** | **0** *(14 av 14 citat lösta)* |
| Överinkluderande | g17, g44 — samma två som i pass 1 och 2 |
| Svarstid | 10,7–14,4 s |
| Frågetexten byte-exakt i fältet | **15 av 15** |

### 5.8 Mätvärden, pass 3

| # | Mätvärde | Pass 3 |
| --- | --- | --- |
| M1 | Start från menyn | **ja, 2 av 2 starter** (instans 1 + omstarten) |
| M2 | Terminalingripanden | **0 krävdes för att använda produkten.** Sanktionerat: tunneln. Dödandet *är* experimentet |
| M3 | Startmisslyckanden (felfönster) | **0** — båda instanserna nådde `status: ready`. Felfönstret räknas **inte** som startmisslyckande: det var den korrekta ytan för en dödad backend, inte en misslyckad start |
| M4 | Oväntade backend-dödsfall | **0 oförklarade** (1 avsiktligt, injicerat). Stoppkriterium 7 kräver **tre oförklarade** i samma pass |
| M5 | Fragment-faktafrågor med korrekt löst citat | **10 / 10** |
| M6 | Felaktiga avvisningar | **0** |
| M7 | Fabricerade källhänvisningar | **0** |

Efter passet: fönstret stängt, `pgrep -f brfv2-desktop` tomt, systemd-enheten
borta, tunneln stängd, `rpm --verify` = 0, `deliveryTree` = `a702a337…`.

---

## 6. Mätvärden M1–M7 över de tre passen

| # | Mätvärde | Pass 1 | Pass 2 | Pass 3 |
| --- | --- | --- | --- | --- |
| M1 | Start från menyn utan terminalarbete utöver tunneln | 1/1 | 1/1 | **2/2** |
| M2 | Terminalingripanden som krävdes för att *använda* produkten | **0** | **0** | **0** |
| M3 | Startmisslyckanden (felfönster vid start) | 0 | 0 | 0 |
| M4 | **Oförklarade** backend-dödsfall | 0 | 0 | 0 *(1 avsiktligt)* |
| M5 | Fragment-fakta med korrekt löst citat | **10/10** | **10/10** | **10/10** |
| M6 | Felaktiga avvisningar | 0 | 0 | 0 |
| M7 | **Fabricerade källhänvisningar** | **0** | **0** | **0** |
| — | Prosa med stött citat | 2/2 | 2/2 | 2/2 |
| — | Obesvarbara med noll citat | 3/3 | 3/3 | 3/3 |
| — | Citat lösta / totalt | 14/14 | 14/14 | 14/14 |
| — | Svarstid | 10,8–14,4 s | 10,7–14,4 s | 10,7–14,4 s |

**Fyra starter från menyn, noll terminalingripanden för att använda produkten,
noll fabricerade källhänvisningar, 42 av 42 citat lösta.** Utfallet är identiskt
över tre pass — inklusive vilka två frågor som blir överinkluderande. Det är
reproducerbarhet, inte tur.

---

## 7. Avvikelser

| # | Klass | Vad | Följd |
| --- | --- | --- | --- |
| 1 | **S3 / F** | **`Appinställningar` går inte att nå med tangentbordet.** Fokusringen är en sluten cykel om sex element; menyns ingång (`user-profile`) saknar `tabIndex` (`brfv2-mockup/src/App.jsx:863`) | En tangentbordsberoende operatör kan varken probe:a modelltjänsten, byta modelladress eller skapa säkerhetskopia. Ligger i `REPRO_DELIVERY_PATHS` → **får inte åtgärdas under piloten**. Uppföljning efter piloten |
| 2 | **S3** | **XS-55:s baslinje har ett sakfel i g24** — svaret `Driftia Fastighetsservice AB` godkändes för en fråga om *ekonomisk* förvaltning, där facit är `SBC Sveriges BostadsrättsCentrum AB`. Driftia är teknisk förvaltare | Journalens `M5 = 10 av 10` för XS-55 bör läsas med förbehåll. **Metodisk rot:** citatupplösning användes som om den bevisade svarets riktighet. XS-56 skiljer på de två (§3.3). Inget stoppkriterium — citatet var inte fabricerat |
| 3 | **S3** | **`OTILLRÄCKLIGT UNDERLAG` återanvänds som rubrik vid leverantörsfel.** Vid tunnelbortfall står rubriken kvar trots att underlaget fanns; orsaken sägs korrekt på nästa rad | Risk att en operatör tror att korpusen är otillräcklig när problemet är tunneln. Beteendet är säkert; formuleringen är förbättringsbar. Erfarenhetsåterföring |
| 4 | **S3** | **`backend.log` innehåller ingen rad om backendens död.** Processen fick `SIGTERM` och hann inte skriva | Orsaken finns i felfönstret och systemd-journalen, inte i produktens egen logg. Ligger nära XS-55:s öppna fynd om saknade tidsstämplar i `backend.log` |
| 5 | **S3** | **Sessionen överlever tre appstarter och en backendkrasch.** Ingen inloggning krävdes i något pass; sessionsraden från 2026-07-29 har fjorton dagars giltighet | Samma observation som XS-55 gjorde, nu bekräftad över en krasch. Hör till BP5-underlaget. Oförändrad, ingen ny åtgärd |
| 6 | **S3** *(mätmetod)* | **Sidindikatorn `Sida N av M` exponeras inte i AT-SPI.** Sidan bevisades i stället via highlight-overlayens renderingsvillkor (`PdfPane.jsx:82`) | Begränsning i mätmetoden, inte i produkten. En människa ser siffran |
| 7 | **S3** *(miljö)* | **Pekarinjektion krävde platt accelerationsprofil** på den virtuella `ydotool`-enheten; tangentbordsinjektion fungerade direkt | Rör inte produkten. Nyanserar pilotplanens begränsning 3: tangentbord är automatiserbart här, pekaren bara efter omställning. Inställningen återställdes; enheten finns inte längre |
| 8 | *(ingen)* | Inget stoppkriterium i pilotplanen §8 inträffade | Se §8.1 |

### 7.1 Stoppkriterierna, prövade var för sig

| # | Stoppkriterium | Utfall |
| --- | --- | --- |
| 1 | Dokument/data från en förening syns i en annan | **Nej.** En förening, ett konto; inga andra tenants finns |
| 2 | Utgående anslutning till annan värd än modelladressen | **Nej.** Samtliga URL:er i loggarna är `http://127.0.0.1:8000` — kontrollerat, inte antaget |
| 3 | Värdbaserad leverantör valbar eller i det installerade trädet | **Nej.** `inspect_payload --installed` 45 kontroller / **0 fynd** |
| 4 | Fabricerad källhänvisning, eller ostött svar presenterat som grundat | **Nej.** 42 av 42 citat lösta mot extraherad sidtext över tre pass |
| 5 | Dataförlust vid kopiering/återställning/av- och ominstallation | **Nej.** Inget av det gjordes; och `data/`-trädets summa var oförändrad över backendens död |
| 6 | `rpm --verify` ≠ 0 utan förklaring, eller `deliveryTree` ≠ `a702a337…` | **Nej.** `0` och `a702a337…` före och efter alla tre passen |
| 7 | Tre oförklarade backend-dödsfall i ett pass | **Nej.** Ett dödsfall, avsiktligt och förklarat |

---

## 8. Begränsningar i den här evidensen

1. **Korpusen är syntetisk.** Ingenting här säger något om verkliga stadgar eller
   årsredovisningar. Oförändrad begränsning från pilotplanen §2.
2. **Evidensklassen är agentkörning med verktygsstöd**, inte
   operatörsattestering. Frågorna gick genom gränssnittets egen väg, men det var
   inte en människa som skrev dem. XS-55:s tangentbordssmoke (7 av 8, med
   Shift+Enter underkänt) står oförändrad och är inte omprövad här.
3. **Tre pass är tre pass.** Utfallet är identiskt över dem, men "upprepade
   arbetspass" i pilotplanens mening är inte detsamma som veckor av verklig drift.
4. **Ingen omkörning av den formella acceptansen gjordes**, eftersom villkoret
   (ändrad `webkit2gtk4.1`/`gtk3`) inte var uppfyllt. Om Fedora uppgraderar
   någon av dem gäller C5 igen innan piloten återupptas.
5. **Slinga 4:s frågor är obesvarade här.** Säkerhetskopian som skapades i pass 3
   är kontrollerad post för post men **inte återställd** — att den går att
   återställa är XS-57:s sak, inte den här filens.
6. **`M8`–`M10` mättes inte** (de tillhör slinga 4 respektive slinga 2).

---

## 9. BP4-3 — rekommendation

**BP4-3 ska visa:** att produkten beter sig som acceptansen lovar även utanför
acceptansens isolerade miljö.

**Rekommendation: passera BP4-3 och gå vidare till slinga 4 (XS-57).**

Underlaget är sammanställt som grindunderlag i
[`BP4-3-BESLUTSUNDERLAG.md`](../../pilot/BP4-3-BESLUTSUNDERLAG.md), där de fyra
besluten nedan ligger var för sig med alternativ och belägg. Tre av dem är
verkställda som dokumentändringar i pilotplanen och journalen (rättelsen av g24
med metodregeln, `M4`-definitionen, begränsning 13); det fjärde — villkoret för
obesvarbara frågor — är **oförändrat**, och skälet är att den som kört testet inte
får avgöra det.

Underlaget för det:

| Vad slinga 3 skulle visa | Utfall |
| --- | --- |
| C1 — upprepade arbetspass, journalförda | **3 pass**, fyra menystarter, journalförda med M1–M7 var för sig |
| C2 — uppsättningen körd per pass, jämförd mot baslinjen | **3 körningar**, identiska: 10/10 · 2/2 · 3/3 · 0 fabricerade. Ingen kategori tappade mot XS-55; två blev bättre |
| C3 — tunneln stängd mitt i passet | **Vägran med leverantörsfel, noll citat, inget påhittat svar**, orsaken namngiven i loggen, ingen annan värd kontaktad |
| C4 — backendprocessen dödad | **Arbetsfönstret stängdes, produktens eget felfönster namngav signal 15**, loggarna bit-identiska och rotationen bevarade den döda instansens logg, `data/`-trädet bit-identiskt |
| C5 — omkörning vid `webkit2gtk4.1`/`gtk3`-byte | **Utlöstes inte** — båda versionerna oförändrade sedan XS-55 |

**Fyra saker BP4-3 bör besluta om, inte bara notera:**

1. **Rätta XS-55:s g24-post och skriv in metodregeln.** Citatupplösning och
   svarsriktighet är två kontroller. Att slå ihop dem lät ett fel svar passera med
   godkänt citat. Regeln bör stå i pilotplanen §6.3, inte bara i den här filen.
2. **Villkoret för obesvarbara frågor.** XS-56 gav 3/3 utan att uppsättningen
   ändrades, så frågan är inte längre blockerande — men den kvarstår: ska ett
   kvalificerat icke-svar *med stött citat* räknas som godkänt? Beslutet hör till
   BP4 och får inte fattas av den som kör testet.
3. **Tangentbordsotillgängligheten i `Appinställningar`** är allvarligare än en
   kosmetisk brist: den låser modelladressen och säkerhetskopiorna bakom en
   pekare. Den ligger i `REPRO_DELIVERY_PATHS` och kan inte åtgärdas under
   piloten. BP4 bör klassa den uttryckligen — förslag: **F**, med krav på
   åtgärd innan produkten släpps till någon som inte kan använda mus.
4. **`M4`:s definition.** XS-55 fann att §7 inte skiljer värdorsakad avslutning
   från backend-dödsfall. XS-56 lägger till ett andra fall: *avsiktlig* injektion.
   Definitionen bör skilja **oförklarade** dödsfall från förklarade, vilket är det
   stoppkriterium 7 faktiskt menar.

**Vad rekommendationen inte vilar på.** Inget här stärker påståenden om verklig
korpus, andra maskiner, bred distribution eller uppgraderingsvägen. Slinga 4:s
frågor — säkerhetskopiering, återställning, paketbyte — är fortfarande öppna, och
återställning är **oprövad**: kopian från pass 3 är kontrollerad men inte
återläst.
