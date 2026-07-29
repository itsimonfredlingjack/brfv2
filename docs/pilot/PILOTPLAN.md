# Pilotplan — kontrollerad Fedora-pilot av BRF Dokument-AI (skrivbord)

**Grind:** Planering → BP3. **Status:** underlag, inte beslut.
**Skriven:** 2026-07-29, mot den frysta BP2-baslinjen.
**Beslutsunderlag:** [BP3-BESLUTSUNDERLAG.md](BP3-BESLUTSUNDERLAG.md).
**Genomförandeinstruktion:** [RUNBOOK-PILOT.md](RUNBOOK-PILOT.md).

Den här planen beskriver hur en pilot ska bedrivas. Ingenting i den är
genomfört, och ingenting i den godkänner sig självt. Planeraren fattar inte
BP3-beslutet.

---

## 1. Den frysta baslinjen

BP2 godkändes 2026-07-29 med den formella lydelsen
`PASS BP2 — TAURI 2 FOR CONTROLLED FEDORA PILOT` (XS-52, oberoende kall
granskning). Piloten körs mot exakt den artefakten och ingen annan.

| | |
| --- | --- |
| Commit | `84b6fc853ec047fe9b438f2e1c0a2aed08cfe754` |
| `deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| Artefakt | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| Storlek | 574 604 029 byte |
| SHA-256 | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |

### Vad som är verifierat på pilotmaskinen redan nu

Kontrollerat under planeringen 2026-07-29 på den tänkta pilotmaskinen
(Fedora 44, kernel `7.1.5-200.fc44.x86_64`), läsande kommandon:

| Kontroll | Kommando | Utfall |
| --- | --- | --- |
| Paketet är installerat | `rpm -q brf-dokument-ai` | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| Installerat träd = paketet | `rpm --verify brf-dokument-ai` | exitkod 0, inga skillnader |
| Installationen är den godkända | `BUNDLE.json.deliveryTree` | `a702a337…` — identisk med BP2-baslinjen |
| Leverantörsgränsen håller i det installerade trädet | `ops/inspect_payload.py --installed` | 45 kontroller, **0 fynd** (4675 filer) |
| Skalets identitet | `sha256sum /usr/bin/brfv2-desktop` | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` |
| Ingen användardata finns ännu | `ls ~/.local/share/se.brfdokumentai.desktop` | katalogen saknas |
| Diskutrymme | `df -h /home` | 356 GB fritt |

Två konsekvenser för planen:

1. **Piloten behöver inte installera om något för att börja.** Den godkända
   artefakten sitter redan på maskinen och det installerade trädet är
   bitidentiskt med paketet.
2. **Första starten blir en genuin förstagångsstart.** Ingen datakatalog
   finns, så uppstartsdialogen och installationsadministratörens tillkomst
   kan observeras på riktigt en gång — inte simuleras.

### Vad som saknas i den här arbetskopian

| Saknas | Betydelse |
| --- | --- |
| `dist/…rpm` — själva paketfilen | Utan den går det inte att installera om efter en avinstallation. Ombygge ger samma bytes (bevisad reproducerbarhet), men det är ett ombygge, inte en återställning. Arbetspunkt A1. |
| `backend/.venv` | Krävs för acceptans, artefakttester och pytest. `make setup`. Arbetspunkt A1. |

---

## 2. Pilotens omfattning

**En maskin, en människa, syntetisk korpus, självhostad modell.**

| Dimension | Beslut |
| --- | --- |
| Maskiner | En: den Fedora 44-maskin där paketet redan är installerat |
| Deltagare | En: Simon Fredling Jack, tillika installationsadministratör och operatör |
| Korpus | Endast syntetisk demokorpus (`backend/eval/golden.json`, fem dokument) |
| Personuppgifter | Inga |
| Modelltjänst | Gemma 4 12B på `agenntserver`, nådd som loopback via `ssh -N -L 8000:127.0.0.1:8000 agenntserver` |
| Artefakt | Uteslutande `6ba028fb…`; ingen annan version installeras under piloten |
| Distribution | Ingen |

**Det piloten ska avgöra:** om den godkända artefakten går att *leva med* som
skrivbordsprogram över upprepade verkliga arbetspass — installation, första
start, dagligt bruk, säkerhetskopiering, återställning, avinstallation och
ominstallation, samt de fel som faktiskt inträffar — utan att operatören
behöver terminalen för annat än SSH-tunneln.

