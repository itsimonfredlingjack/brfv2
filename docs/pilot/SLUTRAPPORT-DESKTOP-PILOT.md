# Slutrapport — kontrollerad Fedora-skrivbordspilot

**Projekt:** brfv2 Desktop — Fedora app shell
**Fas:** Avslut (BP6)
**Rapportdatum:** 2026-08-01
**Rapporterad linje:** `bp6/fedora-pilot-closeout`, avstamp `d6e73bf280390995847b87cdd092acc9fa211014`
**Pilotens sista evidenscommit:** `a5a112b095d28f2e740b9fe8a095e2c62b9c5803`
**Artefakt:** `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm`, SHA-256 `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d`

Den här rapporten avslutar **skrivbordspiloten**. Den avslutar inte, ersätter
inte och uppdaterar inte `docs/SLUTRAPPORT.md`, som är webb-MVP:ns slutrapport
från 2026-07-28 och tillhör en annan grindkedja. De två cyklerna delar
gate-namn men inte innehåll; ett tal eller ett `PASS BP5` ur den ena får inte
läsas in i den andra.

---

## 1. Vad piloten var

En kontrollerad enanvändarpilot av **en** osignerad skrivbordsartefakt på **en**
Fedora 44-maskin (KDE/Wayland), med **en** människa som både
installationsadministratör och operatör, en **syntetisk** femdokumentskorpus och
Gemma 4 12B på `agenntserver` nådd över loopback via SSH-forward.

Frågan piloten skulle avgöra, ur `PILOTPLAN.md` §2:

> om den godkända artefakten går att *leva med* som skrivbordsprogram över
> upprepade verkliga arbetspass — installation, första start, dagligt bruk,
> säkerhetskopiering, återställning, avinstallation och ominstallation, samt de
> fel som faktiskt inträffar — utan att operatören behöver terminalen för annat
> än SSH-tunneln.

Genomförandet skedde i fyra slingor: **slinga 1** (XS-54) återställbar och
evidenssäker pilotmiljö, **slinga 2** (XS-55) okonfigurerad maskin till
fungerande installation, **slinga 3** (XS-56) upprepade arbetspass med
felinjektion, **slinga 4** (XS-57) säkerhetskopiering, återställning,
paketbyte och katastrofövning. Därefter en oberoende **BP5-kallgranskning**
(2026-07-31) av en granskare utan bygghistorik.

---

## 2. Vad den kontrollerade piloten verifierade

Detta avsnitt innehåller **endast** påståenden som bärs av körd, committad
evidens. Varje rad har en evidensfil.

### 2.1 Artefaktidentitet och reproducerbarhet

| Påstående | Bevis |
| -- | -- |
| Artefakten byggdes om från `84b6fc8` i en ren fristående checkout och blev **bit-identisk** med BP2-baslinjen | `slinga1-startevidens.md` A1: SHA-256 `6ba028fb…`, 574 604 029 byte |
| Reproducerbarhet mellan två checkouter med olika sökvägslängd | `xs51-reproducibility.json`: båda `6ba028fb…`, `cmp -s` identiska |
| Det arkiverade paketet **är** det installerade | `%{SHA256HEADER}` = kvittots `rpm.headerSha256` = `5fc97bce…` |
| Paketet är osignerat, och det påstås öppet | `%{SIGPGP}` = `(none)`; kallgranskningens `rpm -qi` → `Signature : (none)` |
| `rpm --verify brf-dokument-ai` utan skillnader | exitkod 0, i slinga 1, slinga 4 och i kallgranskningen |
| Leveransträdet är oförändrat genom hela piloten | `deliveryTree` = `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` i repot, i `BUNDLE.json` och i varje acceptanskvitto |
| Piloten kunde inte tyst ändra artefakten | `git diff 84b6fc85… HEAD -- <REPRO_DELIVERY_PATHS>` **tomt** (kallgranskningen §4) |

### 2.2 Leverantörsgränsen — ingen dold utgående trafik

