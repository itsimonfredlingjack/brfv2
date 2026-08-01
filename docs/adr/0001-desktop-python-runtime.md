# ADR 0001 — Så paketeras Python-körmiljön i Fedora-desktopleveransen

Status: **antagen** (XS-47, 2026-07-28), **reviderad** (XS-49, 2026-07-28)
Ersätter: hypotesen "PyInstaller `onedir` + Tauri `externalBin`" från XS-46.

## Beslut

Den installerade applikationen levererar **exakt det CPython-bygge som
`ops/pins.json` pinnar** — samma python-build-standalone-utgåva som uv löser
ut för tolken testsviten kör på — med **exakt samma hash-låsta wheels** som
`backend/uv.lock` löser ut. Trädet stegas av `ops/build-runtime.sh` till
`src-tauri/runtime/` och följer med RPM:en som Tauri-**resurser** — inte som
`externalBin`.

## Revidering i XS-49: pinnat arkiv i stället för byggmaskinens träd

Första utkastet kopierade tolken **ur uv:s katalog på byggmaskinen**
(`~/.local/share/uv/python/…`). Det gav rätt version men fel egenskaper:

* **Identiteten var inte kontrollerbar.** "Den tolk uv råkar ha installerat" är
  inte en identitet någon kan verifiera i efterhand. Det fanns ingen URL, ingen
  förväntad SHA-256 och inget som skulle ha upptäckt om trädet ändrats.
* **Trädet är föränderligt.** uv:s katalog samlar `__pycache__` från allt som
  någonsin kört mot den tolken. Två byggmaskiner — eller samma maskin före och
  efter ett annat projekt — stegade därför olika bytes.

Nu hämtas i stället det pinnade arkivet av `ops/fetch_pinned.py`, som
kontrollerar SHA-256 **innan** det packas upp. Cachen är en effektivitetsfråga:
en cachad fil används bara om dess hash stämmer, annars kastas den och hämtas
om. Bygget avbryter om den pinnade tolkens `sys.version` inte är identisk med
`backend/.venv`s — det är det som gör "det som skickas är det som testades" till
ett faktum i stället för en avsikt.

Samma princip gäller `uv` självt (pinnat arkiv, verifierad hash, verifierad
`--version`) och embeddervikterna (exakt revision, explicit fillista, SHA-256
per fil). Se [0003-reproducerbar-rpm.md](0003-reproducerbar-rpm.md) för vad det
gör med artefaktens bytes.

## Varför inte PyInstaller

Båda alternativen byggdes och kördes på den faktiska Fedora 44-maskinen innan
beslutet togs.

| | PyInstaller `onedir` | Flyttad CPython (valt) |
| --- | --- | --- |
| Byggde och startade backend | ja | ja |
| `model2vec`, `pymupdf`, `uvicorn` fungerade | ja | ja |
| Storlek (utan embeddervikter) | 172 MB | 277 MB, 263 MB efter trimning |
| Andel av hela paketet (776 MB) | — | ~12 % större |
| Extra byggverktyg i den betrodda kedjan | ja (`pyinstaller`) | nej |
| Beroendeupplösning | egen modulgrafanalys | `uv.lock` med hashar |
| Stackspår och felsökning | `_MEIPASS`, omskrivna sökvägar | riktiga filsökvägar |

PyInstaller fungerade — det är värt att säga rakt ut, eftersom XS-46:s hypotes
byggde på det. Skillnaden som avgjorde var inte "fungerar/fungerar inte" utan
**vad som kan gå sönder tyst senare**:

1. **Det som testas är det som skickas.** `uv export --frozen` ger samma
   pinnade versioner och samma hashar som `pytest` körde mot. PyInstaller
   härleder i stället sin egen modulgraf; en beroendeuppgradering kan tappa en
   lat import (`app.llm` importerar `anthropic` inuti en konstruktor, `model2vec`
   laddar backends dynamiskt) utan att bygget klagar — felet dyker upp först
   hos användaren.
2. **90 MB på ett 776 MB-paket är ingen storleksvinst.** Paketet domineras av
   embeddervikterna (513 MB). Att byta bort spårbarhet mot 12 % är fel
   avvägning här.
3. **`externalBin` var aldrig ett verkligt alternativ.** Båda metoderna
   producerar ett *katalogträd*, inte en ensam körbar fil, och `externalBin`
   tar en fil. Resurser krävs oavsett — så `externalBin` köpte ingenting.
4. **Ingen shell-plugin behövs.** Skalet startar tolken direkt med
   `std::process::Command`. Hade vi gått via Tauris sidecar-API hade
   `tauri-plugin-shell` behövt installeras, vilket öppnar en IPC-yta som
   XS-46:s säkerhetsbevis uttryckligen vilar på att inte finnas.

## Vad som medvetet *inte* följer med

`ops/build-runtime.sh` tar bort tre saker ur det upplösta trädet, och det är
säkerhet snarare än storlek:

* **`anthropic`** — den enda andra nätverks-LLM-klienten i beroendeträdet. Utan
  den finns ingen kodväg alls från den installerade produkten till en
  tredjepartsmodell, oavsett miljövariabler. Bygget avbryter om paketet ändå
  går att importera.
* **`hf_xet`, `pip`, `setuptools`** — finns bara för att hämta saker vid
  körning. En paketerad applikation ska inte kunna göra det.
* **`backend/scripts/`** — demoseedaren. Den installerade produkten kan
  strukturellt inte skapa demoföreningar eller demolösenord; första körningen
  går genom `/api/desktop/setup`.

Embeddervikterna (`minishlab/potion-multilingual-128M`, 513 MB) följer däremot
*med* i stället för att hämtas vid första start. En tyst hämtning från
huggingface.co vid första körningen vore precis den dolda utgående trafik
produkten lovar att inte ha.

Vikterna är pinnade till revision `73908c34…` med en explicit fillista och en
förväntad SHA-256 per fil (`ops/pins.json`). Tidigare hämtades de med
`snapshot_download()` mot den globala Hugging Face-cachen, vilket betyder "den
revision som råkar ligga på byggmaskinen" — en identitet som varken kan
granskas eller reproduceras.

## Konsekvenser

* RPM:en är stor (~700 MB installerat). Det är den ärliga kostnaden för
  offline semantisk sökning; den dokumenteras i stället för att döljas.
* En Python-uppgradering kräver ombygge av körmiljön, inte bara av skalet.
  `make desktop-runtime` är därför ett eget steg som `make desktop-package`
  alltid kör.
* Trädet måste vara flyttbart. Bygget avbryter på absoluta eller utåtpekande
  symlänkar — den kontrollen fanns inte i första utkastet och fångade
  omedelbart att `uv`:s `cpython-3.12-…`-symlänk stegades i stället för det
  verkliga trädet, vilket hade gett en RPM som bara fungerar på byggmaskinen.
