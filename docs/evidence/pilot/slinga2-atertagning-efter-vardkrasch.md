# Slinga 2 — värddatorkrasch och kontrollerad återtagning

Plan: [PILOTPLAN.md](../../pilot/PILOTPLAN.md) · Instruktion:
[RUNBOOK-PILOT.md](../../pilot/RUNBOOK-PILOT.md) · Journal:
[JOURNAL.md](../../pilot/JOURNAL.md) · Passets evidens:
[slinga2-forstastart.md](slinga2-forstastart.md)

Pilotmaskinen gick ned **2026-07-30 07:19** — efter att baslinjekörningen (B5) var
klar, men **innan** passets efterpasskontroller var utförda. Passet var alltså
öppet när värden försvann.

Den här filen fastställer två saker och inget mer:

1. **vad som objektivt går att säga om nedgången** — och lika viktigt vad som
   *inte* går att säga; och
2. **att pilotens tillstånd är oskadat**, kontrollerat post för post innan något
   startades om.

**Evidensklasser.** *Verifierat* = kommandot kördes på pilotmaskinen och utfallet
nedan är det observerade. *Härlett* = slutsats dragen ur verifierade observationer,
med härledningen utskriven. Ingenting här är attesterat av operatören — det är
maskinläst evidens.

---

## 1. Nedgången som händelse

*Verifierat 2026-07-30 08:47–08:55 ur `journalctl`, `coredumpctl` och filsystemet.*

| Observation | Källa | Utfall |
| --- | --- | --- |
| Sista journalraden i passets boot (`-3`) | `journalctl -b -3 -n 1` | `2026-07-30T07:19:21+02:00 kwin_wayland[2256]: Libinput: … event processing lagging behind by 44ms` |
| Avstängningssekvens i boot `-3` | `grep systemd-shutdown\|Reached target Power-Off\|Sending SIGTERM to remaining` | **ingen** — journalen slutar tvärt |
| Kernel-panic, oops, `BUG:`, Machine Check | `journalctl -b -3 -k \| grep -iE 'oops\|panic\|BUG:\|mce\|hardware error'` | **inga** |
| OOM-dödande | `journalctl -b -3 \| grep -iE 'oom\|killed process\|SIGKILL'` | **inga** träffar på någon process |
| Coredump | `coredumpctl list` | **ingen** för produkten *(de två som finns är Playwright-Chromium från 2026-07-29 07:53, en annan aktivitet)* |
| Fel loggat av appens systemd-enhet | `journalctl -b -3 --user \| grep -E 'BRF\|brfv2' \| grep -iE 'Failed\|Main process exited'` | **inget** |

**Det som följde.** Efter nedgången startade maskinen tre gånger. De två första
starterna var korta och avslutades **rent** — `systemd-shutdown` körde,
`Syncing filesystems and block devices`, `Sending SIGTERM to remaining processes`
(07:24:15 respektive 07:26:24). Det var alltså avsiktliga omstarter, inte fler
krascher. Den nuvarande boot:en startade 07:26 (`who -b`) och har varit uppe
oavbrutet sedan dess.

*Notering om klockan:* `journalctl --list-boots` visar för de tre senaste
boot:arna en *första*-tidsstämpel två timmar senare än deras *sista*. Det är
tidsstämplar skrivna innan tidssynkroniseringen hunnit korrigera klockan i tidig
boot, inte en ordningsföljd som går baklänges. Tidpunkterna ovan är därför lästa
ur *sista*-stämplarna och ur `who -b`, som inte har den skevheten. Det redovisas i
stället för att tyst jämkas ihop.

### Vad orsaken var går inte att fastställa — och gissas därför inte

Journalen slutar mitt i normal drift utan ett enda felmeddelande. Det mönstret är
förenligt med flera helt olika orsaker (strömbortfall, hård återställning, en hängning
som inte hann skriva något) och **särskiljer dem inte**. Ingen loggpost pekar ut
någon av dem.

**Ingenting i materialet knyter nedgången till produkten**, och den kopplingen görs
därför inte:

* produktens sista loggrad är **06:13:05** — **1 h 06 min** före värdens sista
  journalrad;
* backend-processen (`389858`) loggade inget fel, fick ingen signal och lämnade
  ingen coredump;
* ingen `backend.log.2` skapades, dvs. backend startade aldrig om av sig själv;
* appens minnestopp under passet (2,1 GB, journalförd som S3) är **inte** ett
  belägg för orsak — den var uppmätt på instans 1, som avslutades rent 21:41:58,
  nio timmar före nedgången, och ingen OOM-händelse finns loggad.

Att produkten kördes när värden gick ned gör den inte till orsak. Att påstå
motsatsen vore en efterhandskonstruktion utan stöd, och pilotens hela värde ligger
i att den inte gör sådana.

### M4 räknas inte upp — och skälet står utskrivet

`M4` mäter **oväntade backend-dödsfall per pass** (pilotplanen §7, avläst i journal
och `logs/backend.log.1`). Backend-processen upphörde tillsammans med värden. Det
är inte samma sak som att backend dog:

| Fråga | Svar | Grund |
| --- | --- | --- |
| Dog backend före värden? | **Nej, inget stöd** | inget enhetsfel, ingen signal, ingen coredump, ingen ny loggrotation |
| Dog backend av egen orsak? | **Inget stöd** | sista raden 06:13:05 är ett normalt `200 OK`, inte ett fel |
| Fortsatte backend efter nedgången? | Nej | hela värden var borta |

**`M4` för slinga 2 / pass 1 står därför kvar på `0`.** En processavslutning som
orsakats av att värddatorn försvinner är inte ett backend-dödsfall i M4:s mening,
och att räkna in den skulle förvanska just det mätvärde som ska fånga produktens
stabilitet.

Att pilotplanen §7 inte skiljer på *dödsfall* och *värdorsakad avslutning* är
däremot en verklig lucka i mätdefinitionen. **Den frågan tillhör BP4** — den kan
inte avgöras av den session som råkade drabbas.

---

## 2. Återtagningskontrollen — är tillståndet oskadat?

*Verifierat 2026-07-30 08:47–08:58, före varje omstart av tunnel eller applikation.*

Kontrollerna gjordes i den ordning som gör dem meningsfulla: läsande först, och
inget skrevs till pilotens datakatalog. `auth.db` lästes uttryckligen skrivskyddat
(`file:…?mode=ro`) så att kontrollen inte kan ändra det den kontrollerar.

### 2.1 Arbetskopia och evidens

| # | Kontroll | Kommando | Observerat | Krav | Utfall |
| --- | --- | --- | --- | --- | --- |
| 1 | XS-55-worktreet finns | `git worktree list` | `~/Projects/brfv2-desktop-xs55` på XS-55-grenen | finns | ✅ |
| 2 | Basen orörd | `git rev-parse HEAD` | `7cd1f9211e4c7b670cd8185302fb01a9d3c65057` | `7cd1f92` | ✅ |
| 3 | De okommittade evidensfilerna kvar | `git status --porcelain` | `M docs/pilot/JOURNAL.md` + 8 nya filer *(2 evidenstexter, 6 acceptansfiler)* | alla kvar | ✅ |
| 4 | Ingen trunkering vid kraschen | `ls -la` på de nio | alla har innehåll; `JOURNAL.md`-diffen är komplett och läsbar | inget tomt/avhugget | ✅ |
| 5 | **Leveransträdet (§4.1)** | `git ls-tree -r HEAD -- <REPRO_DELIVERY_PATHS> \| sha256sum` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |

### 2.2 Installation och artefakter

| # | Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- | --- |
| 6 | `rpm --verify brf-dokument-ai` | exitkod `0`, inga skillnader | `0` | ✅ |
| 7 | Installationens `deliveryTree` | `a702a337…` | `a702a337…` | ✅ |
| 8 | Skalets identitet | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` | `d3cb3c02…` | ✅ |
| 9 | Arkivet `~/pilot-artefakter/` | `sha256sum -c SHA256SUMS` → RPM `OK`, provenance `OK` | båda `OK` | ✅ |
| 10 | Korpusen `~/pilot-korpus/` | `sha256sum -c korpus.sha256` → alla fem `OK` | fem `OK` | ✅ |

Kontroll 6–8 är samma tre som B0 gjorde, körda om **som integritetskontroll efter
en abrupt nedgång** — inte som en omkörning av baslinjen. Baslinjebatteriet
(acceptans, `inspect_payload`) har medvetet **inte** körts om: ingen kontroll visar
skada, och en omkörning utan anledning skulle bara skapa evidens som ser ut att
svara på en fråga ingen ställt.

### 2.3 Datakatalogen

| # | Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- | --- |
| 11 | Katalogen finns | `~/.local/share/se.brfdokumentai.desktop`, `mode=700` | finns, `0700` | ✅ |
| 12 | Kontraktets fyra kataloger | `data/`, `backups/`, `restore-staging/`, `logs/` — alla `drwx------` | §4.3 | ✅ |
| 13 | **`auth.db` integritet** | `PRAGMA integrity_check` → `ok` | `ok` | ✅ |
| 14 | **Främmande nycklar** | `PRAGMA foreign_key_check` → tom utdata | tom | ✅ |
| 15 | Inga journal-/WAL-rester | endast `auth.db` finns i `data/` — ingen `-wal`, ingen `-journal` | inga | ✅ |
| 16 | **Exakt en förening** | `SELECT COUNT(*) FROM tenants` → **1** (`fredling` / `FREDLING`, skapad `2026-07-29T19:24:08Z`) | 1 | ✅ |
| 17 | **Befintligt administratörskonto** | 1 användare, `memberships.role = admin`, **och** en rad i `installation_admins` | finns | ✅ |
| 18 | Kontot är användbart | `password_hash` 64 byte + `salt` 16 byte satta | satta | ✅ |
| 19 | Sessionen överlevde | 1 session, giltig t.o.m. `2026-08-12T19:24:08Z` | — | *(noteras)* |
| 20 | **Modellkonfigurationen** | `desktop-config.json`: `baseUrl` = `http://127.0.0.1:8000/v1`, modell `gemma4:e12b`, etikett `agenntserver`, `apiKey` tom | `http://127.0.0.1:8000/v1` | ✅ |

Kontroll 17 gäller **rollen och kontots existens**. Kontots namn och e-postadress
lästes aldrig ut i klartext — frågan maskerade fälten (`<namn satt>`,
`<e-post satt, 27 tecken>`), eftersom de är operatörens verkliga personuppgifter.
Det är samma omfångsavvikelse som journalen redan har öppen, och den ska inte
förvärras av en kontroll.

### 2.4 Dokument och index

| # | Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- | --- |
| 21 | **Antal dokument** | `documents.json` → **5** poster | exakt 5 | ✅ |
| 22 | **Antal chunks** | 3 + 2 + 3 + 2 + 3 = **13** | exakt 13 | ✅ |
| 23 | Inga dubbletter återuppstod | fem unika id, fem unika namn | 5 | ✅ |
| 24 | Extraktionen läsbar | alla fem `extract/<id>.json` parsar som JSON | alla fem | ✅ |
| 25 | Inga föräldralösa filer | `docs/` 5 PDF, `extract/` 5 JSON, `documents.json` 5 poster | 5/5/5 | ✅ |
| 26 | **Dokumenten bit-identiska med korpusen** | alla fem SHA-256 identiska med `~/pilot-korpus/korpus.sha256` | alla fem | ✅ |

Kontroll 26 är den starkaste: en abrupt nedgång skadar filer genom halvskrivna
block, och en enda ändrad byte skulle synas som en annan summa. Ingen gjorde det.

### 2.5 Filsystemet under

| # | Kontroll | Observerat | Utfall |
| --- | --- | --- | --- |
| 27 | Btrfs-fel i nuvarande boot | inga `BTRFS error/warning/critical`, ingen `csum`-avvikelse | ✅ |
| 28 | Enhetsstatistik | `btrfs device stats /home`: write `0`, read `0`, flush `0`, corruption `0`, generation `0` | ✅ |
| 29 | Diskutrymme | 349 GB fritt (475 G, 27 % använt) | ✅ |

