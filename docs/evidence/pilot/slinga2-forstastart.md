# Slinga 2 — evidens för första installationen och första start

Plan: [PILOTPLAN.md](../../pilot/PILOTPLAN.md) · Instruktion:
[RUNBOOK-PILOT.md](../../pilot/RUNBOOK-PILOT.md) · Journal:
[JOURNAL.md](../../pilot/JOURNAL.md)

Arbetskopia: commit `7cd1f9211e4c7b670cd8185302fb01a9d3c65057`, ren
(`git status --porcelain` tomt vid kontrolltillfället).

**Evidensklasser.** *Verifierat* = kommandot kördes på pilotmaskinen och utfallet
nedan är det observerade. *Operatörsattestering* = en människa utförde momentet
vid fysiskt tangentbord och intygar utfallet; det är inte automatkörd evidens och
ska läsas som ett vittnesmål. Inget i den här filen får skrivas innan momentet
faktiskt är utfört.

---

## B0 — kontroller före första start

Alla kontroller kördes 2026-07-29 mellan 19:31 och 19:34 (Europe/Stockholm), före
varje start av applikationen och innan datakatalogen fanns.

| # | Kontroll | Kommando | Observerat utfall | Krav | Utfall |
| --- | --- | --- | --- | --- | --- |
| 1 | Arbetskopians commit | `git rev-parse HEAD` | `7cd1f9211e4c7b670cd8185302fb01a9d3c65057` | exakt `7cd1f92` | ✅ |
| 2 | Arbetskopian ren | `git status --porcelain` | tom utdata | tom | ✅ |
| 3 | Leveransträdet orört (§4.1) | `git ls-tree -r HEAD -- <REPRO_DELIVERY_PATHS> \| sha256sum` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |
| 4 | Paketet installerat | `rpm -q brf-dokument-ai` | `brf-dokument-ai-0.2.0-1.fc44.x86_64` | installerat | ✅ |
| 5 | Installerat träd = paketet | `rpm --verify brf-dokument-ai` | exitkod `0`, inga skillnader | `0` | ✅ |
| 6 | Installationens identitet | `BUNDLE.json.deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |
| 7 | Skalets identitet | `sha256sum /usr/bin/brfv2-desktop` | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` | `d3cb3c02…` | ✅ |
| 8 | Leverantörsgränsen i installerat träd | `ops/inspect_payload.py --installed --scope installed` | `4675 filer`, `kontroller: 45  frånvarande: 21  godkända: 24  utanför omfång: 0  fynd: 0` | 45 kontroller, 0 fynd | ✅ |
| 9 | Arkivets identitet | `sha256sum -c SHA256SUMS` i `~/pilot-artefakter/` | RPM `OK` (`6ba028fb…`), provenance `OK` (`bbf6ee99…`) | båda `OK` | ✅ |
| 10 | Korpusens identitet | `sha256sum -c korpus.sha256` i `~/pilot-korpus/` | alla fem PDF:er `OK` | fem `OK` | ✅ |
| 11 | **Ingen användardata ännu** | `ls ~/.local/share/se.brfdokumentai.desktop/` | `No such file or directory` (exit 2) | katalogen saknas | ✅ |
| 12 | Ingen instans körande | `pgrep -f brfv2-desktop` | endast den egna kontrollprocessens kommandorad matchade; ingen `brfv2-desktop`-process | ingen instans | ✅ |
| 13 | Diskutrymme | `df -h /home` | 353 GB fritt (475 G totalt, 26 % använt) | gott om utrymme | ✅ |
| 14 | Körmiljöns versioner (risk R1) | `rpm -q webkit2gtk4.1 gtk3` | `webkit2gtk4.1-2.52.5-1.fc44.x86_64`, `gtk3-3.24.52-2.fc44.x86_64` | noterade | ✅ |
| 15 | Skrivbordssession | `XDG_SESSION_TYPE` / `XDG_CURRENT_DESKTOP` | `wayland` / `KDE`, kernel `7.1.5-200.fc44.x86_64` | den verifierade sessionen | ✅ |