Det knyter an till projektets effektmål (Effekt-milstolpen: *minskar
desktopformen operatörsfriktion, förbättrar installation och ökar
användbarheten utan att försämra säkerhet eller underhållbarhet*). Piloten
mäter den friktionen i stället för att anta den.

### Uttryckliga exkluderingar

Följande ligger utanför piloten och får inte smygas in i den:

* distribution till annan maskin eller annan människa;
* riktig BRF-korpus, kunddokument eller personuppgifter;
* signering av paketet, paketrepo eller uppdateringskanal;
* `dnf upgrade` mellan versioner — ett versionsbyte under piloten sker som
  säkerhetskopia → avinstallation → installation → verifiering;
* andra operativsystem, andra Fedora-versioner än 44, andra skrivbordsmiljöer
  än den verifierade KDE/Wayland-sessionen;
* **ändringar i `REPRO_DELIVERY_PATHS`** (se §4) — en sådan ändring gör att
  artefakten inte längre är den BP2 granskade;
* de parkerade produktytorna (global sök, dokumentbunden chatt,
  kvalitetskontroll, bevakningar) som ska förbli onåbara;
* kvantisering av embeddervikterna för att minska paketet — egen utvärdering
  mot golden set krävs, och den tillhör inte piloten.

### Vad piloten inte kan avgöra

Detta får inte läsas in i ett senare BP5-godkännande:

* att någon **annan** människa kan installera paketet — det finns ingen andra
  maskin och ingen andra användare i piloten;
* att produkten håller mot **verkliga** stadgar och årsredovisningar — korpusen
  är syntetisk;
* att osignerad distribution är acceptabel — ingen distribution sker;
* att uppgraderingsvägen fungerar — det finns bara en version;
* att den lokala tillitsgränsen (OS-användaren) räcker på en delad maskin.

---

## 3. Arkitektur — beslutad och fryst

Arkitekturbeslutet togs vid BP2 och öppnas inte här. Kortfattat, som referens:

```
brfv2-desktop (Rust/Tauri 2)
 └─ startar  runtime/python/bin/python3 -E -s -B -m app.desktop
     ├─ binder 127.0.0.1:0 (OS-vald port)
     ├─ serverar /brfv2/* och /api/* från SAMMA origin
     └─ skriver ett maskinläsbart readiness-kontrakt på stdout
 └─ validerar kontraktet innan fönstret skapas
 └─ navigation endast till exakt den origin; nya fönster nekas
 └─ tom `capabilities`, `withGlobalTauri: false`, inga plugins → ingen IPC-yta
 └─ exitkod 86 = omstart; annat = felfönster
```

Beslutsunderlagen finns i [`adr/0001`](../adr/0001-desktop-python-runtime.md),
[`adr/0002`](../adr/0002-model-endpoint-boundary.md) och
[`adr/0003`](../adr/0003-reproducerbar-rpm.md). Ett genuint pilotblockerande fynd
är enda skälet att öppna dem igen.

---

## 4. Kontrakt

Det piloten får förlita sig på, och det piloten inte får röra.

### 4.1 Vad som får ändras utan att artefakten rörs

Artefakten är en funktion av `REPRO_DELIVERY_PATHS`
([`ops/lib/repro.sh`](../../ops/lib/repro.sh)) och ingenting annat. Under piloten
får dessa ändras fritt:

* `docs/**` — planer, runbooks, evidens, journal;
* `backend/scripts/**` — acceptans, seed, hjälpverktyg;
* `backend/tests/**` — tester;
* `Makefile`, rotens `src/`-prototyp, `README.md`.

Dessa får **inte** ändras under piloten: `backend/app`, `backend/pyproject.toml`,
`backend/uv.lock`, `backend/.python-version`, `brfv2-mockup/{src,public,index.html,package.json,package-lock.json,vite.config.js}`,
`src-tauri`, `ops/{pins.json,fetch_pinned.py,lib,build-runtime.sh,package-desktop.sh,brf-dokument-ai.spec,forbidden_providers.json,prune_payload.py,inspect_payload.py}`.

