# XS-49 — Reparerad skrivbordsleverans: reproducerbarhet, härkomst och modellgräns

Datum: 2026-07-28
Reparerar: [XS-47 — Distribuerbar skrivbordsleverans](xs47-desktop-delivery.md), som BP2 returnerade
Bygger på: [XS-46 — Tauri 2 på Fedora/KDE/Wayland](xs46-tauri-fedora.md) (arkitekturbevis, oförändrat)

> Det här är en **reparerad kandidat inför en ny oberoende BP2-granskning**.
> Dokumentet är inte ett godkännande.

## Vad som var fel, och vad som gäller nu

| BP2:s anmärkning | Vad som faktiskt var fel | Nu |
| --- | --- | --- |
| Acceptansidentitet | Den incheckade evidensen kom från commit `57236762…` med `dirty: true` — alltså från en annan revision och ett träd ingen kan checka ut | Ny evidens, genererad mot RPM:en från `8d8dd73c…` med ren arbetskatalog; de gamla JSON-filerna är **borttagna**, inte omdöpta |
| Reproducerbarhet | Två rena checkouter av samma källor gav olika RPM-filer | Identisk SHA-256 från två sökvägar; `ops/verify-reproducible.sh` kör om beviset |
| Härkomst | Tolk, `uv` och modellvikter togs från byggmaskinens föränderliga cacher | Allt pinnat i `ops/pins.json` och SHA-256-verifierat före användning |
| Modellgräns | Vilket inloggat konto som helst kunde peka om modelltjänsten till vilken `http(s)`-adress som helst | Installationsadministratör krävs; endast loopback eller https mot eget privat nät accepteras |

Arkitekturen från XS-46 är oförändrad: Tauri 2, WebKitGTK, UI och API från
**samma** loopback-origin, tom `capabilities`, `withGlobalTauri: false`, inga
Tauri-plugins.

## Leveransens identitet

| | |
| --- | --- |
| Gren | `itsimonfredlingjack/xs-49-reparera-xs-47-reproducerbarhet-proveniens-och-modellgrans` |
| Commit som byggde och accepterades | `8d8dd73ca355fd5d445b50c2aa4613ff3a245744` |
| `dirty` | `false` |
| `deliveryTree` | `9c996ddfab4e0cb6d3ccb2bad01bc3739cd9e3dbd53f7b170bf559d6f78105ef` |
| Artefakt | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| SHA-256 | `f8ddb770d9fccf9a23525e4534fbc052edc92d28e14b29a2e16762d23f121887` |
| Storlek | 574 916 814 byte (548 MiB), 773 MiB installerat |
| RPM-header SHA-256 | `81ec457f5260c6ac8d28fb2f78eb65d8aa4ab92afb55f9b94dc8f8c3a12ae0f1` |
| `BUILDTIME` / `BUILDHOST` | `1785196800` (2026-07-28T00:00:00Z) / `reproducible.brfdokumentai.se` |
| Payload | zstd |
| Signering | ingen — se begränsning 2 |

### Commit-SHA och evidens i samma commit

Den commit som byggde artefakten och som acceptansen kördes mot är
`8d8dd73c…`, med ren arbetskatalog. **Leveranscommiten** — den enda commiten
ovanpå `823a3d75` — skiljer sig från den bara i filer *utanför*
`REPRO_DELIVERY_PATHS`: acceptansevidensen under `docs/evidence/` och
acceptansskriptets egen sökvägsmaskering i `backend/scripts/`.

Ingen commit kan innehålla sitt eget SHA — det vore en preimage. Konstruktionen
är därför gjord så att skillnaden inte spelar någon roll, och så att det går att
kontrollera:

* artefakten är en funktion av **leveranskällorna**, inte av commiten;
  `ops/lib/repro.sh` (`REPRO_DELIVERY_PATHS`) listar exakt vilka spårade
  sökvägar det är, och varken `docs/` eller `backend/scripts/` står på listan;
* därför är `deliveryTree` för leveranscommiten **samma** `9c996ddf…` som ovan;
* och därför ger ett ombygge från leveranscommiten samma
  `f8ddb770…` som acceptansen kördes mot:

```bash
git checkout <leveranscommit> && git status --porcelain   # tomt
make desktop-package
sha256sum dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
# f8ddb770d9fccf9a23525e4534fbc052edc92d28e14b29a2e16762d23f121887
```

Detta är inte en formalitet: samma egenskap demonstrerades oavsiktligt under
arbetet, där två *olika* commits med identisk `deliveryTree` gav bitidentiska
RPM-filer (`552d7893…`).

## Reproducerbarhet: två rena checkouter