| Påstående | Bevis |
| -- | -- |
| Ingen värdbaserad modell-leverantör finns i paketet | `ops/inspect_payload.py --installed`: **45 kontroller, 0 fynd**, 4 675 filer, payload `55c20520…` — omkört i slinga 1, slinga 2 (B0), slinga 4 och av kallgranskaren |
| Uteslutningen är strukturell, inte en flagga | `app.llm_hosted` finns inte i bundlen; `ops/build-runtime.sh` fäller bygget på första fynd och har ingen förbi-flagga |
| Den paketerade tolken kan inte välja en värdbaserad leverantör | sju `provider-selection`-prov i den paketerade Pythonen ger `none` för `auto+ANTHROPIC_API_KEY`, `auto+claude på PATH`, `BRF_LLM=api` och `BRF_LLM=cli`; endast `selfhosted` väljer något |
| Endast en utgående anslutning existerade i drift | slinga 2 B0: backend-pid 389868 hade exakt en TCP-anslutning, `127.0.0.1:54896 → 127.0.0.1:8000`, och lyssnade endast på `127.0.0.1:47671` |
| Modelladressen är default-deny | `model_endpoint.py`: `loopback` (http/https) och `private-network` (endast https); sex avvisade adresser i acceptansevidensen, var och en med sin stabila kod |
| En handredigerad konfigurationsfil sätter inte en otillåten adress i kraft | `securityBoundary.tamperedConfigFile`: `https://api.openai.com/v1` → `configured: false`, `provider: none` |
| Vikterna hämtas inte över nätet | `HF_HUB_OFFLINE=1`, `BRF_MODEL2VEC_PATH` mot bundlens vikter; skalet kräver `runtime/models/potion-multilingual-128M` för att alls starta |

### 2.3 Installation, första start och daglig drift

| Påstående | Bevis |
| -- | -- |
| Genuin förstagångsstart — ingen datakatalog fanns innan | slinga 2 B0 punkt 11: `No such file or directory` (exit 2); `EVIDENSREGISTER-XS55.md` skiljer klass **P** (preflight) från klass **F** (första start) |
| Installationen konfigurerades genom produktens eget fönster | `INFO brf.desktop: Installation konfigurerad: förening fredling`; datakatalogen skapad `mode 700`, alla fyra kontraktskataloger `drwx------` |
| Produkten startas från applikationsmenyn utan terminal | M1 = 1/1, 1/1, 2/2 över slinga 3:s tre pass; `.desktop`-posten har `Terminal=false` |
| **M2 = 0 terminalingripanden** för att använda produkten | slinga 3, alla tre pass — effektmålets mätvärde |
| M3 startmisslyckanden = 0, M4 oförklarade backend-dödsfall = 0 | slinga 3, alla tre pass |
| Formell pilotacceptans grön mot det **installerade** paketet | `make desktop-acceptance-installed`, exitkod 0, 129,9 s, alla fyra faser `uiJourney`/`lifecycle`/`securityBoundary`/`failureSurfaces` (`xs55-slinga2-installed-desktop-acceptance.json`) |
| Regressionssviten grön på pilotmaskinen | 657 passed / 3 skipped, `npm test` 21, Playwright 11, `cargo test --locked` 5 |

### 2.4 Svarskvalitet på den syntetiska korpusen

Frågeuppsättningen är femton namngivna frågor med facit i
`backend/eval/golden.json`: tio fragment-fakta, två prosakontroller, tre
obesvarbara.

| Mätvärde | Slinga 2 (baslinje) | Slinga 3, pass 1–3 |
| -- | -- | -- |
| M5 fragment-fakta med korrekt löst citat | 9/10 (rättad från 10/10) | **10/10 i alla tre pass** |
| Prosakontroller besvarade med stött citat | 2/2 | 2/2 i alla tre pass |
| Obesvarbara avvisade med noll citat | 2/3 | **3/3 i alla tre pass** |
| **M7 fabricerade källhänvisningar** | **0** | **0** |
| Citat oberoende lösta mot extraktionen | 13/13 | **42/42** |

Rättelsen 10/10 → 9/10 gjordes av piloten själv (g24: `Driftia
Fastighetsservice AB` är *teknisk* förvaltare; facit är `SBC Sveriges
BostadsrättsCentrum AB`) och det ursprungliga felaktiga svaret bevarades med
genomstrykning. Kallgranskningen bedömde det som en höjd ribba, inte en tyst
förbättring. Efter slinga 3 gäller två kontroller per fråga som inte får slås
ihop: (1) löser citatet mot extraktionen, (2) är svaret rätt mot facit.

### 2.5 Felbeteende

