# Runbook — kontrollerad Fedora-pilot

Operativ instruktion för piloten som [PILOTPLAN.md](PILOTPLAN.md) beskriver.
Gäller artefakten `6ba028fb…` (commit `84b6fc8`) och ingen annan.

Produktens allmänna användardokumentation finns i
[DESKTOP-FEDORA.md](../DESKTOP-FEDORA.md); den här filen upprepar den inte utan
lägger till det piloten behöver: installation med identitetskontroll, återgång,
dataåterställning, sessionsrutin, mänsklig tangentbordssmoke och
incidentinsamling.

**Evidensklasser i den här filen:** *Verifierat* = kört och observerat på den här
maskinen eller i BP2-evidensen. *Härlett* = följer av kod som är läst, men den
exakta sekvensen är inte körd. Härledda steg är märkta, och att köra dem är just
vad slinga 4 i pilotplanen går ut på.

---

## Installation

Endast från den arkiverade artefakten, aldrig från en nybyggd fil utan kontroll.

```bash
ARKIV=~/pilot-artefakter                       # utanför dist/ — rotens npm run build raderar dist/
RPM=$ARKIV/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm

sha256sum "$RPM"
# MÅSTE vara: 6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d

sudo dnf install "$RPM"
```

`dnf` varnar för att paketet saknar OpenPGP-signatur. Det är väntat och
accepterat för den här piloten (pilotplanen §9, begränsning 1); SHA-256-kontrollen
ovan är det som ersätter signaturen. `dnf` drar in `webkit2gtk4.1`, `gtk3`,
`tesseract` och `tesseract-langpack-swe`.

Direkt efter installation:

```bash
rpm --verify brf-dokument-ai; echo "verify=$?"          # ska vara 0
python3 -c "import json;print(json.load(open('/usr/lib/BRF Dokument-AI/runtime/BUNDLE.json'))['deliveryTree'])"
# ska vara: a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083
python3 ops/inspect_payload.py --installed --scope installed
# ska vara: kontroller: 45 … fynd: 0
```

Starta sedan **BRF Dokument-AI** från applikationsmenyn. Att starta från terminal
är tillåtet vid felsökning men räknas som terminalingripande i journalen (mätvärde
M2) — piloten mäter bland annat hur ofta det behövs.

*Verifierat: alla tre kontrollerna kördes 2026-07-29 mot den redan installerade
artefakten, med de utfall som står ovan.*

### Första start

Uppstartsdialogen skapar föreningens namn, administratörskontot (minst 12 tecken)
och modelladressen. Modelladressen i piloten är `http://127.0.0.1:8000/v1`, vilket
kräver att SSH-tunneln är uppe **innan** dialogen fylls i, annars misslyckas
probningen.

Kontot som skapas här blir **installationsadministratör**. Den behörigheten kan
inte delas ut i gränssnittet efteråt, och den är det enda som får peka om
modelltjänsten.

---

## Sessionsrutin