```bash
ops/verify-reproducible.sh \
  /home/aidev/Projects/repro/a \
  /home/aidev/Projects/repro/brfv2-second-checkout-with-a-much-longer-path
```

Skriptet klonar båda checkouterna från repot, checkar ut samma commit, kör
`uv sync` + `npm ci`, bygger körmiljön och paketet i var och en, och jämför
resultaten med `cmp` och `sha256sum`.

| Checkout | SHA-256 |
| --- | --- |
| `/home/aidev/Projects/repro/a` | `f8ddb770d9fccf9a23525e4534fbc052edc92d28e14b29a2e16762d23f121887` |
| `/home/aidev/Projects/repro/brfv2-second-checkout-with-a-much-longer-path` | `f8ddb770d9fccf9a23525e4534fbc052edc92d28e14b29a2e16762d23f121887` |

**Byteidentiska** (`cmp -s` utan skillnad, 574 916 814 byte båda). Maskinläsbart
resultat i [`xs49-reproducibility.json`](xs49-reproducibility.json).

Sökvägarna ovan är medvetet olika långa och står i den här filen just för att de
*är* testet. Ingen annan evidensfil innehåller byggmaskinens kataloglayout.

### De fem orsakerna som åtgärdades

Detaljerna, inklusive varför byggepoken är fast i stället för hämtad ur
commiten, står i [adr/0003-reproducerbar-rpm.md](../adr/0003-reproducerbar-rpm.md).

1. Kompilerad bytekod bar checkoutens sökväg och källans mtime.
2. `CARGO_MANIFEST_DIR` bakades in i skalet av `tauri::generate_context!`,
   utom räckhåll för `--remap-path-prefix`.
3. `dist-info/RECORD` beskrev konsolskript som redan tagits bort, med en längd
   som berodde på byggsökvägen.
4. Tidsstämplar i payloaden och i RPM-headern kom från byggtillfället.
5. Vakten mot sökvägsläckage var skriven som `strings | grep -q` inuti ett `if`
   — SIGPIPE under `pipefail` gjorde den garanterat tyst. Efter rättningen
   fångade den omedelbart både checkoutens sökväg och 195 förekomster av
   byggarens hemkatalog.

## Pinnade byggindata

Allt hämtas av `ops/fetch_pinned.py`, som kontrollerar SHA-256 **innan** bytesen
används. En cachad fil används bara om hashen stämmer; annars kastas den och
hämtas om. Cachen är alltså en indata som verifieras, aldrig en auktoritet.

### CPython

| | |
| --- | --- |
| Version | 3.12.13 (`sys.version`: `3.12.13 (main, Jul 18 2026, 17:02:19) [Clang 22.1.3]`) |
| Utgåva | `astral-sh/python-build-standalone`, build `20260718`, `install_only_stripped` |
| Kanonisk källa | `https://github.com/astral-sh/python-build-standalone/releases/download/20260718/cpython-3.12.13%2B20260718-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` |
| Förväntad SHA-256 | `5854aa6ec71cad00334d5065633c210b2e7feb40956767a59a91791cadcf0b79` |
| Verifieras av | `ops/fetch_pinned.py python` — SHA-256 före uppackning |
| Kontroll mot testsviten | Bygget avbryter om den pinnade tolkens `sys.version` inte är identisk med `backend/.venv`s |

Resultat: hash matchade, och paketerad tolk = tolken `pytest` körde på.

### uv

| | |
| --- | --- |
| Version | 0.11.32 |
| Kanonisk källa | `https://github.com/astral-sh/uv/releases/download/0.11.32/uv-x86_64-unknown-linux-gnu.tar.gz` |
| Förväntad SHA-256 | `aab924fd522efd06f1c5f3b93a243864fc453132c94b2dc49f1371b528a4b967` |
| Verifieras av | `ops/fetch_pinned.py uv` — SHA-256 + `uv --version` mot pinnen |

Bygget använder den här binären, inte den `uv` som råkar ligga i `PATH`.

### Hjul

`uv export --frozen --no-dev --no-emit-project` ur `backend/uv.lock`
(SHA-256 `f0b3b31384ca27c35d38d1d88961469b65249fca8bb430dce4807185f3281f9f`),
installerade med `uv pip install --require-hashes`. Bygget avbryter om den
exporterade kravfilen saknar hashar.

### Embeddervikter

| | |
| --- | --- |
| Repo | `minishlab/potion-multilingual-128M` |
| Revision | `73908c3438cf03b6a01bcb9611d62b23d0726f08` (oföränderlig commit, inte `main`) |
| Källa | `https://huggingface.co/{repoId}/resolve/{revision}/{file}` |
| Verifieras av | `ops/fetch_pinned.py embedder` — SHA-256 + storlek per fil |