| Fel | Vad produkten gjorde | Bevis |
| -- | -- | -- |
| SSH-tunneln stängd (C3) | En fråga med bevisat stöd gav `OTILLRÄCKLIGT UNDERLAG` + `Tekniskt fel vid svarsgenerering`, **noll citat**, inget grundat-utseende svar | slinga 3 §4; `ERROR brf.answer: … ConnectError` |
| Backenden dödad med SIGTERM (C4) | Arbetsfönstret stängdes, skalet levde, felfönster med **TEKNISK ORSAK: avslutades av signal 15**; hela `data/`-trädet oförändrat `23e27246…` | slinga 3 §4.5 |
| Värddatorns strömbortfall mitt i pass | Trettio läsande återtagningskontroller: `PRAGMA integrity_check` `ok`, `foreign_key_check` tom, 5 dokument/13 chunks, alla PDF:er bit-identiska, Btrfs `device stats` alla noll | `slinga2-atertagning-efter-vardkrasch.md` |

### 2.6 Data över säkerhetskopiering, återställning och paketbyte

| Arbetspunkt | Utfall | Bevis |
| -- | -- | -- |
| **D1** kopia genom produktens eget UI | `brfv2-backup-20260730-145457-9999.zip`, 62 578 byte, 16 poster, `unzip -t` rent, `auth.db` i arkivet bit-identisk, SHA-256 `5fe53c7a…` identisk lokalt och på annan media, katalog `700` / fil `600` | slinga 4 §3 |
| **D2** återställning mot avsiktlig avvikelse | Avvikelsen (`aaab8211…`) rullades tillbaka till **exakt** `23e27246…`; `last-restore.json` `{"status":"restored"}`; bytet skedde vid nästa start, aldrig under öppna SQLite-handtag | slinga 4 §3 |
| **D3** avinstallation och ominstallation | `dnf remove` frigjorde 772 MiB, datakatalogen låg kvar byte-identisk; efter ominstallation `rpm --verify` 0, `deliveryTree` `a702a337…`, 45/0, fem dokument listade vid namn, ingen inloggning krävdes | slinga 4 §4 |
| **D4** katastrofövning — produkten mötte en tom installation | Produkten visade `Välkommen`, listade alla tre säkerhetskopiorna, återställde `5fe53c7a…`, och `data/`-trädet blev **exakt** `23e27246…` med det ursprungliga kontot tillbaka och drillkontot borta | slinga 4 §9 |
| **M8** | 1 kopia + **2** återställningsövningar, båda med korrekt data efteråt | slinga 4 §9.10 |
| **M9** | 1 av-/ominstallationscykel med bevarad data | slinga 4 §4 |

### 2.7 Stoppkriterier

Alla sju stoppkriterier prövades var för sig i varje slinga och av
kallgranskaren. **Inget utlöstes.** Kriterium 4 (fabricerad källhänvisning)
bedömdes särskilt: `0 fabrications; g24 baseline error was wrong-but-supported
selection, corrected methodologically`. Kriterium 7 (tre oförklarade
backend-dödsfall) hade en avsiktlig SIGTERM och ett förklarat strömbortfall —
noll oförklarade trippel.

Kriterium 1 (korsföreningsläckage) är **inte** bevisat. Det kan inte prövas
meningsfullt med en enda tenant, och evidensen säger det uttryckligen.

### 2.8 BP5-kallgranskningens verdikt

> **PASS BP5 — CONTROLLED SINGLE-OPERATOR FEDORA PILOT VERIFIED**

Kallgranskaren körde om artefaktidentitet, `rpm --verify`, `inspect_payload
--installed` (45/0), leveransträdet, leverantörsvalet, den levande
datakatalogens filnivåidentitet mot D1-kopian (15/15 bit-identiska) och
rekonstruerade sidtexten ur extraktionen för att verifiera **14/14 citat**
oberoende. Slutsatsen: *"No contradiction was found that reverses a loop PASS
or trips a stop criterion."*

---

## 3. Vad som accepterades **endast** inom enanvändarpiloten

Följande medgivanden vilar uteslutande på att piloten hade en maskin, en
människa, syntetisk korpus och ingen distribution. Inget av dem är en
egenskap hos produkten som kan bäras vidare.

1. **Osignerad RPM.** Identiteten kontrollerades i stället mot SHA-256
   `6ba028fb…` före varje installation. `dnf`s OpenPGP-varning var väntad.
2. **Ingen bevisad uppgraderingsväg.** Endast version 0.2.0 kördes; versionsbyte
   skedde som säkerhetskopia → avinstallation → installation → verifiering.
3. **Lokal tillitsgräns = OS-användaren.** Den som kör som samma Unix-användare
   kan läsa och skriva applikationens data direkt, förbi API:t.
4. **Tangentbordsotillgängliga `Appinställningar`.** Accepterat därför att
   piloten hade en operatör med mus som kunde nå allt.