### Före passet

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver     # egen terminal, lämnas öppen
curl -s http://127.0.0.1:8000/v1/models | head -c 300   # ska annonsera gemma
```

- [ ] Tunneln uppe och annonserar Gemma 4 12B
- [ ] Appen startad från applikationsmenyn
- [ ] Modelltjänsten svarar på probe från **Appinställningar** — inte bara
      `ready` i gränssnittet. `ready` är konfigurationsstatus, inte nåbarhet
- [ ] Leveransträdets summa oförändrad (kommandot i pilotplanen §4.1)

### Efter passet

- [ ] Journalrad skriven (`docs/pilot/JOURNAL.md`): pass, frågeutfall,
      terminalingripanden, avvikelser
- [ ] Har passet skapat ny data: säkerhetskopia skapad **och flyttad till annan
      media**
- [ ] Fönstret stängt; `pgrep -f brfv2-desktop` tomt
- [ ] Tunneln stängd (Ctrl+C)

**Att stoppa appen:** stäng fönstret. Efter en återställningsomstart kör appen
under ett **nytt pid i samma processgrupp** — att döda det pid man startade
stoppar alltså inte nödvändigtvis appen. Kontrollera alltid med `pgrep`, och
signalera processgruppen om något behöver stängas hårt:

```bash
pgrep -f brfv2-desktop
kill -TERM -"$(ps -o pgid= -p "$(pgrep -f brfv2-desktop | head -1)" | tr -d ' ')"
```

---

## Mänsklig tangentbordssmoke

Fysisk tangentbordsautomation är blockerad i den här KWin/WebKit-miljön, så den
här sekvensen körs av en människa vid ett fysiskt tangentbord och attesteras i
journalen. Den ersätter ingen automatkörning — den täcker vägen automatiken inte
når.

Gör i ordning, i det verkliga fönstret, med musen orörd där det går:

1. Skriv en fråga i chattrutan och tryck **Enter**. Frågan ska skickas (inte
   radbryta, inte försvinna).
2. **Skift+Enter** i chattrutan: ska ge radbrytning, inte skicka.
3. **Tab** genom gränssnittet: fokusringen ska vara synlig och gå i en begriplig
   ordning.
4. **Escape** i en öppen dialog: ska stänga den.
5. Markera text i ett svar och **Ctrl+C**; klistra in i en annan applikation och
   kontrollera att texten följde med.
6. **Ctrl++ / Ctrl+-** eller zoomknapparna i PDF-vyn: zoomnivån ska ändras.
7. Klicka ett citat, och kontrollera att rätt sida visas med synlig markering.
8. Ändra fönsterstorlek till ungefär 1000×700: ingen horisontell scroll.

Anteckna i journalen: datum, vilka steg som gick, vilka som inte gick, och att
attesteringen är gjord av en människa. Evidensklassen är **operatörsattestering**
och ska stå så även i BP5-underlaget.

---

## Återgång

Piloten kör en enda version, så "återgång" betyder något av tre saker.

### 1. Återgång av data — appen är hel, innehållet är fel

**Appinställningar → Säkerhetskopior → Återställ.** Bytet sker inte under en
igångvarande databas: kopian *förbereds*, och själva bytet görs vid nästa start
innan något arkiv öppnas. Appen erbjuder omstart direkt. Misslyckas bytet rörs
inte befintliga data, och orsaken visas under **Lagring och version**.

Vilken inloggad användare som helst får skapa och återställa säkerhetskopior; att
peka om modelltjänsten kräver installationsadministratör.

*Verifierat i BP2-acceptansen: förberedd återställning applicerades vid start och
den avvikelse som gjorts efter kopian rullades bort.*

### 2. Återgång av paket — installationen är trasig

```bash
sudo dnf remove brf-dokument-ai        # datakatalogen under ~/.local/share lämnas kvar
sudo dnf install "$RPM"                # samma arkiverade fil, samma SHA-256
```

`dnf downgrade` finns inte som väg: det finns bara en version och inget
paketrepo. Den arkiverade filen **är** återgångsvägen. Skulle arkivet vara
förlorat är försäkringen att bygget är reproducerbart — ett ombygge från
`84b6fc8` i ren checkout ger samma bytes:

```bash
git -C <ren checkout av 84b6fc8> status --porcelain    # måste vara tomt
make desktop-package
sha256sum dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm  # 6ba028fb…
```

### 3. Versionsbyte under piloten

Skulle en ny version behöva installeras mitt i piloten gäller ordningen, i den
här följden och inte någon annan, eftersom det inte finns någon
migreringsmekanism och ingen testad uppgraderingsväg:

1. skapa säkerhetskopia i appen och flytta den till annan media;
2. `sudo dnf remove brf-dokument-ai`;
3. `sudo dnf install <ny rpm>` efter SHA-256-kontroll;
4. starta, kontrollera att föreningar, dokument och konton finns kvar;
5. kör om den formella pilotacceptansen;
6. journalför att baslinjen bytts — mätvärden före och efter är inte jämförbara
   utan den noteringen.

**Ingen `dnf upgrade`.** Den vägen är otestad (pilotplanen §9, begränsning 2).

---

## Dataåterställning

```
~/.local/share/se.brfdokumentai.desktop/
├── data/            föreningar, PDF:er, index, konton, appkonfiguration
├── backups/         säkerhetskopior (zip)   ← ligger UTANFÖR data/
├── restore-staging/ förberedd återställning
└── logs/            backend.log, backend.log.1
```

Att `backups/` ligger utanför `data/` är det som gör återställning möjlig även när
`data/` är borta.

**Om `data/` är raderad eller obrukbar** *(Härlett — läst ur koden, inte kört;
detta är precis vad övning D4 i pilotplanen ska bevisa)*:

1. starta appen — den möter en tom installation och visar uppstartsdialogen;
2. skapa ett tillfälligt konto och en tillfällig förening;
3. **Appinställningar → Säkerhetskopior**, välj kopian, återställ;
4. starta om när appen erbjuder det;
5. den återställda installationens konton gäller igen, och
   installationsadministratör adopteras för den återställda installationen om
   ingen sådan finns i kopian;
6. verifiera: föreningar, dokument, ett citat som löser till rätt sida.

**Om hela maskinen är borta:** installera Fedora 44, installera den arkiverade
RPM:en efter SHA-256-kontroll, starta, och följ stegen ovan med kopian från den
andra median. Det finns ingen molnlagring och ingen extern databas — kopian är
allt som finns.

---

## Incidenthantering

| Klass | Vad | Åtgärd |
| --- | --- | --- |
| **S1** | Ett stoppkriterium i pilotplanen §8 | Stoppa appen. Samla evidens (nedan). Skriv incidentanteckning. Lägg upp en Linear-issue som säger att den blockerar BP5. Ingen fortsatt pilotdrift före diagnos |
| **S2** | Degraderad drift: tunnel, GPU, modellvärd | Pausa passet, följ felsökningen nedan, journalför |
| **S3** | Kosmetiskt eller irriterande | Journalrad; blir underlag till erfarenhetsåterföringen |

### Evidensinsamling vid S1

```bash
D=docs/evidence/pilot/incident-$(date +%F-%H%M)
mkdir -p "$D"
cp -a ~/.local/share/se.brfdokumentai.desktop/logs/. "$D/logs/"
rpm --verify brf-dokument-ai > "$D/rpm-verify.txt" 2>&1; echo "exit=$?" >> "$D/rpm-verify.txt"
python3 ops/inspect_payload.py --installed --scope installed > "$D/inspect-installed.txt" 2>&1
sha256sum /usr/bin/brfv2-desktop >> "$D/inspect-installed.txt"
cp -a ~/.local/share/se.brfdokumentai.desktop/data "$D/data-snapshot"   # syntetisk korpus
```

Lägg till skärmbild av felfönstret om ett sådant visades, och en anteckning med
vad som gjordes precis före. `data-snapshot` går att spara och dela just därför
att korpusen är syntetisk — med riktig korpus vore samma steg en
personuppgiftsfråga.

---

## Felsökning

| Symtom | Trolig orsak | Åtgärd |
| --- | --- | --- |
| Appen startar inte, eget felfönster med teknisk orsak | Trasig installation eller körmiljö | Läs orsaken i fönstret; `rpm --verify brf-dokument-ai`; ominstallera från arkivet |
| Arbetsfönstret stängs mitt i, felfönster förklarar | Backendprocessen dog | Data ligger kvar. Läs `logs/backend.log.1`, starta om. Tre gånger i samma pass = stoppkriterium |
| AI-chatten svarar med leverantörsfel | Tunneln nere eller modellvärden otillgänglig | `curl -s http://127.0.0.1:8000/v1/models`; öppna tunneln igen. Detta är korrekt beteende, inte ett fel i produkten |
| `ready` visas men inget svar kommer | `ready` är konfigurationsstatus, inte nåbarhet | Kör probe från Appinställningar och kontrollera tunneln |
| Modelladressen går inte att spara | Adressen bryter mot policyn, eller kontot är inte installationsadministratör | Endast loopback, eller `https` mot privat nät. Se `GET /api/desktop/model-endpoint-policy` |
| Uppladdat dokument ger inget citat | Extraktionen tom (skannad PDF utan OCR) eller frågan verkligen obesvarbar | Kontrollera att `tesseract-langpack-swe` finns; annars är vägran korrekt |
| Appen verkar stoppad men körs | Omstart spawnar nytt pid i samma processgrupp | `pgrep -f brfv2-desktop`, signalera processgruppen |
| Efter systemuppgradering: fönstret renderar fel eller startar inte | `webkit2gtk4.1`/`gtk3` har bytt version | Notera versionerna, kör om den formella acceptansen innan piloten återupptas |
| Container-/GPU-fel på `agenntserver` | NVML-mismatch, CDI-spec, CUDA | Felsökningskedjan i [DEPLOY-SELFHOSTED-LLM.md](../DEPLOY-SELFHOSTED-LLM.md) |
| Dokument från fel förening syns | Isoleringsregression | **Stoppa omedelbart.** S1. Detta är stoppkriterium 1 |

---

## Vad som aldrig görs under piloten

* installera en artefakt vars SHA-256 inte är kontrollerad;
* köra `dnf upgrade` av paketet;
* ändra något under `REPRO_DELIVERY_PATHS` (pilotplanen §4.1);
* ladda upp riktiga föreningsdokument eller andra personuppgifter;
* köra acceptansen med förvald evidenskatalog innan arbetspunkt A3 är gjord —
  den skriver då över committad XS-49-evidens;
* köra rotens `npm run build` med den arkiverade RPM:en liggande i `dist/`.