| Fil | Byte | SHA-256 |
| --- | --- | --- |
| `config.json` | 271 | `595e4cab2093732efd5dbe084fd5c1826b5eea693b73b4c1fd971672867d2e54` |
| `model.safetensors` | 512 361 560 | `14b5eb39cb4ce5666da8ad1f3dc6be4346e9b2d601c073302fa0a31bf7943397` |
| `modules.json` | 278 | `a68dcbed0429dcdd5bfdca92b0b03cc30d09122c0a3fcf4758787d4b244e45b2` |
| `special_tokens_map.json` | 167 | `d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7` |
| `tokenizer.json` | 18 616 131 | `19f1909063da3cfe3bd83a782381f040dccea475f4816de11116444a73e1b6a1` |
| `tokenizer_config.json` | 1 898 | `bd0e8c3a56aeac5078a6445e6b04425cd17b41bcc8d382ae925b5dbca287f8eb` |
| `vocab.txt` | 6 355 735 | `090a91cb4ec3969e9dd3bf9f0fb4bd88006a857737f4144c64acc03ed13db53b` |

Alla sju verifierade. Ingen fil utanför listan följer med, och den globala
Hugging Face-cachen läses inte längre som auktoritet — varken av bygget eller
av den installerade applikationen (`BRF_MODEL2VEC_PATH` pekar på bundlen och
`HF_HUB_OFFLINE=1`).

Hela manifestet finns i paketet, i
`/usr/lib/BRF Dokument-AI/runtime/BUNDLE.json` (`brfv2-desktop-bundle/v2`).

## Modellgränsen

Fullständigt beslut: [adr/0002-model-endpoint-boundary.md](../adr/0002-model-endpoint-boundary.md).
Maskinläsbart utfall: [`xs49-desktop-acceptance-installed.json`](xs49-desktop-acceptance-installed.json),
`securityBoundary`.

### Behörighet

| Kontroll | Resultat |
| --- | --- |
| Kontot som konfigurerade installationen | `installationAdmin: true` |
| Andra kontot (admin för **alla** föreningar på maskinen) | `installationAdmin: false` |
| `GET /api/desktop/model-runtime` som vanligt konto | `200` — proveniensen är läsbar |
| `PUT /api/desktop/model-runtime` som vanligt konto | `403` |
| `POST /api/desktop/model-runtime/test` som vanligt konto | `403` |
| Konfigurationen efter de nekade anropen | oförändrad (`http://127.0.0.1:8000/v1`) |

Det andra kontot skapades med **produktens egen** `AuthStore` ur den
installerade bundlen, inte med checkoutens kod.

### Destination

Policyn (`brfv2-model-endpoint-policy/v1`, default deny) serveras på
`GET /api/desktop/model-endpoint-policy` och i `/api/desktop/state`;
acceptansen kontrollerar att de är samma dokument (`servedMatchesState: true`).

| Klass | Värdar | Scheman |
| --- | --- | --- |
| `loopback` | `localhost`, `127.0.0.0/8`, `::1/128` | `http`, `https` |
| `private-network` | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7` | endast `https` |

Nekat i den **installerade** applikationen, som installationsadministratör:

| Adress | HTTP | `X-Model-Endpoint-Rejection` |
| --- | --- | --- |
| `https://api.openai.com/v1` | 422 | `hostname_not_allowed` |
| `https://api.anthropic.com/v1` | 422 | `hostname_not_allowed` |
| `https://8.8.8.8/v1` | 422 | `address_not_self_hosted` |
| `http://192.168.13.13:8000/v1` | 422 | `plaintext_off_host` |
| `http://169.254.169.254/latest/meta-data` | 422 | `link_local_address` |
| `file:///etc/passwd` | 422 | `scheme_not_allowed` |

Den godkända endpointen fortsatte fungera efteråt (`deploymentClass: loopback`,
verklig `/v1/models`-probe `ok: true`).

### Handredigerad konfigurationsfil

`desktop-config.json` skrevs om till `https://api.openai.com/v1` och
applikationen startades om:

| | |
| --- | --- |
| `modelRuntime.configured` | `false` |
| `llm.provider` | `none` |
| `llm.ready` | `false` |

Efter att filen återställts kom installationen tillbaka till
`provider: selfhosted`, `ready: true`. En adress som policyn nekar sätts alltså
inte i kraft ens när den redan ligger på disk.

## Installerad acceptans

Kommandon:

```bash
make desktop-package
sudo dnf install -y dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
make desktop-acceptance-installed RPM=dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
```