**Punkt 11 är slingans viktigaste kontroll.** Den är det som gör den här starten
till en genuin förstagångsstart och inte en simulering, och den kan bara
observeras en enda gång. Kontrollerna 14 och 15 är oförändrade sedan slinga 1.

**Punkt 12, precisering:** `pgrep -f brfv2-desktop` returnerade exitkod 0, men den
enda träffen var kontrollkommandots egen `bash -c`-rad, som innehåller söksträngen.
Ingen process med binären `brfv2-desktop` körde. Detta är en känd artefakt av att
söka på hela kommandoraden och är inte en avvikelse.

### Applikationsmenyns post

`/usr/share/applications/BRF Dokument-AI.desktop` finns och är den väg operatören
ska använda:

```
Name=BRF Dokument-AI
Exec=brfv2-desktop
Terminal=false
StartupWMClass=brfv2-desktop
Categories=Office;Viewer;
```

`Terminal=false` är det som gör att M1 ("startat från applikationsmenyn utan
terminalarbete") kan bli sant.

---

## B1 — SSH-tunnel och modelltjänst

*Verifierat 2026-07-29 19:33–19:34.*

| Steg | Kommando | Observerat |
| --- | --- | --- |
| Port ledig före | `ss -ltn \| grep :8000` | inget lyssnade på 8000 |
| SSH nåbar | `ssh agenntserver 'hostname; uptime'` | `agenntserver`, uppe 14 dagar, load 0.00 |
| Tjänsten uppe på värden | `ssh agenntserver 'curl -s http://127.0.0.1:8000/v1/models'` | annonserar Gemma 4 12B |
| Tunneln öppnad | `ssh -N -o ExitOnForwardFailure=yes -L 8000:127.0.0.1:8000 agenntserver` | lyssnade på `127.0.0.1:8000` och `[::1]:8000` inom ~1 s |
| Lokal probe | `curl -s http://127.0.0.1:8000/v1/models` | samma modell annonserad genom tunneln |

Annonserad modell, ordagrant ur svaret:

```
unsloth/gemma-4-12b-it-GGUF
  snapshot d997c805aafe035a8024f961c6e1afd6b30d79a5
  gemma-4-12b-it-UD-Q4_K_XL.gguf
  capabilities: ["completion","multimodal"]
```

Det är Gemma 4 12B (instruction-tuned, Q4_K_XL-kvantiserad GGUF) — den
modelltjänst pilotplanen §2 anger. `ExitOnForwardFailure=yes` gör att tunneln
antingen är uppe eller uppenbart nere; den kan inte stå halvöppen och ge sken av
nåbarhet.

**Detta är enda tillåtna terminalarbetet under passet** (pilotplanen §7, M1/M2).

---

## B1b — formell pilotacceptans (§6.1)

*Verifierat 2026-07-29 **19:38:43–19:40:53**, **före** första start, efter
operatörens beslut. Fönstret är avläst ur evidensfilernas mtime — första
skärmbilden 19:38:52, `acceptance.json` skriven 19:40:53 — jämte
`durationSeconds: 129.9`. (En tidigare version av den här filen angav 19:49–19:52;
det var tidpunkten då agenten läste resultatet, inte då körningen skedde, och är
rättat.)*

```bash
make desktop-acceptance-installed \
  RPM=~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  RUN_LABEL=xs55-slinga2
```

| Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- |
| Exitkod | `0` | 0 | ✅ |
| Faser | `uiJourney`, `lifecycle`, `securityBoundary`, `failureSurfaces` | alla fyra | ✅ |
| Körtid | 129,9 s | — | — |
| Schema | `brfv2-desktop-acceptance/v2` | — | — |
| Modelltjänst | `baseUrl` `http://127.0.0.1:8000/v1`, `served` = Gemma 4 12B GGUF | pilotens adress | ✅ |
| `bundle.deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |
| Isolering | `isolatedXdgHome` = `<isolated-xdg-home>`, mönster `/tmp/brfv2-acceptance-*` | eget XDG-hem | ✅ |

**Att den inte förbrukade förstagångsstarten är kontrollerat, inte antaget.**
Källan visar `tempfile.mkdtemp(prefix="brfv2-acceptance-")` som rot och ett eget
`XDG_DATA_HOME` (`backend/scripts/desktop_acceptance.py:378,1861`), och efter
körningen gällde fortfarande:

* `ls ~/.local/share/se.brfdokumentai.desktop` → `No such file or directory`
* `ls -d /tmp/brfv2-acceptance-*` → borta (uppstädat)
* leveransträdets summa oförändrad `a702a337…`

**A3 bekräftad i skarp körning.** Evidensen namngavs av `--run-label`:
`xs55-slinga2-installed-desktop-{acceptance.json,setup.png,documents.png,settings.png,refusal.png,answer-highlight.png}`.
Ingen `xs49-*`-fil rördes. Det är första gången skyddet prövas utanför sin egen
regressionssvit.

Acceptansen bevisar produkten, inte pilotens tillstånd: den körde mot samma
installerade skal men i ett eget datahem, och säger därför ingenting om den
förstagångsstart som följer nedan.

### Hemlighetsgranskning av den nya evidensen

Acceptansen skriver sex nya filer under `docs/evidence/`. Eftersom de är avsedda
att committas granskades de innan de läggs till, inte efteråt:

| Kontroll | Utfall |
| --- | --- |
| Acceptansens testlösenord (`OWNER_PASSWORD`, `desktop_acceptance.py:66`) i evidens-JSON | **0 förekomster** — läcker inte |
| Acceptansens testadress `styrelsen@acceptans.example` | 1 förekomst; syntetisk `.example`-domän, ingen personuppgift |
| `ANTHROPIC_API_KEY: "sk-ant-must-never-be-used"` | Avsiktligt attrappvärde. Säkerhetsfasen sätter det för att bevisa att skalet *tar bort* variabeln ur backendprocessens miljö (`src-tauri/src/main.rs`). Ingen verklig nyckel |
| Riktiga nycklar/tokens (`token`, `bearer`, `authorization`, `api_key`) | inga träffar med verkligt värde |

Ingen verklig hemlighet och ingen personuppgift finns i evidensen. Det som *ser
ut* som en nyckel är en attrapp vars hela syfte är att vara frånvarande i
barnprocessen — den ska stå kvar i evidensen, eftersom det är den som visar att
borttagningen sker.

Korpusens PDF:er (`~/pilot-korpus/`) och den arkiverade RPM:en
(`~/pilot-artefakter/`) ligger **utanför arbetskopian** och kan därför inte nå
Git via ett misstag i den här slingan. `backend/.venv/` och
`brfv2-mockup/node_modules/` täcks av `.gitignore` (rad 25 respektive
`brfv2-mockup/.gitignore` rad 10).

---

## B2 — första start och uppstartsdialog

### Starten som händelse

Startad från Fedoras applikationsmeny, inte från terminal. Tidpunkten är avläst
**objektivt ur filsystemet**, inte noterad för hand: en vakt väntade på att
datakatalogen skulle uppstå.

| | Värde | Källa |
| --- | --- | --- |
| `T0_förberedd` | 2026-07-29 21:07:22 +02:00 | stämplad före första knapptryck |
| `T0_operatör` | 2026-07-29 **21:14:52.838** +02:00 | `stat --format=%w` på datakatalogen (birth) |
| Sträcka | 7 min 30 s | operatören hittade posten i menyn och startade |
| Process | `380658 /usr/bin/brfv2-desktop` | `pgrep -ax` |

Att sträckan mättes till 7,5 minuter är i sig ett M2-relevant utfall: posten låg i
menyn hela tiden, men den var inte omedelbart hittad. Se journalens
avvikelseavsnitt — en del av tiden är operatörens läsning av agentens
felsökningsmeddelanden och ska inte läsas som ren produktfriktion.

### Datakatalogen som den faktiskt skapades

`~/.local/share/se.brfdokumentai.desktop`, **mode `700`** — uppfyller
pilotplanen §4.3 och §11-checklistans krav.

| Post | Rättigheter | I datakontraktet §4.3? |
| --- | --- | --- |
| `data/` | `drwx------` | ✅ dokumenterad |
| `backups/` | `drwx------` | ✅ dokumenterad |
| `restore-staging/` | `drwx------` | ✅ dokumenterad |
| `logs/` | `drwx------` | ✅ dokumenterad |
| `CacheStorage/` | `drwxr-xr-x` | ❌ **odokumenterad** |
| `WebKitCache/` | `drwxr-xr-x` | ❌ **odokumenterad** |
| `storage/` | `drwxr-xr-x` | ❌ **odokumenterad** |
| `mediakeys/` | `drwxr-xr-x` | ❌ **odokumenterad** |
| `hsts-storage.sqlite` | `-rw-r--r--` | ❌ **odokumenterad** |

De fyra kataloger kontraktet beskriver skapades alla, med rätt rättigheter och
med `backups/` **utanför** `data/` precis som återställningsvägen förutsätter.

**Fynd (S3, dokumentation):** WebKit lägger fem egna poster i samma katalog, och
de står inte i §4.3. De är läsbara för andra (`0755`/`0644`), men
**föräldrakatalogens `0700` är det som bär gränsen** — ingen av dem är åtkomlig
för en annan OS-användare. Ingen säkerhetskonsekvens i den lokala tillitsgränsen,
men kontraktet i §4.3 är ofullständigt och beskriver katalogen som om den bara
innehöll produktens egna fyra. Det bör rättas innan §4.3 citeras som uttömmande.

`data/` innehöll vid start `auth.db`, `.desktop-cookie-id` och en tom `tenants/`.

### Första loggraderna — förväntat fel, olämplig nivå

`logs/backend.log` (328 byte) vid första start:

```
ERROR brf.llm: Självhostad LLM kunde inte initieras: BRF_LLM_BASE_URL saknas — ange den självhostade LLM-serverns adress.
ERROR brf.llm: Självhostad LLM kunde inte initieras: BRF_LLM_BASE_URL saknas — ange den självhostade LLM-serverns adress.
INFO  brf.embeddings: Embedding provider: model2vec:potion-multilingual-128M
```

**Detta är inte ett fel i produkten.** Modelladressen sätts i uppstartsdialogen,
som per definition inte är ifylld när backend startar första gången. Att den
självhostade klienten inte kan initieras är korrekt beteende.

**Fynd (S3, kosmetiskt):** tillståndet loggas på `ERROR`-nivå, två gånger, vid en
helt förväntad förstagångssituation. En operatör som öppnar loggen efter sin
första start möts av två röda rader som inte betyder något fel. `M3`
(startmisslyckanden) är fortfarande **0** — inget felfönster visades och
fönstret öppnades normalt. Raderna får inte räknas som M3.

Embeddern laddades ur paketet (`model2vec:potion-multilingual-128M`), vilket
bekräftar att vikterna är buntade och att första start inte kräver nätverk för
annat än modelltjänsten.

### Provisionering genomförd — verifierad i logg, inte bara attesterad

`logs/backend.log` efter uppstartsdialogen:

```
INFO brf.desktop: Installation konfigurerad: förening fredling
INFO brf.desktop: Modelltjänsten ändrad av installationsadministratör fc69c8f41250
                  till http://127.0.0.1:8000/v1 (loopback).
INFO httpx: HTTP Request: GET http://127.0.0.1:8000/v1/models "HTTP/1.1 200 OK"
```

| Kontroll | Observerat | Betydelse |
| --- | --- | --- |
| Förening skapad | tenant `fredling` under `data/tenants/` | B2 klar |
| Installationsadministratör | `fc69c8f41250` satte adressen | §4.2: endast den rollen får peka om modelltjänsten — och det var den som gjorde det |
| Modelladress | `http://127.0.0.1:8000/v1`, klassad **`(loopback)`** av policyn | §4.2:s driftklass loopback, exakt pilotens adress |
| **Verklig nåbarhet** | `GET /v1/models` → **`200 OK`** | §4.4: detta är beviset, inte `ready`. Probe-anropet gick igenom tunneln till Gemma 4 12B |
| M4 backend-dödsfall | ingen `backend.log.1` | **0** |
| Process | samma pid `380658` genomgående | ingen omstart |

Att `200 OK` står i loggen är den kontroll pilotplanen §4.4 kräver: `ready` är
konfigurationsstatus, faktisk nåbarhet bevisas av probe-anropet. Här finns båda.

**Notering om föreningsnamnet:** operatören valde ett annat namn än det
föreslagna `Brf Gjutformen 12`; tenantslugen blev `fredling`. Det påverkar inget i
utvärderingen — ingen av de femton frågorna refererar föreningens namn, och
korpusen laddas in i den förening som råkar vara aktiv. Det noteras bara så att
BP5-läsaren inte förväxlar tenantnamnet med korpusens fiktiva förening.

### Avvisning före uppladdning — operatörsattesterat negativt kontrollutfall

*Evidensklass: operatörsattestering, delvis styrkt av logg.*

Operatören ställde en fråga **innan** något dokument fanns och fick en korrekt
avvisning. Det var inte ett planerat steg i §6.3, men det är ett värdefullt
negativt kontrollutfall: med noll dokument i indexet finns ingen möjlig grund, och
produkten hittade inte på ett svar. Det är samma egenskap som stoppkriterium 4
skyddar, prövad i det mest extrema fallet.

Utfallet räknas **inte** in i M5/M6/M7 — det tillhör inte den definierade
uppsättningen och får inte förbättra baslinjen. Det redovisas som en observation.

## B3 — mänsklig tangentbordssmoke

**7 av 8 godkända. Steg 2 underkänt.** Fullständig tabell, attestering och
kodverifiering av felet finns i
[JOURNAL.md](../../pilot/JOURNAL.md#tangentbordssmoke--operatörsattestering-b3).

Evidensklass: **operatörsattestering med verktygsstöd** — inte renodlad fysisk
attestering, eftersom en input-daemon användes för delar av sekvensen.

Det underkända steget (Shift+Enter skickar i stället för att radbryta) är
**verifierat i källkoden** och därmed oberoende av verktygets tillförlitlighet:
chattrutan är `<input type="text">` och `onKeyDown` saknar `shiftKey`-kontroll
(`brfv2-mockup/src/App.jsx:1522–1526`, `1107–1111`).

## B4 — uppladdning av korpus genom produktens egen väg

Uppladdad genom Dokument-vyn, aldrig genom seedning.

| Kontroll | Utfall |
| --- | --- |
| Poster i indexet | **5** |
| Chunks | **13** |
| Dubbletter | inga *(efter åtgärd — se avvikelsen nedan)* |
| Föräldralösa filer i `docs/` / `extract/` | inga |
| Bit-identitet mot `~/pilot-korpus/` | **alla fem** |
| Extraktion icke-tom | alla fem, 597–1149 tecken per sida |

Sidantal och extraherad text stämmer med korpusens original, och varje sida som
facit citerar finns.

**Avvikelse (S2, åtgärdad):** korpusen laddades upp två gånger — 10 poster /
26 chunks — därför att en andra instans startades mitt i passet. Dubbletterna
raderades genom produktens egen väg innan baslinjen kördes. Hade de fått ligga
kvar vore baslinjen mätt mot en korpus som inte går att återskapa.

## B5 — frågeuppsättningen, baslinjekörning

**Baslinjen är satt.** Fullständig tabell med svar, citat, sida och oberoende
verifiering finns i
[JOURNAL.md](../../pilot/JOURNAL.md#frågeuppsättningen--baslinjekörning-b5).

| Kategori | Utfall |
| --- | --- |
| Fragment-fakta med korrekt löst citat | **10 / 10** |
| Prosakontroller | **2 / 2** besvarade med stött citat |
| Obesvarbara avvisade med noll citat | **2 / 3** |
| **Fabricerade källhänvisningar** | **0** |

**Citaten är verifierade av agenten, inte bedömda av operatören.** Sidtexten
rekonstruerades ur `extract/<id>.json` (ord med koordinater) och varje citerad
uppgift söktes i den citerade sidan. Alla 13 citat hade stöd. Dessutom
kontrollerades att `arvode` och `radon` **inte** förekommer någonstans i korpusen,
vilket gör avvisningarna av u02 och u08 objektivt korrekta.

u05 avvek: kvalificerat icke-svar med **stött** citat i stället för noll citat.
Inte fabricering, men en avvikelse mot villkoret — se journalen.

---

## Kontroller efter passet

*Verifierat 2026-07-30, efter baslinjekörningen.*

| Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- |
| Leveransträdet (§4.1) | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | oförändrat | ✅ |
| `rpm --verify brf-dokument-ai` | exitkod `0` | 0 | ✅ |
| Installationens `deliveryTree` | `a702a337…` | `a702a337…` | ✅ |
| `inspect_payload --installed` | 45 kontroller, **0 fynd** | 45 / 0 | ✅ |
| Datakatalogens rättigheter | `mode=700` | `0700` | ✅ |
| Ändringar i `REPRO_DELIVERY_PATHS` | **inga** | inga | ✅ |
| PDF / RPM / hemligheter mot Git | **inga** — korpus och arkiv ligger utanför arbetskopian | inga | ✅ |

### Stoppkriterierna (§8), prövade var för sig

| # | Kriterium | Utfall |
| --- | --- | --- |
| 1 | Data från en förening syns i en annan | **Ej utlöst.** Endast en förening (`fredling`) finns. Kriteriet kan inte prövas meningsfullt med en tenant — det ska inte läsas som att isoleringen är bevisad |
| 2 | Utgående anslutning till annan värd än modelladressen | **Ej utlöst.** Med korrekt pid-attribuering har backend (`389868`) exakt **en** TCP-anslutning: `127.0.0.1:54896 → 127.0.0.1:8000`, dvs. den konfigurerade adressen. WebKit-processerna och skalet har inga. Backend lyssnar endast på `127.0.0.1:47671` |
| 3 | Värdbaserad leverantör valbar eller i installerat träd | **Ej utlöst.** `inspect_payload --installed`: 0 fynd |
| 4 | Fabricerad källhänvisning | **Ej utlöst.** Alla 13 citat verifierade mot sidtexten |
| 5 | Dataförlust vid backup/restore/ominstallation | **Ej tillämpligt** — hör till slinga 4 |
| 6 | `rpm --verify` ≠ 0 eller `deliveryTree` ≠ `a702a337…` | **Ej utlöst.** Båda gröna |
| 7 | Tre oförklarade backend-dödsfall i samma pass | **Ej utlöst.** Noll dödsfall; pidbytet var en andra menystart med ren avslutning av instans 1 |

**Inget stoppkriterium inträffade.**

### Kvarstående i sessionschecklistan

Passet är **inte formellt avslutat**. Runbookens efterpasskontroller som återstår
och som kräver operatören:

* säkerhetskopia skapad och **flyttad till annan media** — passet har skapat ny
  data (fem dokument, ett konto, en förening), så detta är obligatoriskt
* fönstret stängt och `pgrep -f brfv2-desktop` tomt
* SSH-tunneln stängd

Appen kördes fortfarande (pid `389858`) och tunneln var uppe när dessa kontroller
skrevs. Det är avsiktligt: runbooken säger att appen inte stängs utanför dess egna
instruktioner, och avslutet är operatörens beslut.
