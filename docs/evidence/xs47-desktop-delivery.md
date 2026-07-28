# XS-47 — Distribuerbar skrivbordsleverans för Fedora

> **Ersatt av [XS-49](xs49-desktop-delivery.md).** BP2-granskningen returnerade
> den här leveransen. Tre saker i dokumentet nedan håller inte: acceptansens
> JSON-filer var genererade från en **annan commit och en smutsig checkout**
> (de är därför borttagna, inte omdöpta), RPM:en gick **inte** att reproducera
> — SHA-256 `b0b1a90a…` gäller ett bygge som inte kan återskapas — och
> avsnittet "Säkerhetsgräns" beskrev en självhostad gräns som implementationen
> inte upprätthöll. Texten står kvar som historik över vad XS-47 faktiskt
> levererade; den gällande leveransen och dess evidens är XS-49.

Datum: 2026-07-28
Föregås av: [XS-46 — Tauri 2 på Fedora/KDE/Wayland](xs46-tauri-fedora.md) (arkitekturbevis)

## Vad som ändrades i förhållande till spiken

XS-46 bevisade att arkitekturen bär. XS-47 gör den till en produkt som går att
installera och använda. Fyra saker i spiken höll inte för det.

| Spikens beteende | Varför det inte kunde levereras | Nu |
| --- | --- | --- |
| `BRF_LLM=scripted` som default | En scriptad leverantör är simulerad funktionalitet. När den togs bort valde `pick_provider()`s `auto`-väg **`claude-cli`** — installationen hade skickat föreningens dokument dit den startande sessionen råkade peka. | `BRF_LLM=selfhosted` är fastnaglat. Utan konfigurerad adress är leverantören `none` och appen säger det. |
| `--seed-demo` med `max@demo.se / max-demo-2026` | Demokonton i en distribuerad produkt är både en säkerhetsrisk och en osanning. | Produkten levereras utan konton. Första start konfigureras i appen; `backend/scripts/` finns inte ens i bundlen. |
| `backend/.venv` + HF-cache i checkouten | Fungerar bara på byggmaskinen. | Paketerad CPython 3.12.13 med hash-låsta hjul och medföljande embeddervikter. |
| `BRF_MODE` ärvdes (default `dev`) | `dev` exponerar `/api/reset`, som raderar alla föreningar. | `BRF_MODE=desktop`: `/api/reset` är av, och pilotlägets startspärr gäller inte (en installerad app måste kunna starta och *förklara* en saknad modelltjänst). |

## Miljö

| Del | Verifierad version |
| --- | --- |
| OS | Fedora 44, kernel `7.1.5-200.fc44.x86_64` |
| Session | `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE` |
| Rust / Tauri | `rustc 1.97.1`, `tauri = 2.11.5`, `tauri-build = 2.6.3` (exakt låsta) |
| Webview | `webkit2gtk4.1 2.52.5`, GTK 3 `3.24.52` |
| Paketering | `rpmbuild 6.0.2` (Fedoras egen), zstd-payload |
| Modelltjänst | Gemma 4 12B (`gemma-4-12b-it-UD-Q4_K_XL.gguf`) på `agenntserver`, nådd via SSH-forward |
| Körmiljö i paketet | CPython 3.12.13 (samma uv-hanterade tolk som testsviten), `model2vec:potion-multilingual-128M` |

## Distributionsartefakt

| | |
| --- | --- |
| Sökväg | `dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` (bygg-output, inte spårad i git) |
| Storlek | 573,735,176 byte (547 MiB) |
| SHA-256 | `b0b1a90a8bd6df05b2e3b040a128b4167ae0f94464c58864750680eb74923ed0` |
| Installerat paket | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| Installerad storlek | 769 MiB under `/usr/lib/BRF Dokument-AI/` |
| Payload | zstd (`rpmlib(PayloadIsZstd)`) |
| Signering | ingen — se begränsning 2 |

Artefakten återskapas från de spårade källorna med `make desktop-package`;
den checkas medvetet inte in (se `.gitignore`).

### Kommandon som gav den här evidensen

```bash
make desktop-package                     # -> dist/*.rpm  (~55 s efter stegad körmiljö)
sudo dnf install dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm

# Full journey mot RELEASE-BYGGET i checkouten (täcker även felfönstret,
# vilket kräver att inget paket är installerat):
sudo dnf remove -y brf-dokument-ai
backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
  --output docs/evidence/xs47-desktop-acceptance.json

# Full journey mot det INSTALLERADE paketet:
make desktop-install
backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
  --application /usr/bin/brfv2-desktop \
  --output docs/evidence/xs47-desktop-acceptance-installed.json

sha256sum dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
rpm -q brf-dokument-ai
```

Acceptansens JSON skriver ut körlokala sökvägar som stabila platshållare
(`~` och `<isolated-xdg-home>`) — byggmaskinens kataloglayout hör inte hemma i
en delad evidensfil. Inget annat skrivs om.

Beroenden som paketet självt kräver — inget annat:

```
gtk3  tesseract  tesseract-langpack-swe  webkit2gtk4.1
```

Installerad layout:

```
/usr/bin/brfv2-desktop
/usr/lib/BRF Dokument-AI/runtime/{python,backend,models}
/usr/lib/BRF Dokument-AI/ui/
/usr/share/applications/BRF Dokument-AI.desktop      (desktop-file-validate: OK)
/usr/share/icons/hicolor/{32x32,128x128,256x256}/apps/brfv2-desktop.png
```

Användardata ligger utanför paketet, i `~/.local/share/se.brfdokumentai.desktop/`
(`0700`), och överlever av- och ominstallation.

### Varför rpmbuild och inte Tauris RPM-bundler

Tauris bundler stegade trädet korrekt men **blev aldrig klar** med den här
payloaden: 27 minuters CPU i ett försök med standard-gzip och ett med
konfigurerad zstd, båda avbrutna utan artefakt. Att komprimera samma bytes med
systemets egen kompressor tar sekunder (`zstd -10` på de 512 MB vikterna: 1,9 s),
så kostnaden ligger inte i komprimeringen. `rpmbuild` packar identiskt träd på
**55 sekunder**, är den inbyggda paketeraren på måldistributionen och låter
payload-kompressorn väljas explicit. Tauri bygger fortfarande binären och äger
fönster- och assetsidan; bara packningen är vår.

## Journeyn som faktiskt kördes

`make desktop-acceptance-installed` driver den **installerade** applikationen
(`/usr/bin/brfv2-desktop`) genom hela flödet. Körningen sker i ett eget
`XDG_DATA_HOME`, så varje körning startar från en genuint okonfigurerad maskin
och operatörens riktiga installation rörs aldrig. Genereringen är verklig:
skriptet vägrar starta om modelltjänsten inte svarar.

Full maskinläsbar utdata:
[`xs47-desktop-acceptance-installed.json`](xs47-desktop-acceptance-installed.json)
(installerat paket) och
[`xs47-desktop-acceptance.json`](xs47-desktop-acceptance.json) (release-bygget i
checkouten, som dessutom täcker felfönstret vid en trasig installation — det
steget hoppas över när ett fungerande paket är installerat).

| Steg | Kontroll | Resultat |
| --- | --- | --- |
| Start från applikationsmenyn | `gio launch` av `.desktop`-posten, utan terminal | Fönster i KWin, `tty=?`, backend från `/usr/lib/BRF Dokument-AI/runtime/python`, logg skriven — [skärmbild](xs47-desktop-menu-launch.png) |
| Start | Slumpport, maskinläsbart readiness-kontrakt, samma origin för UI och API | PASS |
| Första körning | Ingen inloggningsruta — uppstartsdialog; `max@demo.se` fungerar inte | PASS |
| Konto + förening | Skapas i appen, ägaren blir admin | PASS |
| En förening = statiskt namn | Ingen påhittad enval-dropdown | PASS |
| Modelltjänst | Adress angiven i appen, verklig `/v1/models`-probe, `provider=selfhosted` | PASS |
| Andra föreningen + byte | Skapad i appen, växling fram och tillbaka | PASS |
| Uppladdning + ingestion | Riktig `<input type=file>`-väg, PDF indexerad | PASS |
| Underbyggt svar | Riktig Gemma 4 12B, exakt citat | PASS |
| Citation → PDF | Rätt sida, synlig highlight-rect | PASS |
| Zoom | 100 % → 110 % | PASS |
| Vägran | Källfrämmande fråga, noll citationer | PASS |
| Säkerhetskopia från UI | Skapad och listad | PASS |
| Omstart | Backend-exit 86 → skalet startar om appen | PASS |
| Bevarat tillstånd | Identitet, föreningar, dokument och modellkonfiguration kvar | PASS |
| Återställning | Förberedd, applicerad vid start, avvikelse bortrullad | PASS |
| Ren nedstängning | Port stängd, noll kvarvarande processer | PASS |
| Abrupt avslut (SIGKILL) | Port stängd, noll föräldralösa backends | PASS |
| Modelltjänst nere | `provider_error`-vägran utan citationer, inget påhittat svar | PASS |
| Backend dör | Skalet stannar kvar och förklarar; logg skriven | PASS |
| Kompakt fönster | 1000×700 utan horisontell overflow | PASS |
| CSP och origin | `default-src 'none'`, exakt host 200 / främmande host 403 | PASS |
| Sidan kan inte nå modelltjänsten direkt | `securitypolicyviolation`: `connect-src` blockerade `http://127.0.0.1:8000/v1/models` — samma tjänst appens backend just använt | PASS |
| Inga runtimefel i webviewen | `window.onerror` + `unhandledrejection` under hela resan | `[]` |
| Tauri-IPC från HTTP-sidan | `Command plugin:window|set_title not allowed by ACL` | PASS |
| Cookie | HttpOnly, `Path=/api/`, SameSite=Lax, installationsspecifikt namn | PASS |

### Visuell evidens