Journeyn kör mot `/usr/bin/brfv2-desktop` i ett eget `XDG_DATA_HOME`, så varje
körning börjar från en genuint okonfigurerad maskin och operatörens riktiga
installation rörs aldrig. Genereringen är verklig — skriptet vägrar starta om
modelltjänsten inte svarar. Total körtid 129,2 s.

Artefaktidentitet i evidensen (`applicationIdentity`):

| | |
| --- | --- |
| `/usr/bin/brfv2-desktop` SHA-256 | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` |
| Installerat paket | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| `rpm --verify` | exitkod 0, inga skillnader |
| Testad artefakt | `f8ddb770…` (samma fil som paketeringen producerade) |

| Steg | Kontroll | Resultat |
| --- | --- | --- |
| Förstagångskonfiguration | Uppstartsdialog, inget inloggningsformulär; konto + förening skapas i appen | PASS — [skärmbild](xs49-desktop-setup.png) |
| Modelltjänst | Adress angiven i appen, verklig `/v1/models`-probe, `provider=selfhosted` | PASS |
| En förening = statiskt namn | Ingen påhittad enval-dropdown | PASS |
| Uppladdning + ingestion | Riktig `<input type=file>`-väg, PDF indexerad på 0,3 s | PASS — [skärmbild](xs49-desktop-documents.png) |
| Underbyggt svar | Riktig Gemma 4 12B: "Styrelsen har sitt säte i Göteborgs kommun." | PASS |
| Citat | Ett verifierat citat med källa och sida | PASS |
| PDF-markering | Rätt sida (1 av 3), synlig highlight-rect | PASS — [skärmbild](xs49-desktop-answer-highlight.png) |
| Zoom | 100 % → 110 % | PASS |
| Vägran | Källfrämmande fråga → `OTILLRÄCKLIGT UNDERLAG`, 0 citationer | PASS — [skärmbild](xs49-desktop-refusal.png) |
| CSP-nekande | `securitypolicyviolation`: `connect-src` blockerade sidans egen förfrågan till `http://127.0.0.1:8000/v1/models` — samma tjänst backend just använt | PASS |
| Origin | Exakt host 200, främmande host 403 | PASS |
| IPC-nekande | `Command plugin:window|set_title not allowed by ACL`; `window.__TAURI__` är `undefined` | PASS |
| Cookie | HttpOnly, `Path=/api/`, SameSite=Lax, installationsspecifikt namn | PASS |
| Inga runtimefel i webviewen | `window.onerror` + `unhandledrejection` under hela resan | `[]` |
| Säkerhetskopiering | Skapad från UI:t och listad | PASS — [skärmbild](xs49-desktop-settings.png) |
| Återställning | Förberedd, applicerad vid start; avvikelsen `brf-efter-kopian` bortrullad | PASS |
| Omstart | Backend-exit **86** → skalet startar om appen | PASS |
| Bevarat tillstånd | Identitet, föreningar, dokument och modellkonfiguration kvar | PASS |
| Ren nedstängning | Port stängd, 0 kvarvarande processer | PASS |
| Abrupt avslut (SIGKILL) | Port stängd, 0 föräldralösa backends | PASS |
| Barnprocess dör | Skalet stannar kvar och förklarar; backend-logg skriven; 0 föräldralösa | PASS |
| Processgrupp | SIGTERM till hela gruppen vid avslut; `PR_SET_PDEATHSIG` vid abrupt död | PASS — se begränsning 6 |
| Modelltjänst nere | `provider_error`-vägran utan citationer, inget påhittat svar | PASS |
| Kompakt fönster | 1000×700 utan horisontell overflow | PASS |
| Modellgräns | Se avsnittet ovan | PASS |

Journeyn mot **release-bygget i checkouten**
([`xs49-desktop-acceptance.json`](xs49-desktop-acceptance.json)) kördes också.
Den täcker dessutom felfönstret vid trasig installation
([skärmbild](xs49-desktop-startup-failure.png)), vilket kräver att inget paket
är installerat och därför hoppas över i den installerade körningen.

## Miljö

