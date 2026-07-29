# Slinga 1 — pilotens startevidens

Datum: 2026-07-29
Ärende: XS-54 (slinga 1 i [PILOTPLAN.md](../../pilot/PILOTPLAN.md) §5)
Maskin: Fedora 44, kernel `7.1.5-200.fc44.x86_64`, KDE/Wayland
Utförd av: agent i repo-sessionen, på uppdrag av Simon Fredling Jack

> Det här dokumentet visar att **pilotmiljön går att återställa från en arkiverad
> artefakt** och att **evidensinsamlingen inte kan skada tidigare evidens**.
> Det säger ingenting om produktens beteende i drift — inget pilotpass har körts,
> appen har inte startats, och ingen fråga har ställts.

---

## A1 — artefakten återskapad och arkiverad

Ett ombygge i en **ren, fristående checkout** av den godkända commiten, på en
annan sökväg än någon tidigare byggkatalog:

```bash
git clone --no-local <repo> ~/brfv2-pilot-build/xs54-a1
git -C ~/brfv2-pilot-build/xs54-a1 checkout --detach 84b6fc8
git status --porcelain            # tomt
(cd backend && uv sync) && (cd brfv2-mockup && npm ci)
ops/build-runtime.sh && ops/package-desktop.sh
```

| Kontroll | Utfall |
| --- | --- |
| Leveransträdet i checkouten | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` — det BP2 granskade |
| SHA-256 på den ombyggda RPM:en | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |
| Väntat värde (pilotplanen §1) | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` — **identiskt** |
| Storlek | 574 604 029 byte |

Reproducerbarheten är därmed inte längre bara ett bevis från XS-49/XS-52 utan
pilotens egen försäkring (riskregistret R4): skulle arkivet gå förlorat går
artefakten att göra om, från källor som går att checka ut, och få samma bytes.

### Arkivets plats och identitet

Arkiverat **utanför `dist/`** (begränsning 10 — rotens `npm run build` raderar
`dist/`), skrivskyddat, med sitt härkomstkvitto och en kontrollsummefil:

```
~/pilot-artefakter/
├── brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm                  (0444, 574 604 029 byte)
├── brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm.provenance.json  (0444, 51 155 byte)
└── SHA256SUMS
```

```
6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d  ./brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
bbf6ee99120d2a5397c919f4fe10457888eea5db143c3d54c0276e9dc60f565f  ./brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm.provenance.json
```

`sha256sum -c SHA256SUMS` i arkivkatalogen: båda **OK**. Sökvägen är den
runbooken redan pekar ut (`ARKIV=~/pilot-artefakter`).

### Kvittots innehåll