5. **B3 stängd med 7 av 8** på grund av Shift+Enter-felet.
6. **`Settings.aiModel = "claude-opus-4-8"`** som deklarerad, oanvänd
   defaultsträng: att ändra den skulle flytta artefaktens bytes och upphäva
   BP2-underlaget.
7. **Stort paket** (574 604 029 byte; 772 MiB installerat) — pilotmaskinen hade
   356 GB fritt.
8. **Säkerhetskopior lokalt bredvid datakatalogen**, kompenserat av runbookens
   krav att flytta kopian till annan media efter varje pass med ny data.
9. **Ingen telemetri** — journalen *är* hela mätinsamlingen.
10. **`pending-restore.zip` `0644`.**
11. **14-dagarssessionen.**
12. **D4:s karantänmetod** i stället för verklig radering.
13. **Ägarskap delvis `TBD`.** Endast backup/återställningsövning och
    incidenthantering är stängda, och endast för pilotens omfattning.
    Supportvägen var operatören själv: ingen jour, ingen svarstid, ingen andra
    linje.
14. **Personuppgifter i installationen.** Pilotplanen skrev `Personuppgifter:
    Inga`, men uppstartsdialogen kräver namn och e-post, så
    installationsadministratörskontot innehåller operatörens verkliga namn och
    e-postadress i `data/auth.db`. Hanterat operativt — ingen datakatalog, ingen
    säkerhetskopia och ingen `auth.db` är committad — men planens text motsäger
    verkligheten och det är dokumenterat som en öppen omfångsavvikelse.

---

## 4. Kända begränsningar

Samtliga, med den faktiska formuleringen och var den är dokumenterad.

### 4.1 Ogiltig M10

M10 skulle mäta tiden från okonfigurerad maskin till första grundade svar och
skulle mätas **en gång**. `T0_förberedd` 2026-07-29 21:07:22, `T0_operatör`
21:14:52.838, `T1` 2026-07-30 04:57:26 — båda intervallen innehåller en
**~7 h 15 min nattlig paus**. Journalen redovisar M10 som *"mätt men ogiltigt"*
och konstaterar att möjligheten är förbrukad utan ett användbart värde. Den
observerade **aktiva** tiden var ≈ 35 minuter, varav 7 min 30 s för att hitta
menyposten. Tre förkastade `T0_förberedd`-stämplar redovisas öppet i stället
för att skrivas över. Kallgranskningen listar *"a valid M10 friction
measurement"* under **unsupported scope**.
*Källa:* `JOURNAL.md`, BP4-3 §6, BP5-COLD-REVIEW §6.2 och §10.

### 4.2 Shift+Enter radbryter inte

Shift+Enter skickar meddelandet i stället för att radbryta. Två oberoende
strukturella orsaker: kontrollen är `<input type="text">`, inte `<textarea>`
(ett enradigt fält *kan inte* innehålla en radbrytning), och handlaren saknar
`shiftKey`-kontroll. `brfv2-mockup/src/App.jsx:1522–1526` och `1107–1111`.
**Flerradig inmatning finns inte implementerad**, så en `shiftKey`-kontroll
skulle bara göra att ingenting händer. Runbookens smoke-steg 2 beskriver därmed
en förmåga produkten inte har och aldrig har haft. Filerna ligger i
`REPRO_DELIVERY_PATHS` — att åtgärda hade flyttat artefaktens bytes, så
åtgärden var förbjuden under piloten.
*Källa:* `JOURNAL.md` avvikelse S3/F, `slinga2-forstastart.md` B3 steg 2.

### 4.3 Tangentbordsotillgängliga Appinställningar

Fokusringen i dokument-/chattvyn är en sluten cykel om sex element, uppmätt
genom 22 `Tab`-tryck. Ingången till menyn är `<div className="user-profile">`
**utan `tabIndex`** (`brfv2-mockup/src/App.jsx:863`), alltså inte fokuserbar.
Följden: en tangentbordsberoende operatör kan varken probe:a modelltjänsten,
ändra modelladressen eller skapa säkerhetskopia. Avgränsning: dialogernas
knappar och hela `Appinställningar` **är** nåbara med tangentbord när menyn väl
är öppen — det är **ingången** som saknar tangentbordsväg.
*Källa:* `slinga3-upprepade-arbetspass.md` §2 och §7, PILOTPLAN §9 begränsning 13.

### 4.4 14-dagarssession