| Del | Verifierad version |
| --- | --- |
| OS | Fedora 44, kernel `7.1.5-200.fc44.x86_64` |
| Session | `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE` |
| Rust | `rustc 1.97.1`, `cargo 1.97.1` |
| Tauri | `tauri = 2.11.5`, `tauri-build = 2.6.3` (exakt låsta) |
| Webview | `webkit2gtk4.1-2.52.5-1.fc44`, `gtk3-3.24.52-2.fc44` |
| OCR | `tesseract-5.5.2-1.fc44`, `tesseract-langpack-swe-4.1.0-12.fc44` |
| Node | `v22.22.2`, npm `10.9.7` |
| Paketering | `rpmbuild 6.0.2`, zstd-payload |
| Körmiljö i paketet | CPython 3.12.13+20260718, `model2vec:potion-multilingual-128M`@`73908c34…` |
| Modelltjänst | Gemma 4 12B (`gemma-4-12b-it-UD-Q4_K_XL.gguf`) på `agenntserver`, nådd via SSH-forward |

## Verifieringssvit

| Kommando | Utfall |
| --- | --- |
| `backend/.venv/bin/pytest -q backend/tests` | **604 passed, 3 skipped** (XS-47: 565) |
| `make test-isolation` | 48 passed |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 5 passed (XS-47: 4) |
| `cd brfv2-mockup && npm run lint` | 0 fel |
| `cd brfv2-mockup && npm test` | 21 passed (XS-47: 19) |
| `cd brfv2-mockup && npm run test:e2e` | 11 passed |
| `cd brfv2-mockup && npm run build` | OK |
| `make desktop-build` | OK |
| `make desktop-package` | OK — `f8ddb770…` |
| `make desktop-acceptance` | PASS |
| `make desktop-acceptance-installed` | PASS |
| `ops/verify-reproducible.sh` | IDENTISKA |

De nya testerna: 29 i `backend/tests/test_model_endpoint.py` (policyn), 7 i
`backend/tests/test_desktop.py` (behörighet, installerad policykontroll,
handredigerad konfigurationsfil, adoption vid återställd backup), 2 i
`brfv2-mockup/src/App.test.jsx` (gränssnittet ljuger inte om vem som får ändra),
1 i `src-tauri/src/main.rs`.

Typkontroll: projektet har ingen (`backend` kör utan mypy, frontenden är JSX
utan TypeScript). Det är oförändrat sedan XS-47 och står här för att frånvaron
ska vara uttalad snarare än underförstådd.

## Kvarstående begränsningar

1. **Reproducerbarheten är visad på samma Fedora-version.** `%{dist}`-makrot
   (`.fc44`) kommer från byggdistributionen och ingår medvetet i artefaktens
   identitet. Byggen tvärs över distributioner är inte testade.
2. **Paketet är osignerat.** `dnf install` varnar om saknad OpenPGP-kontroll.
   Signering kräver en nyckel och en distributionskanal som inte finns ännu.
3. **Uppgraderingsvägen är inte testad.** Bara version 0.2.0 finns; en
   `dnf upgrade` från en tidigare version har aldrig körts.
4. **Storleken är 548 MiB komprimerad, 773 MiB installerad.** 513 MiB är
   embeddervikterna i float32. Kvantisering skulle halvera paketet men ändra
   retrievalvektorerna och kräver egen utvärdering mot golden set.
5. **Fysisk tangentbordsautomation är fortfarande blockerad** i den här
   KWin/WebKit-miljön. Applikationens verkliga `keydown Enter`-väg körs i
   webviewen; en mänsklig tangentbordssmoke bör göras i en manuell releasecheck.
6. **Tauris omstart spawnar en ny process i stället för `exec`.** Efter en
   återställningsomstart kör appen under ett nytt pid i samma processgrupp
   (`restartRespawnsUnderANewPid: true`). En operatör som dödar det pid hen
   startade stoppar alltså inte appen — signalera processgruppen.
7. **Den lokala tillitsgränsen är fortfarande OS-användaren.** Modellgränsen som
   repareras här är produktens egen: vilka destinationer den kan förmås att
   kontakta och vem som kan förmå den. En process som redan kör som samma
   Unix-användare kan läsa användarens appdata direkt.
8. **Ingen användarhantering i produkten.** Installationsadministratör ges vid
   första start och kan inte delas ut i gränssnittet. Acceptansen skapar det
   andra kontot direkt i produktens egen `AuthStore` — det är så ett extra konto
   ser ut på en verklig installation i dag.
9. **`brfv2-mockup/`s orealiserade ytor** (global sök, dokumentchatt,
   kvalitetskontroll, bevakningar) är fortsatt onåbara och märkta i UI:t, med en
   e2e-test som vaktar det. De är kvar som död kod i `App.jsx`.
10. **Backup är lokal.** Säkerhetskopior hamnar bredvid datakatalogen; att
    kopiera dem till annan media är användarens ansvar och står i gränssnittet.

## Nästa steg

En **ny oberoende BP2-granskning**. Den här leveransen är en kandidat; inget i
det här dokumentet är ett gate-beslut.