Kontrollen är mekanisk, inte en hedersregel:

```bash
git ls-tree -r HEAD -- backend/app backend/pyproject.toml backend/uv.lock \
  backend/.python-version brfv2-mockup/src brfv2-mockup/public \
  brfv2-mockup/index.html brfv2-mockup/package.json brfv2-mockup/package-lock.json \
  brfv2-mockup/vite.config.js src-tauri ops/pins.json ops/fetch_pinned.py ops/lib \
  ops/build-runtime.sh ops/package-desktop.sh ops/brf-dokument-ai.spec \
  ops/forbidden_providers.json ops/prune_payload.py ops/inspect_payload.py \
  | sha256sum
# ska vara a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083
```

Avviker den summan är artefakten inte längre den BP2 granskade, och piloten är
inte längre en pilot av den godkända produkten.

### 4.2 Modellgränsen

Maskinläsbar på `GET /api/desktop/model-endpoint-policy`. Två driftklasser:
loopback (`http` eller `https`) och eget privat nät (endast `https`). Allt annat
avvisas. Endast installationsadministratören får peka om adressen. Pilotens
adress är `http://127.0.0.1:8000/v1` — loopbackänden av SSH-forwarden.

### 4.3 Datakontrakt

```
~/.local/share/se.brfdokumentai.desktop/     (0700)
├── data/            föreningar, PDF:er, index, konton, appkonfiguration
├── backups/         säkerhetskopior (zip)
├── restore-staging/ förberedd återställning
└── logs/            backend.log, backend.log.1
```

Katalogen ligger kvar vid av- och ominstallation. Det finns inget versionsfält
och ingen migreringsmekanism i `documents.json`/`tenant_meta.json`/`auth.db` —
därav pilotens versionsbytespolicy i §2.

### 4.4 `ready` är inte nåbarhet

`/api/health`s `ready` är konfigurationsstatus (`provider ∉ {none, fake}`), inte
en aktiv nätverksprobe. Faktisk nåbarhet bevisas av probe-anropet som
installationsadministratören kan utlösa, och av ett verkligt svar. Därför
innehåller sessionschecklistan en probe, inte en blick på `ready`.

---

## 5. Arbetsuppdelning

Fyra slingor. Varje slinga slutar i en BP4-avstämning: något demonstrerbart,
dess evidens, och vad den *inte* visade. Ingen slinga har ett datum; nästa
slinga börjar när föregående BP4 är skriven.

**Ägare genomgående:** Simon Fredling Jack beslutar och opererar; agent i
repo-sessionen utför och skriver evidens. Kall granskning inför BP5 görs av en
fristående session utan bygghistorik.

### Slinga 1 — pilotmiljön är verklig och återställbar

| # | Arbete | Beroende |
| --- | --- | --- |
| A1 | `make setup`; bygg om artefakten från `84b6fc8` i ren checkout; verifiera SHA-256 = `6ba028fb…`; arkivera RPM + `*.provenance.json` **utanför `dist/`** (rotens `npm run build` raderar `dist/`) | — |
| A2 | Kör om baslinjekontrollerna i §1 och skriv in dem som pilotens startevidens | A1 |
| A3 | Åtgärda den hårdkodade `xs49-*`-namngivningen i `backend/scripts/desktop_acceptance.py` så att en acceptanskörning inte kan skriva över committad XS-49-evidens; verifiera efteråt att leveransträdet är oförändrat (§4.1) | — |
| A4 | Skriv ut den syntetiska korpusens fem PDF:er till fil ur `scripts.seed.render_pdf` så att de kan laddas upp genom produktens egen väg | — |
| A5 | Lägg upp pilotjournalen (`docs/pilot/JOURNAL.md`) — produkten har ingen telemetri, mätvärdena finns bara om de skrivs ned | — |

**BP4-1 visar:** pilotmiljön kan återställas från arkiverad artefakt, och
evidensinsamlingen kan inte skada tidigare evidens.

### Slinga 2 — första installationen och första start

