# BRF Dokument-AI — skrivbordsapplikationen för Fedora

Den installerade applikationen är samma produkt som webbleveransen: samma
React-gränssnitt, samma Python-backend, samma grundningsgarantier. Skillnaden
är att allting kör lokalt på användarens dator och startas som ett vanligt
skrivbordsprogram.

## För användaren

### Installera

```bash
sudo dnf install ./brf-dokument-ai-0.2.0-1.x86_64.rpm
```

`dnf` drar in det applikationen faktiskt behöver: `webkit2gtk4.1`, `gtk3`,
`tesseract` och `tesseract-langpack-swe`. Utan svenskt OCR-språkstöd kan
inskannade PDF:er inte tolkas, så paketet vägrar installera sig utan det i
stället för att fallera först när ett dokument laddas upp.

Starta sedan **BRF Dokument-AI** från applikationsmenyn.

### Första gången

Applikationen levereras **utan konton och utan föreningar**. Första starten
visar en uppstartsdialog där du skapar

1. föreningens namn,
2. ditt administratörskonto (minst 12 tecken i lösenordet), och
3. adressen till den självhostade modelltjänsten.

Modelltjänsten kan hoppas över. Då fungerar uppladdning, indexering, sökning
och dokumentvisning som vanligt, men AI-chatten kan inte generera svar — och
säger det rakt ut i stället för att gissa. Adressen kan anges senare under
**Appinställningar**.

### Var ligger mina data?

```
~/.local/share/se.brfdokumentai.desktop/
├── data/            föreningar, PDF:er, index, konton, appkonfiguration
├── backups/         säkerhetskopior (zip)
└── restore-staging/ förberedd återställning
```

Katalogen är `0700` — bara ditt eget OS-konto kommer åt den. Den ligger kvar
vid av- och ominstallation.

### Säkerhetskopiera och återställa

**Appinställningar → Säkerhetskopior.**

* *Skapa säkerhetskopia nu* skriver en zip med alla föreningar, dokument,
  index och konton till `backups/`. Kopiera den till en annan disk — en
  säkerhetskopia som bara ligger kvar på samma hårddisk skyddar mot misstag,
  inte mot hårdvarufel.
* *Återställ* byter inte data under en igång­varande databas. Kopian
  *förbereds*, och själva bytet sker vid nästa start innan något arkiv öppnas.
  Applikationen erbjuder en omstart direkt.
* Misslyckas bytet rörs inte de befintliga uppgifterna, och orsaken visas
  under **Lagring och version**.

### Modelltjänsten

Applikationen kontaktar **exakt en** tjänst utanför datorn: den
OpenAI-kompatibla modelltjänst du själv anger. Det finns ingen
fallback-leverantör: utan konfigurerad adress är genereringsleverantören
`none`, och AI-chatten svarar med ett tydligt fel i stället för att kontakta
någon annan. En eventuell åtkomsttoken lagras `0600` på datorn och skickas
aldrig tillbaka till gränssnittet.

Pilotens modelltjänst är Gemma 4 12B på `agenntserver`; se
[DEPLOY-SELFHOSTED-LLM.md](DEPLOY-SELFHOSTED-LLM.md).

### Om något går fel

Startar inte applikationen visas ett eget felfönster med den tekniska orsaken
i klartext. Dör bakgrundstjänsten medan appen kör stängs arbetsfönstret och
samma felfönster förklarar vad som hände — dina data ligger kvar. Stäng och
starta om.

## För den som bygger paketet

```bash
sudo dnf install rpm-build   # enda systempaketet som paketeringen kräver
make setup                   # en gång per ren checkout
make desktop-package         # -> dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
make desktop-install         # dnf install av den nyss byggda RPM:en
```

Paketet byggs med Fedoras egen `rpmbuild` (spec i
[`ops/brf-dokument-ai.spec`](../ops/brf-dokument-ai.spec)) i stället för Tauris
RPM-bundler, som inte blev klar med den här payloadens storlek. `make setup`
självt behöver fortfarande inget sudo.

`make desktop-package` kör alltid `make desktop-runtime` först, som stegar den
paketerade Python-körmiljön till `src-tauri/runtime/` (~776 MB). Hela
paketeringen tar under en minut efter att körmiljön är stegad. Se
[adr/0001-desktop-python-runtime.md](adr/0001-desktop-python-runtime.md) för
varför körmiljön ser ut som den gör.

Under utveckling behövs ingen paketering:

```bash
make desktop-build && make desktop-run
```

Skalet hittar då `backend/.venv`, `brfv2-mockup/dist` och den vanliga
Hugging Face-cachen i checkouten i stället för den installerade bundlen.

### Verifiering

```bash
make desktop-check                    # Rust-enhetstester + desktopadapterns pytest
make desktop-acceptance               # full journey mot release-bygget
make desktop-acceptance-installed     # samma journey mot /usr/bin/brfv2-desktop
```

Acceptansen kräver en nåbar modelltjänst och vägrar köra utan. Den kör i ett
eget `XDG_DATA_HOME`, så din riktiga installation påverkas aldrig och varje
körning börjar från en genuint okonfigurerad maskin.

## Arkitektur i korthet

```
brfv2-desktop (Rust/Tauri)
 └─ startar  runtime/python/bin/python3 -E -s -B -m app.desktop
     ├─ binder 127.0.0.1:0 (OS-vald port)
     ├─ serverar /brfv2/* (byggt React) och /api/* från SAMMA origin
     ├─ skriver ett maskinläsbart readiness-kontrakt på stdout
     └─ kör produkten i BRF_MODE=desktop
 └─ validerar kontraktet innan fönstret skapas
 └─ tillåter navigation ENDAST till exakt den origin, nekar nya fönster
 └─ övervakar barnet: kod 86 = omstart, annat = felfönster
 └─ SIGTERM till hela processgruppen vid avslut; PR_SET_PDEATHSIG vid abrupt död
```

Skalet exponerar ingen Tauri-IPC mot den HTTP-laddade sidan: `capabilities` är
tom, `withGlobalTauri` är `false` och inga plugins är installerade.
Omstartsbehovet efter en förberedd återställning löses i stället genom
backendens exitkod — inte genom att öppna en IPC-yta.