Sessionen skapades 2026-07-29 21:24 med giltighet till 2026-08-12T19:24:08Z.
`backend/app/auth.py` använder `BRF_SESSION_TTL_HOURS` med default `336`;
`backend/app/desktop.py` sätter cookien `httponly`, `samesite=lax`,
`path=/api/`, `max_age = 14*24*3600`. Sessionen har överlevt tre appstarter, en
backendkrasch, en återställning, ett paketbyte och en fullständig återuppbyggnad
av `data/`. En pilotmaskin som kraschar och startar om är alltså fortfarande
inloggad i upp till fjorton dagar utan att någon behöver kunna lösenordet.
Detta är **inte** ett fel mot skriven kravbild. En start med *utgången* session
är oprövad.
*Källa:* `slinga2-atertagning-efter-vardkrasch.md` §4.3, BP4-4 §4.2.

### 4.5 `pending-restore.zip` skrivs `0644`

`stage_restore()` sätter `0700` på katalogen men kopierar arkivet med
`shutil.copyfile` + `os.replace` **utan `os.chmod` på filen**, så den får
processens umask. Säkerhetskopiorna den kopieras från har `0600`. Katalogen är
`0700`, så filen är inte exponerad för andra konton — men den innehåller
`auth.db` med operatörens verkliga namn och e-postadress, och dess filläge är
lösare än originalets. `backend/app/desktop.py`, i `REPRO_DELIVERY_PATHS` →
fick inte åtgärdas under piloten.
*Källa:* `slinga4-sakerhetskopiering-och-paketbyte.md` §3.5 och §7, BP4-4 §4.1.

### 4.6 D4:s karantänmetod

Det som gjordes var en **atomär flytt, inte en radering**: katalogen flyttades
med `mv` (rename på samma filsystem, device 52) till en skyddad karantänsökväg.
Driftvillkoret som prövas är identiskt med förlust — produkten ser ingen
`data/` — men beteendet vid **fysisk radering av bytes** påstås inte. Metoden
valdes uttryckligen för att den inte kräver att sessionens spärr mot rekursiv
radering kringgås, och den kringgicks inte. Även efterpassets `rm -rf` av
karantänkopian påstår ingen kryptografisk radering (btrfs, copy-on-write).
Kallgranskningen: *"Product-visible condition (path missing) is the same;
block-reuse after true deletion is unproven."*
*Källa:* `slinga4-…md` §9.1 och §9.10, BP4-4 §3, BP5-COLD-REVIEW §6.4.

### 4.7 Osignerad och stor RPM

`%{SIGPGP}` = `(none)`. SHA-256-kontrollen före varje installation är det som
ersätter signaturen. Storleken är 574 604 029 byte komprimerat och 772 MiB
installerat, varav **513 MiB är embeddervikterna i float32**
(`model.safetensors`, 512 361 560 byte). Kvantisering skulle halvera paketet men
ändrar retrievalvektorerna och kräver egen utvärdering mot golden set.
*Anmärkning:* fyra olika sifferpar för i praktiken samma paket cirkulerar i
materialet (PILOTPLAN §9 skriver `548 MiB / 773 MiB`, som är XS-49:s artefakt;
ADR 0001 `~700 MB` och `776 MB`; XS-47 `547 MiB / 769 MiB`). De mätvärden som
gäller pilotens artefakt är de i denna rapport.
*Källa:* PILOTPLAN §9 begränsning 1 och 5, `xs49-desktop-delivery.md`.

### 4.8 Syntetisk korpus

Fem deterministiskt renderade PDF:er, index 5 dokument / 13 chunks. *"Ingenting
i slinga 3 säger något om verkliga stadgar eller årsredovisningar."* Att släppa
in riktig korpus kräver ett eget grindbeslut **och** att ägarbesluten i drift-
och förvaltningsplanen stängs först.
*Källa:* PILOTPLAN §2, `slinga3-…md` §8.1, risk R11.

### 4.9 Ingen `dnf upgrade`

Bara version 0.2.0 finns; en `dnf upgrade` från en tidigare version har aldrig
körts. Det finns **inget versionsfält och ingen migreringsmekanism** i
`documents.json`, `tenant_meta.json` eller `auth.db`. Runbooken föreskriver
därför versionsbyte i sex steg via säkerhetskopia.
*Anmärkning:* `xs47-desktop-delivery.md` påstår att datakatalogen är
versionsmärkt via `schemaVersion` i `desktop-config.json`. Det fältet finns men
versionerar konfigurationsfilen, inte datalagren. PILOTPLAN §4.3 är den korrekta
beskrivningen.
*Källa:* PILOTPLAN §2 och §4.3, RUNBOOK "Återgång" §3.