### 2.6 Ingenting kördes vid kontrolltillfället

| # | Kontroll | Observerat | Utfall |
| --- | --- | --- | --- |
| 30 | Ingen appinstans | `pgrep -a -f brfv2-desktop` → endast kontrollkommandots egen rad *(känd artefakt, se B0 punkt 12)* | ✅ |
| 31 | Tunneln nere | inget lyssnar på `127.0.0.1:8000` | *(väntat efter omstart)* |

---

## 3. Sammanfattad slutsats

**Pilottillståndet överlevde nedgången intakt.** Trettio kontroller, ingen
avvikelse: databasen är konsistent, indexet har exakt de fem dokument och
tretton chunks som B4 lämnade, dokumenten är bit-identiska med den arkiverade
korpusen, leveransträdet är `a702a337…`, installationen verifierar mot paketet och
filsystemet visar noll fel.

**Baslinjen körs därför inte om.** Villkoret för en omkörning är att data eller
index *faktiskt* skadats. Det gjorde de inte.

---

## 4. Efterpasset, återupptaget

*Verifierat 2026-07-30 09:30–09:52. Passet återupptogs där det avbröts — det kördes
inte om.*

### 4.1 Tunneln (steg 1)

| Kontroll | Observerat |
| --- | --- |
| Tailscale SSH | krävde **ombekräftelse i webbläsare** efter omstarten; grantet var borta, inte tailnet-anslutningen (`BackendState: Running`, `agenntserver` online) |
| Tjänsten på värden före tunnel | `/v1/models` annonserar `gemma-4-12b-it-UD-Q4_K_XL.gguf`, snapshot `d997c805aafe035a8024f961c6e1afd6b30d79a5` |
| Tunneln öppnad | `ssh -f -N -o ExitOnForwardFailure=yes -L 8000:127.0.0.1:8000 agenntserver` → pid `63208`, lyssnar på `127.0.0.1:8000` och `[::1]:8000` |
| Lokal probe | **samma modell och samma snapshot** som B1 — modelltjänsten är oförändrad sedan baslinjen |

Att snapshot-hashen är identisk med B1:s är poängen: baslinjen mättes mot exakt den
modellvikt som fanns uppe nu, inte mot "Gemma 4 12B" som kategori.

### 4.2 Start och identitet (steg 2–3)

| Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- |
| Startad från applikationsmenyn | `systemd[1227]: Started app-BRF\x20Dokument\x2dAI@4c164aff…service` **09:36:50** | menyvägen | ✅ |
| Readiness-kontraktet | `{"schema":"brfv2-desktop-startup/v1","status":"ready","host":"127.0.0.1","port":39631}` | `ready` | ✅ |
| **Uppstartsdialogen** | **visades inte** | får inte visas | ✅ |
| `logs/backend.log` vid start | endast embedder-raden — **inga** `ERROR BRF_LLM_BASE_URL` | konfigurationen kvar | ✅ |
| `auth.db` orörd av starten | samma SHA-256 och samma mtime (`2026-07-29 21:24:08`) som före | oförändrad | ✅ |

### 4.3 Fynd: inloggningsrutan visades inte heller

**Produkten återställde sessionen och gick rakt in i dokumentvyn.** Orsaken är
avläst, inte antagen: sessionsraden skapades 2026-07-29 21:24 med giltighet till
**2026-08-12**, och cookie-filen överlevde både nedgången och omstarten.

**Klass S3, med säkerhetsdimension.** En pilotmaskin som kraschar och startar om är
fortfarande inloggad i upp till fjorton dagar, utan att någon behöver kunna
lösenordet. Det är inte ett fel mot någon skriven kravbild — men det är ett
observerat beteende som hör hemma i BP5-underlaget, eftersom det gäller en produkt
vars hela poäng är att data stannar på maskinen.

Den omedelbara följden var att **inloggningsvägen inte blev prövad av starten**.
Den prövades i stället separat, efter att säkerhetskopian var säkrad — se 4.5.