| # | Arbete | Beroende |
| --- | --- | --- |
| B1 | Öppna SSH-tunneln; verifiera att port 8000 annonserar Gemma 4 12B | — |
| B2 | Starta appen **från applikationsmenyn**, inte från terminal; genomför uppstartsdialogen (förening, administratörskonto, modelladress) | B1, A2 |
| B3 | Mänsklig tangentbordssmoke enligt runbooken (fysiskt tangentbord — den vägen kan inte automatiseras i den här KWin/WebKit-miljön) | B2 |
| B4 | Ladda upp de fem korpusdokumenten genom produktens egen uppladdningsväg | A4, B2 |
| B5 | Kör pilotens frågeuppsättning (§6.3) första gången; resultatet blir baslinjen | B4 |

**BP4-2 visar:** en okonfigurerad maskin blev en fungerande installation utan
terminalarbete utöver tunneln.

### Slinga 3 — verkliga arbetspass

| # | Arbete | Beroende |
| --- | --- | --- |
| C1 | Upprepade arbetspass enligt sessionschecklistan, journalförda | Slinga 2 |
| C2 | Frågeuppsättningen körs om per pass och jämförs mot baslinjen | B5 |
| C3 | Felinjektion i skarp miljö: stäng tunneln mitt i ett pass (förväntat: vägran med leverantörsfel, inget påhittat svar) | C1 |
| C4 | Felinjektion: döda backendprocessen (förväntat: felfönster med teknisk orsak, data kvar) | C1 |
| C5 | Om Fedora uppgraderar `webkit2gtk4.1`/`gtk3`: notera versionerna och kör om acceptansen innan piloten återupptas | C1 |

**BP4-3 visar:** produkten beter sig som acceptansen lovar även utanför
acceptansens isolerade miljö.

### Slinga 4 — säkerhetskopiering, återställning, paketbyte

| # | Arbete | Beroende |
| --- | --- | --- |
| D1 | Skapa säkerhetskopia från UI:t; kopiera zip-filen till annan media | Slinga 2 |
| D2 | Återställ från kopian; bekräfta att bytet sker vid start och att data stämmer efteråt | D1 |
| D3 | Avinstallera paketet; bekräfta att datakatalogen ligger kvar; installera om från den arkiverade RPM:en; bekräfta att data läses | A1, D1 |
| D4 | Katastrofövning: radera datakatalogen medvetet och återställ ur säkerhetskopia | D1 |

**BP4-4 visar:** data överlever både operatörsmisstag och paketbyte.

Därefter sammanställs BP5-underlaget, och en kall granskning görs innan det
läggs fram.

---

## 6. Utvärderingsplan

Skriven före piloten och **körd oförändrad**. Ändras något i den ska ändringen
och skälet skrivas in i journalen — en utvärdering som formas efter resultatet
bevisar bara att resultatet blev som det blev.

### 6.1 Formell pilotacceptans

Körs vid pilotstart, efter varje ominstallation, och efter varje systemuppgradering
som rör `webkit2gtk4.1` eller `gtk3`:

```bash
make desktop-acceptance-installed \
  RPM=<arkiverad>/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
```

Godkänt = exitkod 0 med alla fyra faser (`ui,lifecycle,security,failure`).
Acceptansen kräver en nåbar modelltjänst och vägrar köra utan. Den kör i eget
`XDG_DATA_HOME` och rör aldrig pilotinstallationens data — den är alltså en
kontroll av *produkten*, inte av pilotens tillstånd.

### 6.2 Artefakt- och gränskontroll

| Kontroll | Kommando | Godkänt |
| --- | --- | --- |
| Installerat träd = paket | `rpm --verify brf-dokument-ai` | exitkod 0 |
| Installationens identitet | `BUNDLE.json.deliveryTree` | `a702a337…` |
| Leverantörsgräns, installerat | `ops/inspect_payload.py --installed` | 45 kontroller, 0 fynd |
| Leverantörsgräns, artefakt | `make desktop-verify-artifact RPM=<arkiverad>` | 40 passed |
| Leveransträdet orört | kommandot i §4.1 | `a702a337…` |

### 6.3 Frågeuppsättning med facit

Femton frågor ur `backend/eval/golden.json`, som täcker alla fem dokumenten.
Ställs genom appens AI-chatt, inte genom API:et.

**Fragment-fakta (10) — ska besvaras med minst ett verifierat citat som löser
till rätt dokument och rätt sida:**