### 4.10 Ingen delad-maskin-verifiering

Skyddet är inte ett skydd mot OS-användaren själv. Datakatalogen är `0700`, men
det är **föräldrakatalogens** `0700` som bär gränsen — WebKits fem egna poster i
samma katalog är `0755`/`0644`. Korsföreningsisolering (stoppkriterium 1) är
oprövad i piloten: den kan inte prövas meningsfullt med en tenant, och det ska
inte läsas som att isoleringen är bevisad.
*Källa:* ADR 0002 "Vad detta *inte* är", slinga 2 B0.

### 4.11 Ingen bred OS-verifiering

Endast Fedora 44, endast KDE/Wayland, endast en maskin. `%{dist}`-makrot
(`.fc44`) ingår medvetet i artefaktens identitet: *"Reproducerbarheten som visas
är på samma Fedora-version, inte tvärs över distributioner."* RPM:en kräver
`webkit2gtk4.1`, `gtk3`, `tesseract` och `tesseract-langpack-swe`
**oversionerat**; en uppgradering av de två första kräver omkörd acceptans
(C5 utlöstes aldrig under piloten).
*Källa:* ADR 0003 "Konsekvenser", PILOTPLAN §9 begränsning 7.

### 4.12 Ingen fullständig tillgänglighetsverifiering

Tangentbordsvägen täcks endast av operatörsattestering med verktygsstöd (7 av
8), inte av automatkörning. Acceptansens `uiJourney.keyboard` deklarerar
`nativeWaylandAutomation: "blocked by this KWin/WebKit automation environment"`
och `nativeWebDriverElementValue: "unsupported by WebKitWebDriver for WRY"`.
Injektionsverktyget tappade `å`, `ö` och `?` — teststrängarna bär spår av det.
Sidindikatorn `Sida N av M` exponeras inte i AT-SPI. **Ingen WCAG-granskning,
ingen skärmläsartestning och ingen kontrast- eller fokusgranskning finns i något
evidensdokument.** `Appinställningar` är inte nåbar utan pekare (§4.3).
*Källa:* PILOTPLAN §6.4 och §9 begränsning 3 och 13, `JOURNAL.md`
"Evidensklassens gräns", BP5-COLD-REVIEW §10.

### 4.13 Evidensklassernas gräns

Slinga 3 och slinga 4 har **inga skärmbilder alls** — läsningen gjordes ur
a11y-trädet. De enda pilotskärmbilderna är de fem klass-P-filerna från
acceptanskörningen, som visar acceptansens syntetiska förening `Brf Gjutformen
12` i ett tillfälligt datahem, **inte pilotinstallationen**. Slinga 3 och 4 är
*agentkörning med verktygsstöd genom produktens verkliga fönster*, inte
operatörsattestering. Endast slinga 2:s B3 är operatörsattesterad.
*Källa:* `EVIDENSREGISTER-XS56.md` klass U.

### 4.14 Dokumentationsluckor som kvarstår

* **Aggregatsummans formel.** `23e27246…` används genomgående som `data/`-trädets
  identitet, men kallgranskaren kunde inte återskapa den med en enkel
  `find | sha256sum | sha256sum`-pipeline (fick `f7ba3e77…`). Filnivåidentitet
  mot D1 (15/15) användes i stället. Formeln är odokumenterad. Kallgranskningen:
  *"a documentation gap, not evidence of data loss."*
* **Datakontraktet §4.3 är ofullständigt.** Fem odokumenterade WebKit-poster
  (`CacheStorage/`, `WebKitCache/`, `storage/`, `mediakeys/`,
  `hsts-storage.sqlite`) finns i datakatalogen. `docs/DESKTOP-FEDORA.md` utelämnar
  dessutom `logs/` ur sin layout.
* **Runbookens S1-rutin** påstår att `data-snapshot` går att spara och dela
  därför att korpusen är syntetisk. Det stämmer inte längre utan förbehåll:
  `auth.db` och varje säkerhetskopia innehåller en personuppgift. Kvalificeringen
  är inte gjord i runbooken.