| Fält | Värde |
| --- | --- |
| `commit` | `84b6fc853ec047fe9b438f2e1c0a2aed08cfe754` |
| `dirty` | `false` |
| `deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| `sourceDateEpoch` | `1785196800` (2026-07-28T00:00:00Z) |
| `rpm.headerSha256` | `5fc97bcef7da938e658cd486443f5110d97f26ce7b86bd0facadc9ae233243fe` |
| `rpm.buildHost` / `payloadCompressor` | `reproducible.brfdokumentai.se` / `zstd` |
| `providerExclusion` | 0 fynd, granskat på den **uppackade** RPM:en |

### Arkivet är samma artefakt som den installerade

Den kontroll som binder ihop arkivet med maskinen, och som pilotplanens §1 inte
gjorde:

```bash
rpm -q --qf '%{SHA256HEADER}' brf-dokument-ai                     # installerad
python3 -c "...provenance.json...['rpm']['headerSha256']"         # arkivet
```

Båda ger `5fc97bcef7da938e658cd486443f5110d97f26ce7b86bd0facadc9ae233243fe`.
Den installerade pilotinstallationen och den arkiverade filen är alltså samma
artefakt — inte två artefakter som råkar ha samma versionsnummer.

`%{SIGPGP}` är `(none)`: paketet är osignerat, som väntat (begränsning 1).
SHA-256-kontrollen före varje installation är det som ersätter signaturen.

---

## A2 — baslinjekontrollerna omkörda som pilotens startevidens

Alla kontroller i pilotplanen §1, körda om 2026-07-29 efter A1:

| Kontroll | Kommando | Utfall |
| --- | --- | --- |
| Paketet är installerat | `rpm -q brf-dokument-ai` | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| Installerat träd = paketet | `rpm --verify brf-dokument-ai` | exitkod **0**, inga skillnader |
| Installationen är den godkända | `BUNDLE.json.deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| Leverantörsgränsen i det installerade trädet | `ops/inspect_payload.py --installed --scope installed` | 45 kontroller, **0 fynd**, 4 675 filer, payload `55c20520e4a5054c…` |
| Skalets identitet | `sha256sum /usr/bin/brfv2-desktop` | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` |
| Leveransträdet i arbetskopian | pilotplanen §4.1 | `a702a337…` |
| Ingen användardata finns ännu | `ls ~/.local/share/se.brfdokumentai.desktop` | katalogen saknas |
| Diskutrymme | `df -h /home` | 356 GB fritt |

**Första starten är fortfarande en genuin förstagångsstart** — datakatalogen har
inte skapats, eftersom ingenting i slinga 1 startar applikationen.

### Systemversioner vid pilotstart

Registrerade därför att risk R1 säger att en uppgradering av dem kräver omkörd
acceptans innan piloten återupptas:

| Paket | Version |
| --- | --- |
| `webkit2gtk4.1` | `2.52.5-1.fc44` |
| `gtk3` | `3.24.52-2.fc44` |
| `tesseract` | `5.5.2-1.fc44` |
| `tesseract-langpack-swe` | `4.1.0-12.fc44` |
| kernel | `7.1.5-200.fc44.x86_64` |

---

## A3 — evidensinsamlingen kan inte skada tidigare evidens

**Felet:** skärmbildsnamnen i `backend/scripts/desktop_acceptance.py` var
hårdkodade `xs49-*` och skrevs till `docs/evidence/`. En körning med förvalda
inställningar skrev alltså över den committade evidens som XS-49 godkändes på —
tyst, och med bilder från en helt annan körning.

**Reparationen har två halvor, och det är den andra som håller:**

1. Namnen kommer från en körningsetikett: `--run-label <etikett>` ger
   `<etikett>-desktop-<vy>.png` och `<etikett>-desktop-acceptance.json`.
   Ingen etikett är inbyggd i koden längre.
2. Varje målfil som **git redan spårar** stoppar körningen innan den börjar.
   Det gäller alla etiketter, inte bara den som råkade krocka, och även den
   äldre vägen `--output <fil>`. Att skriva över committad evidens kräver
   `--overwrite-evidence` — ett uttryckligt val, inte en förvald bieffekt.

Kontrollen görs före modellkontrollen, så en operatör med fel etikett får veta
det utan att först behöva resa SSH-tunneln.

### Demonstration

```
$ ...desktop_acceptance.py --application /usr/bin/brfv2-desktop --run-label xs49
AcceptanceError: Run label 'xs49' writes over evidence that is committed:
  docs/evidence/xs49-desktop-acceptance.json
  docs/evidence/xs49-desktop-answer-highlight.png
  docs/evidence/xs49-desktop-documents.png
  docs/evidence/xs49-desktop-refusal.png
  docs/evidence/xs49-desktop-settings.png
  docs/evidence/xs49-desktop-setup.png
  docs/evidence/xs49-desktop-startup-failure.png
That record is what an earlier acceptance was approved on. Give this run its own
--run-label, or pass --overwrite-evidence if replacing it is the intent.

$ ...desktop_acceptance.py --application /usr/bin/brfv2-desktop --run-label pilot
AcceptanceError: GET http://127.0.0.1:8000/v1/models: Connection refused
        ^ passerade evidensskyddet och stoppades först av att tunneln är nere

$ ...desktop_acceptance.py --run-label pilot --output docs/evidence/xs49-desktop-acceptance.json
AcceptanceError: Run label 'pilot' writes over evidence that is committed:
  docs/evidence/xs49-desktop-acceptance.json