| id | Fråga | Facit |
| --- | --- | --- |
| g09 | Hur många ledamöter ska styrelsen ha? | Stadgar s. 2 |
| g17 | Vad kostade reliningen av avloppsstammarna? | Årsredovisning 2025 s. 1 |
| g19 | Vad blev årets resultat 2025? | Årsredovisning 2025 s. 2 |
| g24 | Vilket företag sköter den ekonomiska förvaltningen? | Årsredovisning 2025 s. 1 |
| g28 | Vilket företag ska utföra fasadmålningen? | Styrelseprotokoll 2026-03-12 s. 1 |
| g31 | Vad kostar installationen av laddstolpar enligt offerten? | Styrelseprotokoll 2026-03-12 s. 2 |
| g35 | Vid vilket snödjup sker utryckning? | Snöröjningsavtal 2026 s. 1 |
| g37 | Vad kostar maskinell snöröjning per timme? | Snöröjningsavtal 2026 s. 2 |
| g44 | Vilket år ska stambytet genomföras? | Underhållsplan 2026-2036 s. 3 |
| g45 | Vad kostar stambytet enligt planen? | Underhållsplan 2026-2036 s. 3 |

**Prosakontroller (2) — får avvisas, får aldrig hitta på:**
g05 (krav för andrahandsuthyrning, Stadgar s. 2), g25 (hur ofta underhållsplanen
uppdateras, Underhållsplan s. 1).

**Obesvarbara kontroller (3) — ska avvisas med `OTILLRÄCKLIGT UNDERLAG` och noll
citat:** u02 (styrelsearvode), u05 (årsstämmans datum 2026), u08
(radonmätningens resultat).

**Regeln** är densamma som den etablerade readinessgaten
(`backend/scripts/model_readiness.py`): varje fragment-faktafråga besvarad med
minst ett verifierat citat, varje obesvarbar kontroll säkert avvisad, prosafrågor
får avvisas. Skillnaden är att den här uppsättningen körs manuellt genom
skrivbordsappen mot den syntetiska korpusen i stället för automatiskt mot den
skyddade realkorpusen.

**Baslinje kontra tröskel.** Det finns ingen tidigare mätning av just den här
uppsättningen genom skrivbordsappen. Första körningen (B5) *sätter* baslinjen och
skrivs in i journalen. Därefter jämförs varje körning mot baslinjen: ett tapp är en
avvikelse som ska förklaras, inte automatiskt ett stopp. **En fabricerad
källhänvisning är alltid ett stopp** (§8) — den regeln gäller från första
körningen.

### 6.4 Mänsklig tangentbordssmoke