* **Begränsning 3:s premiss** ("fysisk Wayland-tangentbordsinjektion ej
  automatiserad") motsägs delvis av piloten: tangentbord *var* automatiserbart i
  den miljön, pekaren först efter platt accelerationsprofil.
* **M4-etiketten** skärptes från "oväntade" till "oförklarade", men det gamla
  ordvalet står kvar på flera ställen. Sakinnehållet är 0 i alla mätningar.
* **`slinga2-forstastart.md` §B5 bär den orättade 10/10-baslinjen**; rättelsen
  till 9/10 finns bara i journalen.
* **`xs51-desktop-acceptance-installed.json`** namnger fem `xs49-*`-skärmbilder
  som inte är dess egna — samma defekt som slinga 1:s A3 senare stängde.
* **`slinga4-…md` §6 och §9 säger emot varandra om D4**, avsiktligt: filens
  förord förklarar att kronologin är en del av evidensen. §9 ersätter §6. Samma
  gäller M8 (§5 säger 1 återställning, §9.10 säger 2 — 2 är rätt). Den som
  citerar §5 eller §6 isolerat får fel svar.
* **PILOTPLAN §6.5:s regressionsbaslinje** (650/3) uppdaterades aldrig till den
  faktiska 657/3 efter A3.
* **`xs49-*`-acceptansfilerna är inte evidens för pilotens artefakt** — de bär
  `deliveryTree 9c996ddf…` och artefakt `f8ddb770…`, en annan generation, och
  saknar `providerExclusion` helt.

---

## 5. Vad som krävs före en **bredare pilot**

Bredare pilot = mer än en människa, mer än en maskin, eller riktig korpus.

| # | Krav | Varför |
| -- | -- | -- |
| B1 | **Hotmodell för delad maskin** | Nuvarande tillitsgräns är OS-användaren. Den är verklig men ingen annan part var exponerad. |
| B2 | **Korsföreningsisolering bevisad med ≥2 tenants** | Stoppkriterium 1 är oprövat. Isoleringen är implementerad men inte demonstrerad i skrivbordsformen. |
| B3 | **Tangentbordsväg till `Appinställningar`** (§4.3) | En tangentbordsberoende deltagare kan annars inte säkerhetskopiera eller konfigurera modelltjänsten. |
| B4 | **Flerradig inmatning i chattfältet** (§4.2) | Runbooken beskriver en förmåga som inte finns. |
| B5 | **Beslut om sessionslängd** (§4.4) | 14 dygn utan lösenord på en maskin med fler människor är en annan risk än på en. |
| B6 | **`pending-restore.zip` `0600`** (§4.5) | Filen innehåller `auth.db` med personuppgifter. |
| B7 | **Ägarbeslut stängda**: modellruntime, korpus-/dataförvaltning, GDPR-kontakt, godkännande av produktionsändringar | Idag `TBD`. Supportvägen "operatören själv" håller bara när ingen annan är beroende av installationen. |
| B8 | **Riktig korpus som eget grindbeslut** (§4.8) | Ingenting i piloten säger något om verkliga stadgar eller årsredovisningar. |
| B9 | **Villkoret för obesvarbara frågor avgjort** | Det enda formellt oavgjorda utvärderingsvillkoret: noll citat, eller kvalificerat icke-svar med stött citat? |
| B10 | **Personuppgiftshanteringen skriven, inte underförstådd** (§3.14) | Planen säger "Inga"; verkligheten säger annat. |
| B11 | **Aggregatsummans formel dokumenterad** (§4.14) | En evidenskedja som inte går att återskapa är inte en evidenskedja. |
| B12 | **Datakontraktet §4.3 komplett** (§4.14) | Fem odokumenterade poster i datakatalogen. |

---

## 6. Vad som krävs före **distribution eller produktion**

Distribution = paketet lämnar den maskin det byggdes på.

| # | Krav | Varför |
| -- | -- | -- |
| P1 | **Signering av paketet** | `%{SIGPGP}` = `(none)`. En SHA-256 som kontrolleras för hand ersätter en signatur för en människa, inte för många. |
| P2 | **Uppdateringskanal och bevisad `dnf upgrade`-migrering** | Det finns inget versionsfält och ingen migreringsmekanism i datalagren. |
| P3 | **Fysisk radering bevisad, inte karantän** (§4.6) | Block-reuse efter verklig radering är obevisat. |
| P4 | **Tillgänglighetsgranskning: WCAG, skärmläsare, kontrast, fokus** (§4.12) | Ingenting av detta finns i evidensen. |
| P5 | **Bred OS-verifiering** eller uttrycklig plattformsbegränsning | Endast Fedora 44 / KDE Wayland är prövat, och `.fc44` ingår i artefaktidentiteten. |
| P6 | **Versionerade `Requires:`** eller omkörd acceptans som release-villkor | `webkit2gtk4.1` och `gtk3` krävs oversionerat; risk R1 är öppen. |
| P7 | **Paketstorlek adresserad** (§4.7) | 513 MiB float32-vikter. Kvantisering kräver egen golden-set-utvärdering. |
| P8 | **Support- och incidentåtagande** | Ingen jour, ingen svarstid, ingen andra linje idag. |
| P9 | **`Settings.aiModel`-defaulten rensad** | `claude-opus-4-8` är en deklarerad, oanvänd sträng i en produkt som inte får nå en värdbaserad leverantör. Ofarlig men förvirrande. |
| P10 | **En verklig M10-mätning** | Friktionsmåttet som effektmålet vilar på saknas fortfarande. |

---

## 7. Repositorytopologi

Fedora-piloten är en **fryst släpplinje parallellt med mobilspåret på `main`**.
BP6 gör **ingen** produktintegration mellan dem.

```
1cd65ca  gemensam webbaslinje
   │
   ├── desktoplinjen (fryst)
   │     5723676 XS-46 → 823a3d7 XS-47 → ac3cd2b XS-49 → 84b6fc8 XS-51
   │     → 35b67ee XS-53 → 7cd1f92 XS-54 → c6db95a XS-55 → 813f26d XS-56
   │     → a5a112b XS-57 → d6e73bf BP5-kallgranskning
   │     → bp6/fedora-pilot-closeout  ← denna rapport
   │        taggad v0.2.0-fedora-pilot
   │
   └── produktlinjen
         414f6f7 → 8edc99f → 991349d → 535427c → acd39de (origin/main)
         → 3bc78bd (feat/kalla-mobile-pwa, taggad traff-mobile-rc1)
```

Linjerna divergerar från samma bascommit. Mobilspåret ändrar delade backend- och
authfiler (`backend/app/auth.py`, `backend/app/main.py`,
`backend/tests/test_api.py`). En merge i BP6 hade därför varit ny
produktintegration och lämnat den kallgranskade pilotens scope.

**Beslutad policy, oförändrad genom detta avslut:**

* `main` och mobilspåret lämnas orörda;
* ingen merge, squash, rebase, cherry-pick eller force-push mellan linjerna;
* Fedora-piloten avslutas på sin egen frysta linje;
* den verifierade desktophistoriken bevaras oförändrad och görs nåbar genom
  branch och annoterad tagg.

Fortsatt produktutveckling sker **inte** på den här grenen. Den sker på
produktlinjen, där desktopens produktförmågor porteras fram semantiskt.

---

## 8. Backlog — får inte implementeras i BP6

XS-58 (radbrytning i chattfältet, §4.2) och samtliga övriga förbättringar i §5
och §6 är backlog. Den här closeoutens diff är dokument-only: ingen produktkod,
ingen paketering och ingen historisk pilotevidens ändras.

Klass F-punkter som väntar: Shift+Enter/flerradig inmatning, `tabIndex` till
`Appinställningar`, `pending-restore.zip` `0644`, `Settings.aiModel`-defaulten,
signering, `dnf upgrade`-migrering, automatiserbar fysisk tangentbordsväg,
kvantisering av embeddervikterna, hotmodell för delad maskin, sessionslängden.

Erfarenhetsåterföring utan produktändring: `OTILLRÄCKLIGT UNDERLAG` återanvänds
som rubrik vid leverantörsfel; `backend.log` saknar tidsstämplar och nämner inte
backendens död; `ERROR`-nivå för det förväntade förstagångsläget `BRF_LLM_BASE_URL
saknas`; fem bit-identiska dubbletter togs emot utan varning; överinkluderande
svar på g17 och g44; minnestopp 2,1 GB / 787,8 MB swap på en 27-minutersinstans.

---

## 9. Slutsats

Piloten svarade på sin fråga. Artefakten går att leva med som skrivbordsprogram
på den maskin och för den människa den prövades på: fyra menystarter, noll
terminalingripanden för att använda produkten, noll fabricerade källhänvisningar,
42 av 42 citat lösta, och data som överlevde ett strömbortfall, en dödad backend,
ett paketbyte och en katastrofövning — varje gång tillbaka till exakt samma
trädsumma.

Den svarade också ärligt på vad den *inte* kan säga. M10, det mätvärde
effektmålet vilar på, är ogiltigt och möjligheten är förbrukad.
Korsföreningsisoleringen är oprövad. Tillgängligheten är delvis trasig och
oundersökt. Paketet är osignerat. Korpusen är syntetisk. Ingen annan människa
har installerat det.

Det är en avslutad pilot, inte en påbörjad produktleverans.

**Rekommendation till BP6:** se `BP6-BESLUTSUNDERLAG.md`.
