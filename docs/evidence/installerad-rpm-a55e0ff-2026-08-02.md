# Installerad RPM från `a55e0ff` — acceptans 2026-08-02

Sammanslagningen av uppgiftsdomänen flyttade `main` förbi den artefakt som
verifierats dagen innan. Det här bygget stänger det gapet direkt i stället för
att låta det stå öppet.

**Att paketet motsvarar `main` är kontrollerat, inte påstått.** Artefakten
byggdes ur `a55e0ff`; den här evidensen är ett dokument-only-tillägg som gör
`main` till `e91b2b3`. Bygget identifierar sig med *delivery tree*-hashen och
inte med commiten, just för att dokumentation och acceptansevidens ligger i
samma commit som leveransen och inte får kunna flytta artefaktens bytes
(`ops/lib/repro.sh`, `REPRO_DELIVERY_PATHS`). Den hash som ligger inbakad i det
byggda paketets `BUNDLE.json` är

```
b92ed5d0820ba461a720d490b1e14a681c18607ae5654d2a1d93edded65ef8c0
```

och samma hash räknas fram ur **båda** commitarna:

```
$ git ls-tree -r a55e0ff -- "${REPRO_DELIVERY_PATHS[@]}" | sha256sum
b92ed5d0820ba461a720d490b1e14a681c18607ae5654d2a1d93edded65ef8c0
$ git ls-tree -r e91b2b3 -- "${REPRO_DELIVERY_PATHS[@]}" | sha256sum
b92ed5d0820ba461a720d490b1e14a681c18607ae5654d2a1d93edded65ef8c0
```

Paketet är alltså den nuvarande produkten på `main`, och skillnaden mellan de
två commitarna är bevisligen inte i leveransen.

Körningen prövar dessutom hela kedjan i ett svep, i den installerade
applikationen: ett avtal läses → en frist räknas fram → en människa godkänner
den → skyldigheten blir någons jobb, med bevisen kvar hela vägen.

## Artefakten

| | |
| -- | -- |
| Commit | `a55e0ff` (main), utcheckad rent i en egen worktree |
| Paket | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| Storlek | 574 860 579 byte |
| SHA-256 | `1bd4080581831ad945800996af8471860c1ed8a12f6f1066ca8a96e04097bb59` |
| Installerad som | `/usr/bin/brfv2-desktop` (`sudo dnf reinstall`) |
| Värd | Fedora 44, KDE/Wayland |

Tidigare artefakter: `40857ba1…` (`5337eec`, före uppgifterna) och `a06233fa…`
(`f0e8be1`, före bevakningarna). Båda är därmed ersatta.

`rpm -V brf-dokument-ai` rapporterar inga avvikelser. Uppgiftsdomänen ligger i
paketet: `/usr/lib/BRF Dokument-AI/runtime/backend/app/tasks/{models,store,routes}.py`.

Till skillnad från förra gången behövde ingenting stashas undan före
paketeringen: acceptansens nya steg är committat och ingår i `a55e0ff`, så
artefakten och testharnesset kommer ur samma commit.

## Payload-policyn

```
BRFV2_REQUIRE_ARTIFACT=1 BRFV2_RPM=dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  backend/.venv/bin/pytest -q backend/tests/test_desktop_artifact.py
→ 40 passed
```

## Acceptansen

```
backend/scripts/desktop_acceptance.py \
  --application /usr/bin/brfv2-desktop \
  --artifact dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  --run-label uppgifter-installed
→ exit 0, 121,8 sekunder
```

Evidens: [`uppgifter-installed-desktop-acceptance.json`](uppgifter-installed-desktop-acceptance.json)
och sju skärmbilder. Generation gick mot `gemma-4-12b-it-UD-Q4_K_XL.gguf` på
`agenntserver`. Utgångsläget var genuint oprovisionerat.

### Kedjan, i det installerade paketet

**1. Avtalet läses.** Ett serviceavtal laddas upp och paketets egen motor läser
det:

> "Avtalet gäller från och med den 1 februari 2026 **till och med den 31 januari
> 2028**. … Avtalet får sägas upp skriftligen senast **sex månader** före
> avtalstidens utgång."

**2. Fristen räknas fram och godkänns.**

| | |
| -- | -- |
| Förslag | 1 |
| Rubrik | Säg upp eller ompröva avtalet senast **2027-07-31** |
| Uträkning på skärmen | avtalstidens utgång 2028-01-31 enligt citerad avtalstid 2026-02-01 – 2028-01-31, minus 6 månader |
| Efter godkännande | hink **Senare**, ansvarig **Karin Lindqvist** |
| Kvarvarande förslag | **0** |

**3. Skyldigheten blir arbete.** Uppgiften skapas från bevakningskortet och
kontrolleras på Uppgifter-vyn:

| | |
| -- | -- |
| Skapad från | `watch` |
| Ansvarig | **Jonas Berg** |
| Citat som följde med | 1 |
| Händelser i historiken | 1 (`created`) |
| Aktiva uppgifter | 1 |

Uppgiften får medvetet en **annan** ansvarig än bevakningen. Samma namn hade
inte kunnat skilja "namnet kom från formuläret" från "namnet ärvdes", och det är
just den skillnaden steget finns för att pröva.

Skärmbilden visar dessutom det som inte går att påstå i en JSON: ursprunget
utskrivet som *Bevakning — Säg upp eller ompröva avtalet senast 2027-07-31*,
källdokumentet, och avtalsklausulen citerad ordagrant på kortet.

### Resten av resan, oförändrad

Första start på oprovisionerad maskin · grundat svar med citat och markering,
proveniens **Gemma 4 12B · Self-hosted** · vägran utan citat · säkerhetsgränsen
(CSP, `window.__TAURI__` undefined, IPC nekat av ACL, sex otillåtna
modelladresser avvisade med 422) · ren nedstängning, abrupt död, backup och
återställning, kvarhållet tillstånd över omstart · modelltjänst som inte svarar.

## Vad det här inte bevisar

Ingen Microsoft- eller Fortnox-inloggning sker i acceptansen; ett device
code-flöde kräver en människa med en webbläsare. Liveintegrationerna är prövade
genom en injicerad transport som kräver exakt rätt begäran — strängare än ett
verkligt anrop mot en förlåtande server, men inte samma sak, och det sägs som
det är.

En nyinstallerad applikation gör ingen utgående trafik alls förrän någon
konfigurerar och loggar in.