Fysisk tangentbordsautomation är blockerad i den här KWin/WebKit-miljön, så vägen
verifieras av en människa och attesteras i journalen. Stegen finns i
[RUNBOOK-PILOT.md](RUNBOOK-PILOT.md#mänsklig-tangentbordssmoke). Evidensklassen är
**operatörsattestering**, inte automatkörning, och ska stå så i BP5-underlaget.

### 6.5 Regressionssvit

Körs endast om något utanför leveranssökvägarna ändras (t.ex. A3):
`pytest backend/tests` (650 passed / 3 skipped med `BRFV2_REQUIRE_ARTIFACT=1`),
`npm test` i `brfv2-mockup` (21), `npm run test:e2e` (11),
`cargo test --locked` (5), lint rent. Talen är BP2-baslinjens och är det som ska
återkomma.

---

## 7. Mätetal

Produkten har ingen telemetri. Varje mätvärde nedan finns bara om operatören för
in det i journalen efter passet.

| # | Mätvärde | Hur det fångas |
| --- | --- | --- |
| M1 | Pass startade från applikationsmenyn utan terminalarbete (utöver tunneln) | journalrad per pass |
| M2 | Terminalingripanden under pass, och vad de gällde | journalrad — **det här är effektmålets mätvärde** |
| M3 | Startmisslyckanden (felfönster) per pass | journal + `logs/backend.log` |
| M4 | Oväntade backend-dödsfall per pass | journal + `logs/backend.log.1` |
| M5 | Fragment-faktafrågor besvarade med korrekt löst citat | frågeuppsättningen §6.3 |
| M6 | Felaktiga avvisningar (fråga med stöd i korpusen som avvisades) | frågeuppsättningen §6.3 |
| M7 | Fabricerade källhänvisningar | frågeuppsättningen §6.3 — måste vara 0 |
| M8 | Genomförda backup/restore-övningar och om data stämde efteråt | slinga 4 |
| M9 | Av-/ominstallationscykler med bevarad data | slinga 4 |
| M10 | Uppmätt tid från okonfigurerad maskin till första grundade svar | mäts en gång i slinga 2, utan måltal |

M10 mäts därför att den är effektmålets mest konkreta uttryck. Den har medvetet
inget måltal — ett måltal skulle vara en gissning, och gissningen skulle sedan
läsas som ett krav.

---

## 8. Stoppkriterier

Inträffar något av dessa stoppas piloten omedelbart, evidens säkras enligt
runbooken, och inget BP5-underlag läggs fram förrän orsaken är förstådd:

1. dokument eller data från en förening syns i en annan;
2. utgående anslutning till någon annan värd än den konfigurerade modelladressen;
3. någon värdbaserad leverantör blir valbar eller påträffas i det installerade
   trädet (`inspect_payload --installed` ger fynd > 0);
4. en fabricerad källhänvisning, eller ett svar utan stöd presenterat som grundat;
5. dataförlust vid säkerhetskopiering, återställning eller av-/ominstallation;
6. `rpm --verify` ger utfall skilt från 0 utan förklaring, eller installationens
   `deliveryTree` ≠ `a702a337…`;
7. tre oförklarade backend-dödsfall i ett och samma pass.

**Pauskriterier** (piloten vilar, inget beslut krävs): `agenntserver` eller GPU-
tjänsten är nere; SSH-tunneln kan inte etableras; en Fedora-uppgradering har bytt
`webkit2gtk4.1` eller `gtk3` och acceptansen är ännu inte omkörd.

---

## 9. Klassificering av kända begränsningar

XS-53 kräver att de kända begränsningarna klassificeras i stället för att
absorberas tyst. `A` = accepterad för den här piloten, `M` = åtgärdas före
pilotstart, `F` = uttrycklig uppföljning efter piloten.

| # | Begränsning | Klass | Motivering och hantering |
| --- | --- | --- | --- |
| 1 | Osignerad RPM | **A** | En maskin, egen artefakt, ingen distribution. Identiteten kontrolleras i stället mot SHA-256 `6ba028fb…` före varje installation. **F:** signering krävs innan paketet lämnar maskinen. |
| 2 | Ingen bevisad uppgraderingsmigrering | **A + M** | Piloten kör en enda version, så ingen uppgradering sker. **M:** versionsbytespolicyn (säkerhetskopia → avinstallera → installera → verifiera) skrivs in i runbooken före start. **F:** `dnf upgrade` mellan två versioner måste testas innan en andra version finns. |
| 3 | Fysisk Wayland-tangentbordsinjektion ej automatiserad | **M** | **M:** mänsklig tangentbordssmoke (§6.4) ingår i pilotstarten och attesteras. **F:** en automatiserbar väg krävs innan produkten kan släppas till någon som inte kan attestera själv. |
| 4 | Omstart spawnar nytt pid i samma processgrupp | **A + M** | Ofarligt men vilseledande. **M:** runbooken säger: stäng fönstret, verifiera med `pgrep -f brfv2-desktop`, signalera processgruppen — aldrig ett enskilt pid. |
| 5 | Stort paket (548 MiB komprimerat, 773 MiB installerat) | **A** | 356 GB fritt på pilotmaskinen. **F:** kvantisering av embeddervikterna halverar paketet men ändrar retrievalvektorerna och kräver egen utvärdering mot golden set. |
| 6 | Lokal tillitsgräns = OS-användaren | **A** | En människa, en maskin, syntetisk korpus. Gränsen är verklig men ingen annan part är exponerad. **F:** hotmodell för delad maskin krävs innan riktig korpus eller andra användare släpps in. |
| 7 | Inget godkännande för bred distribution eller andra OS | **A** | Redan en uttrycklig exkludering (§2). Piloten varken testar eller påstår något om det. |
| 8 | `Settings.aiModel` har kvar strängen `claude-opus-4-8` som per-förening-preferens | **A** | Den används aldrig för generering i skrivbordsläget, visas aldrig, och är deklarerad i inspektionen. Ligger i `backend/app` — att ändra den skulle **flytta artefaktens bytes** och upphäva BP2-underlaget. **F:** åtgärdas i ett medvetet steg tillsammans med nästa artefaktändring. |
| 9 | Acceptansens skärmbildsnamn är hårdkodade `xs49-*` | **M** | En körning med förvald evidenskatalog skriver över committad XS-49-evidens. Ligger i `backend/scripts` — utanför leveranssökvägarna, alltså åtgärdbar utan att röra artefakten. Arbetspunkt A3. |
| 10 | Rotens `npm run build` raderar `dist/` | **M** | Skulle radera den arkiverade RPM:en. **M:** artefakten arkiveras utanför `dist/` (A1). |
| 11 | Ingen telemetri i produkten | **A + M** | **M:** journalen (A5) är hela mätinsamlingen; utan den finns inga mätvärden alls. |
| 12 | Säkerhetskopior hamnar lokalt bredvid datakatalogen | **A + M** | **M:** varje pass som skapat ny data avslutas med att kopian flyttas till annan media (runbooken). |

---

## 10. Riskregister

| # | Risk | Konsekvens | Hantering | Status |
| --- | --- | --- | --- | --- |
| R1 | Fedora-uppgradering byter `webkit2gtk4.1`/`gtk3` (RPM:en kräver dem oversionerat) | Appen startar inte eller renderar fel mitt i piloten | Registrera versionerna vid start; efter systemuppgradering: kör om acceptansen innan piloten återupptas (C5). Överväg `dnf versionlock` om det inträffar | Öppen |
| R2 | SSH-tunneln nere eller `agenntserver` otillgänglig | Inga genererade svar | Verifierat beteende: vägran med leverantörsfel, inget påhittat svar. Pauskriterium, inte stopp | Öppen |
| R3 | GPU-/NVML-fel på modellvärden | Som R2 | Felsökningskedjan i [DEPLOY-SELFHOSTED-LLM.md](../DEPLOY-SELFHOSTED-LLM.md) | Öppen |
| R4 | Den arkiverade RPM:en raderas | Ominstallation omöjlig utan ombygge | Arkivera utanför `dist/`; ombygge ger bevisat samma bytes — försäkringen är reproducerbarheten | Öppen |
| R5 | Fel artefakt installeras av misstag | Piloten mäter något annat än det granskade | SHA-256-kontroll före varje installation; `deliveryTree`-kontroll efter | Öppen |
| R6 | En leveranssökväg ändras under piloten | Artefakten är inte längre den BP2 granskade | Kontrollkommandot i §4.1 körs före och efter varje arbetspass som rört repot; resultatet i journalen | Öppen |
| R7 | Hårdvarufel raderar datakatalogen och den lokala backupen samtidigt | Total dataförlust (syntetisk korpus — låg konsekvens i denna pilot) | Kopian flyttas till annan media efter varje pass med ny data | Öppen |
| R8 | Journalen förs inte | Piloten producerar inga mätvärden och kan inte utvärderas | Journalraden är sista steget i sessionschecklistan | Öppen |
| R9 | Operatören tror appen är stoppad efter en omstart (nytt pid) | Två instanser, förvirrande felsökning | `pgrep -f brfv2-desktop` i checklistan efter varje avslut | Öppen |
| R10 | Acceptanskörning skriver över committad evidens | Historisk evidens förstörs tyst | A3 före första acceptanskörningen; till dess alltid `--evidence-dir` | Öppen |
| R11 | Piloten glider mot riktig korpus "bara för att prova" | Personuppgifter i en pilot vars ägarfrågor är TBD | Uttrycklig exkludering (§2); att släppa in riktig korpus kräver eget gate-beslut och att ägarbesluten i drift- och förvaltningsplanen §8 stängs först | Öppen |
| R12 | Slutsatser från en enmaskinspilot läses som distributionsklarhet | BP5 påstår mer än evidensen bär | §2 "Vad piloten inte kan avgöra" citeras ordagrant i BP5-underlaget | Öppen |

---

## 11. Säkerhets- och driftchecklista

**Före pilotstart, en gång**

- [ ] Artefaktens SHA-256 = `6ba028fb…` kontrollerad mot den arkiverade filen
- [ ] `rpm --verify brf-dokument-ai` → 0
- [ ] `BUNDLE.json.deliveryTree` = `a702a337…`
- [ ] `ops/inspect_payload.py --installed` → 45 kontroller, 0 fynd
- [ ] Leveransträdets summa (§4.1) = `a702a337…`
- [ ] Formell pilotacceptans grön (§6.1)
- [ ] Mänsklig tangentbordssmoke attesterad (§6.4)
- [ ] `webkit2gtk4.1`- och `gtk3`-versionerna noterade i journalen
- [ ] Datakatalogens rättigheter `0700`
- [ ] Modelladressen i appen är `http://127.0.0.1:8000/v1` och inget annat
- [ ] Arkiverad RPM ligger utanför `dist/`, på känd plats, med sin provenance-fil

**Före varje pass:** SSH-tunneln uppe och annonserar Gemma 4 12B; probe från
appen svarar; leveransträdets summa oförändrad.

**Efter varje pass:** journalrad skriven; ny data → säkerhetskopia skapad och
flyttad till annan media; `pgrep -f brfv2-desktop` tomt; tunneln stängd.

---

## 12. Ägarskap, support och incidenthantering

Drift- och förvaltningsplanens ägartabell
([DRIFT-FORVALTNINGSPLAN.md §8](../DRIFT-FORVALTNINGSPLAN.md)) har flera `TBD`.
Piloten stänger två av dem **för sin egen omfattning**, och låter resten stå kvar
öppna — de blir skarpa först när riktig korpus eller en andra människa kommer in.

| Ansvar | Under piloten |
| --- | --- |
| Produktkod och artefakt | Simon Fredling Jack |
| Modellruntime (`agenntserver`) | Kvarstår `TBD` i det generella fallet; för piloten är otillgänglighet ett pauskriterium, inte en incident |
| Backup och återställningsövning | **Simon Fredling Jack** — stängd för pilotens omfattning |
| Incidenthantering | **Simon Fredling Jack** — stängd för pilotens omfattning |
| Korpus- och dataförvaltning, GDPR-kontakt | Kvarstår `TBD`. Behöver inte stängas: korpusen är syntetisk. **Måste** stängas innan riktig korpus släpps in |
| Godkännande av produktionsändringar | Kvarstår `TBD`; piloten gör inga |

**Supportväg:** operatören själv, med felsökningstabellen i
[RUNBOOK-PILOT.md](RUNBOOK-PILOT.md#felsökning) och
[DEPLOY-SELFHOSTED-LLM.md](../DEPLOY-SELFHOSTED-LLM.md) för modellvärden. Ingen jour,
ingen svarstid, ingen andra linje. Det är hållbart just därför att ingen annan
människa är beroende av installationen — och det upphör att vara hållbart i samma
ögonblick som någon är det.

**Incidentklasser:**

| Klass | Vad | Åtgärd |
| --- | --- | --- |
| S1 | Ett stoppkriterium (§8) | Stoppa appen. Säkra `logs/`, en kopia av datakatalogen, skärmbild av felfönstret, `rpm --verify`, `inspect_payload --installed`. Skriv incidentanteckning i `docs/evidence/pilot/incident-<datum>/`. Lägg upp en Linear-issue som namnger att den blockerar BP5. Ingen fortsatt pilotdrift före diagnos |
| S2 | Degraderad drift (tunnel, GPU, modellvärd) | Pausa passet, följ felsökningskedjan, journalför |
| S3 | Kosmetiskt eller irriterande | Journalrad; blir underlag till erfarenhetsåterföringen |

Att loggarna kan sparas och delas är en följd av att korpusen är syntetisk. Med
riktig korpus vore samma insamling en personuppgiftsfråga.

---

## 13. Förutsättningar som måste vara sanna innan genomförandet börjar

1. BP3 är beslutat av människan. Planeraren beslutar inte.
2. `make setup` har körts i den här arbetskopian (`backend/.venv` saknas i dag).
3. Artefakten är återskapad och arkiverad utanför `dist/` (A1).
4. SSH-åtkomst till `agenntserver` fungerar och tjänsten annonserar Gemma 4 12B.

Punkterna 2–4 är arbete i slinga 1, inte förutsättningar för BP3-beslutet.