```

`git status --porcelain docs/evidence/` efter alla tre försöken: **tomt**.

`make desktop-acceptance` och `make desktop-acceptance-installed` namnger inte
längre någon filsökväg; de skickar `--run-label $(RUN_LABEL)` respektive
`--run-label $(RUN_LABEL)-installed`, förvalt `pilot`.

### Leveransträdet är orört

Ändringarna ligger i `backend/scripts/`, `backend/tests/` och `Makefile` — alla
utanför `REPRO_DELIVERY_PATHS`.

```bash
git ls-tree -r HEAD -- <REPRO_DELIVERY_PATHS> | sha256sum
```

| När | Summa |
| --- | --- |
| Före A3 | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| Efter A3 | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |

Ingen ändrad fil matchar någon leveranssökväg. Artefakten är fortfarande den
BP2 granskade, och det installerade paketet behöver inte röras.

### Regressionssvit (pilotplanen §6.5)

| Svit | BP2-baslinje | Nu |
| --- | --- | --- |
| `pytest backend/tests` (`BRFV2_REQUIRE_ARTIFACT=1`, `BRFV2_RPM=<arkivet>`) | 650 passed / 3 skipped | **657 passed / 3 skipped** |
| `npm test` (brfv2-mockup) | 21 | **21** |
| `npm run test:e2e` | 11 | **11** |
| `cargo test --locked` | 5 | **5** |
| `npm run lint` (rot + mockup) | rent | rent (exitkod 0; rotprototypens fyra sedan tidigare kända `no-unused-vars`-varningar kvarstår oförändrade) |

**Avvikelsen från baslinjen är 650 → 657 och är avsiktlig:** sju nya tester i
`backend/tests/test_desktop_acceptance_evidence.py` håller fast reparationen —
att namnen följer etiketten, att en ogiltig etikett avvisas, att den committade
XS-49-evidensen känns igen som committad, att en ledig etikett är fri att
skriva, att `--output` skyddas likadant, och att skyddet inte beror på vilka
faser som körs. Inget befintligt test ändrades eller togs bort.

Artefakttesterna kördes mot den **arkiverade** RPM:en, vilket samtidigt är en
oberoende kontroll av att arkivfilen är läsbar och granskningsbar där den ligger.

---

## A4 — den syntetiska korpusen som filer

`backend/scripts/export_corpus.py` renderar de fem dokumenten ur
`scripts.seed.render_pdf` till filer, så att de kan laddas upp genom produktens
**egen** uppladdningsväg i slinga 2 i stället för att seedas in bakvägen.

```
~/pilot-korpus/
```

| SHA-256 | Byte | Sidor | Dokument |
| --- | --- | --- | --- |
| `79f4012a1634243c46cd5125e13d2ef3354e827cdf7a3c31759ab6e22b6fcb60` | 12 576 | 3 | Stadgar Brf Gjutformen 12.pdf |
| `10a5ac6bdbc946df44b0ef8fd695951ea7982ed49e129477c7d9b4413cfa70e2` | 9 793 | 3 | Årsredovisning 2025.pdf |
| `713d00a7777e7fb13c34253541bf0b20c97700fb752f3f5d6271641c18e57bca` | 7 714 | 2 | Styrelseprotokoll 2026-03-12.pdf |
| `c448de15fd23e14d74382c4b63b1b843cf4849730be932e42f5f74100a05c236` | 6 912 | 2 | Snöröjningsavtal 2026.pdf |
| `a4b71600fefeba6f80a5e9e83b3b8e1dc3d29160f27dedcac1e238b5d89bc702` | 8 542 | 3 | Underhållsplan 2026-2036.pdf |

Renderingen är deterministisk (fasta dokumentmetadata, `no_new_id=True`): en
andra körning rapporterade alla fem som **oförändrade**, och `sha256sum -c
korpus.sha256` ger OK för alla fem. Det är den egenskapen som gör att de
uppladdade dokumenten bevisligen är de dokument som facit i
`backend/eval/golden.json` beskriver — sidhänvisningarna i frågeuppsättningen
(§6.3) gäller alltså dessa bytes.

Filerna ligger utanför checkouten med avsikt: de är genererade bytes vars
generator redan står under versionshantering.

---

## A5 — pilotjournalen

[`docs/pilot/JOURNAL.md`](../../pilot/JOURNAL.md) är upplagd med mätvärdestabell
(M1–M10), passmall, avvikelselogg och en första rad för slinga 1. Produkten har
ingen telemetri; utan journalen finns inga mätvärden alls (begränsning 11).

---

## Vad slinga 1 **inte** fastställer

* Ingenting om produktens beteende i drift. Appen har inte startats, ingen
  förening skapats, inget dokument laddats upp och ingen fråga ställts.
* Att en **ominstallation** från arkivet fungerar. Arkivet är verifierat som
  fil och som granskningsbar artefakt, och det är bevisat samma artefakt som den
  installerade — men av-/ominstallationscykeln är övning D3 i slinga 4.
* Att den formella pilotacceptansen (§6.1) är grön. Den kräver en nåbar
  modelltjänst och har inte körts; tunneln var nere under slinga 1.
* Att den mänskliga tangentbordssmoken är attesterad. Den hör till slinga 2.
* Ingenting om andra maskiner, andra människor eller riktig korpus — de ligger
  utanför hela piloten (pilotplanen §2).