### 4.4 Säkerhetskopian (steg 5–6)

Skapad genom produktens eget gränssnitt (Appinställningar → *Skapa säkerhetskopia
nu*), aldrig genom att kopiera katalogen för hand.

| Kontroll | Observerat | Utfall |
| --- | --- | --- |
| Arkiv | `brfv2-backup-20260730-074335-fd3e.zip`, 62 570 byte, 16 filer, `-rw-------` | ✅ |
| `unzip -t` | inga fel | ✅ |
| Manifest | `brfv2-backup/v1`, `appVersion 0.2.0`, tenant `fredling` med `documents: 5` | ✅ |
| `auth.db` i arkivet | **identisk** med den levande vid kopieringstillfället (`924512cb…`) | ✅ |
| De fem PDF:erna i arkivet | **bit-identiska** med `~/pilot-korpus/` | ✅ |
| Index i arkivet | 5 dokument, 13 chunks | ✅ |
| Modelladressen | `http://127.0.0.1:8000/v1` följde med | ✅ |

**Flyttad till annan media** *(runbookens krav)*: kopierad till
`agenntserver:~/pilot-sakerhetskopior/`.

| Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- |
| Målkatalog | `drwx------` | `0700` | ✅ |
| Filen | `-rw-------`, 62 570 byte | `0600` | ✅ |
| SHA-256 lokalt | `3ec8b4c331f063532ebd5bbca92fadbf3f7486e05740a76ee3dde0890d448719` | — | — |
| SHA-256 på fjärrsidan | `3ec8b4c331f063532ebd5bbca92fadbf3f7486e05740a76ee3dde0890d448719` | identisk | ✅ |

**Rättigheterna är inte formalia.** Arkivet innehåller `auth.db` med operatörens
verkliga namn och e-postadress — samma omfångsavvikelse som journalen har öppen.
`0700`/`0600` är det som gör att kopian inte blir läsbar för andra konton på
modellvärden.

### 4.5 Inloggningsvägen, prövad separat (steg 4)

Utförd **efter** att säkerhetskopian låg verifierad utanför maskinen. Ordningen var
avsiktlig: hade inloggningen visat sig trasig hade piloten annars stått utan
säkerhetskopia — precis den situation nedgången nyss visade att man inte vill vara i.

| Kontroll | Före | Efter | Utfall |
| --- | --- | --- | --- |
| Antal sessioner | 1 · `e5d31a9d…` | 1 · `894f1e65…` | ✅ |
| Gamla sessionen | finns | **borttagen ur `sessions`** | utloggningen är verklig, inte kosmetisk |
| Ny session skapad | — | `2026-07-30T07:46:07Z`, giltig till `2026-08-13` | lösenordskontrollen kördes |
| `PRAGMA integrity_check` | `ok` | `ok` | ✅ |
| Förening / användare / installationsadmin | 1 / 1 / 1 | 1 / 1 / 1 | ✅ |
| Dokument / chunks | 5 / 13 | 5 / 13 | ✅ |
| Dokumentvyn efter inloggning | — | fem dokument, rätt namn *(a11y-trädet)* | ✅ |

**Säkerhetskopian är fortfarande giltig efter inloggningen — bevisat, inte antaget.**
Arkivets `auth.db` jämfördes tabell för tabell mot den levande:

```
tenants              IDENTISK
users                IDENTISK      (samma id, samma lösenordshash)
memberships          IDENTISK
installation_admins  IDENTISK
sessions             SKILJER       arkiv=e5d31a9d  levande=894f1e65
```

Enda skillnaden är den flyktiga sessionstoken. En återställning ger tillbaka samma
konto och samma data och kräver en ny inloggning — vilket är korrekt beteende.

### 4.6 Nedstängning (steg 7)