- [Uppstartsdialog steg 2 — modelltjänst](xs47-desktop-setup.png)
- [Dokument uppladdat och indexerat](xs47-desktop-documents.png)
- [Svar med citation och exakt PDF-markering](xs47-desktop-answer-highlight.png)
- [Vägran utan citationer, bredvid det underbyggda svaret](xs47-desktop-refusal.png)
- [Appinställningar: modelltjänst och säkerhetskopior](xs47-desktop-settings.png)
- [Felfönster när applikationen inte kan starta](xs47-desktop-startup-failure.png)
- [Startad från KDE:s applikationsmeny, utan terminal](xs47-desktop-menu-launch.png)

## Säkerhetsgräns

Oförändrad från XS-46 där den redan var bevisad, och skärpt på tre punkter.

* **Ingen Tauri-IPC mot HTTP-sidan.** `capabilities` är fortfarande tom,
  `withGlobalTauri` är `false` och **inga plugins är installerade**. Omstarten
  efter en förberedd återställning löses genom backendens exitkod (86) i stället
  för att öppna en IPC-yta — den kanalen fanns redan i processgränsen.
* **Felfönstret är en lokal bundlad asset** (`tauri://localhost`) under en egen
  strikt CSP, inte något som hämtas.
* **Ingen väg till en tredjepartsmodell.** `BRF_LLM` är fastnaglat till
  `selfhosted`, och `anthropic` — den enda andra nätverks-LLM-klienten i
  beroendeträdet — finns inte i bundlen. Bygget avbryter om paketet ändå går
  att importera.
* **Modellens åtkomsttoken** lagras `0600` och returneras aldrig till
  gränssnittet; ett oautentiserat `/api/desktop/state` avslöjar inte ens
  adressen.

Den lokala tillitsgränsen är fortfarande OS-användaren: en process som redan kör
som samma Unix-användare kan läsa användarens appdata. Multi-user-synk och
starkare lokal processisolering ligger utanför den här leveransen.

## Övriga sviter

```
backend/.venv/bin/pytest -q backend/tests        565 passed, 3 skipped  (XS-46: 544)
cargo test --locked --manifest-path src-tauri/    4 passed
cd brfv2-mockup && npm run lint                    0 fel
cd brfv2-mockup && npm test                       19 passed  (XS-46: 14)
cd brfv2-mockup && npm run test:e2e               11 passed
cd brfv2-mockup && npm run build                   OK
git diff --check                                   rent
```

De 21 nya backendtesterna och de 5 nya frontendtesterna täcker
förstagångskonfiguration, den fastnaglade självhostade leverantören,
säkerhetskopiering/återställning inklusive avvisade arkiv, och att
`/api/desktop/state` varken laddar embeddern eller läcker modelladressen.

## Kvarstående begränsningar

1. **Uppgraderingsvägen är inte testad.** Bara version 0.2.0 finns; en
   `dnf upgrade` från en tidigare version har aldrig körts. Datakatalogen är
   versionsmärkt (`schemaVersion` i `desktop-config.json`) men ingen migration
   har behövt köras än.
2. **Paketet är osignerat.** `dnf install` varnar om saknad OpenPGP-kontroll.
   Signering kräver en nyckel och en distributionskanal som inte finns ännu.
3. **Storleken är 547 MiB komprimerad, 769 MiB installerad.** 513 MiB av det
   är embeddervikterna i float32. Att kvantisera dem skulle halvera paketet men
   ändra retrievalvektorerna, vilket kräver egen utvärdering mot golden set.
4. **Fysisk tangentbordsautomation är fortfarande blockerad** i den här
   KWin/WebKit-miljön (oförändrat från XS-46). Applikationens verkliga
   `keydown Enter`-väg körs i webviewen; en mänsklig tangentbordssmoke bör
   fortfarande göras i en manuell releasecheck.
5. **`fetch()` mot en CSP-blockerad adress går inte att observera via
   WebKitWebDriver** — den blockerade förfrågan rapporteras som ett skriptfel
   som inte kan fångas i sidan. Acceptansen använder därför `XMLHttpRequest`,
   som ger ett fångbart `onerror` plus själva `securitypolicyviolation`-posten.
   Skillnaden är metodologisk, inte en produktbegränsning.
6. **Tauris omstart spawnar en ny process i stället för `exec`.** Efter en
   återställningsomstart kör appen under ett nytt pid i samma processgrupp,
   omadopterad av init. Det fungerar för en skrivbordsstart, men en operatör som
   dödar det pid hen startade stoppar inte appen — signalera processgruppen.
7. **`brfv2-mockup/`s orealiserade ytor** (global sök, dokumentchatt,
   kvalitetskontroll, bevakningar) är fortsatt onåbara och märkta i UI:t, och en
   e2e-test vaktar det. De är dock kvar som död kod i `App.jsx` och bör städas
   separat.
8. **Backup är lokal.** Säkerhetskopior hamnar bredvid datakatalogen; att
   kopiera dem till annan media är användarens ansvar och står i gränssnittet.
   Ingen schemalagd eller extern backup ingår.