| Kontroll | Observerat | Krav | Utfall |
| --- | --- | --- | --- |
| Fönstret stängt normalt | av operatören, inte med `kill` | normalt | ✅ |
| Enheten avslutades rent | `Consumed 11.502s CPU time over 12min 30.003s wall clock time, 1.5G memory peak` — **ingen** `Failed`, ingen signal, ingen coredump | ren avslutning | ✅ |
| `pgrep -ax brfv2-desktop` | ingen träff | tomt | ✅ |
| Backend-process kvar | ingen | ingen | ✅ |
| Appens port `39631` | lyssnar inte längre | stängd | ✅ |
| Data efter nedstängning | `integrity_check ok`, 1/1/1, 5 dokument, 13 chunks, inga WAL-rester | oförändrad | ✅ |
| Ingen `backend.log.2` | stämmer — backend startade aldrig om under passet | ingen omstart | ✅ |
| Tunneln stängd | pid `63208` SIGTERM; inget lyssnar på `8000`; probe får ingen kontakt | stängd | ✅ |
| Leveransträdet efter passet | `a702a337…` | oförändrat | ✅ |

### 4.7 Metodnotering — ett falsklarm som inte får läsas som ett fynd

En första avläsning av a11y-trädet rapporterade **noll** dokument i vyn. Orsaken var
mitt eget filter: WebKit exponerar knapparna med rollnamnet `button`, inte
`push button`. Med rätt filter syns alla fem. Felet låg i avläsningsverktyget, inte
i produkten, och antalet är dessutom bekräftat oberoende av a11y-trädet — ur
`documents.json` och ur arkivets innehåll. Det redovisas därför att en läsare annars
kan stöta på den första siffran i transkriptet och tro att den betyder något.

---

## 5. Vad den här filen **inte** fastställer

* **Inte varför värden gick ned.** Journalen slutar utan felmeddelande och
  särskiljer inte möjliga orsaker. Filen fastställer att orsaken inte går att läsa
  ut, inte vad den var.
* **Inte att produkten är oskyldig i någon absolut mening.** Den fastställer att
  *ingenting i det tillgängliga materialet knyter nedgången till produkten* — det
  är ett svagare och sannare påstående.
* **Inte att säkerhetskopian går att återställa.** Arkivet är kontrollerat post för
  post mot originalet, men **ingen återställning har utförts**. M8 och M9 hör till
  slinga 4. Att en zip innehåller rätt bytes är inte samma sak som att
  återställningsvägen fungerar, och den skillnaden får inte suddas ut.
* **Inte att inloggningsrutan visas efter en omstart.** Den prövade vägen var
  utloggning → inloggning i en körande app. En start med *utgången* session är inte
  prövad, eftersom sessionen är giltig till 2026-08-13.
* **Inte att §8:s stoppkriterium 1 (isolering mellan föreningar) är prövat.** Det
  kräver mer än en förening och står fortfarande oprövat, som B0 redan noterade.

---

## 6. Regression efter passet

*Verifierat 2026-07-30 09:55.*

| Svit | Utfall | Krav |
| --- | --- | --- |
| `backend/tests` med `BRFV2_RPM=~/pilot-artefakter/…` | **657 passed, 3 skipped** | baslinjens 657/3 ✅ |
| `test_desktop_acceptance_evidence.py` (A3-skyddet) | **7 passed** | 7 ✅ |
| Leveransträdet efter allt | `a702a337…` | oförändrat ✅ |
| Ändringar i `REPRO_DELIVERY_PATHS` | **inga** | inga ✅ |

**Avvikelse som förklaras, inte döljs:** en första körning gav `620 passed, 40
skipped`. Skillnaden är inte en regression — totalen är oförändrad (660) och de 37
extra hoppen är samtliga `test_desktop_artifact.py` med skälet *"ingen byggd RPM
hittades"*. `BRFV2_RPM` var inte satt i den körningen. Med arkivets RPM angiven är
utfallet exakt baslinjens 657/3, och de tre kvarvarande hoppen är samma tre som
alltid (`jina`-vikter, `RUN_LLM_TESTS`, ingen datarot i checkouten).

Att artefakttesterna kördes mot **arkivet** och inte mot en nybyggd RPM är
avsiktligt: det gör körningen till ett bevis på att den arkiverade filen fortfarande
går att läsa och inspektera på plats efter värddatorns nedgång.
