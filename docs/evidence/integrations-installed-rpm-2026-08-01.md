# Installerad RPM, byggd från integrationsgrenen — acceptans 2026-08-01

Backloggens punkt 1: *"Kör om desktopacceptansen mot en RPM byggd från den här
grenen. Snittet är idag verifierat genom desktopadaptern med TestClient, inte
mot ett installerat paket."*

Den här körningen stänger den. Ingenting nedan är simulerat: applikationen är
den installerade binären, generationen går mot den självhostade Gemma 4 12B, och
maskinens utgångsläge är genuint oprovisionerat (isolerad `XDG_DATA_HOME` /
`XDG_CONFIG_HOME`).

## Artefakten

| | |
| -- | -- |
| Commit | `f0e8be1` på `feat/desktop-styrelsearbetsyta` |
| Paket | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm`, 574 798 945 byte |
| SHA-256 | `a06233fad466226d893d78b6dc88748c5910867daa99280a79d40c2dc5ca94d7` |
| Installerad som | `/usr/bin/brfv2-desktop` (`sudo dnf reinstall`) |
| Värd | Fedora 44, KDE/Wayland |

`rpm -V brf-dokument-ai` rapporterar inga avvikelser: filerna på disk är
paketets.

Bygget vägrade först, och det är värt att notera som en egenskap snarare än ett
hinder: `ops/package-desktop.sh` avbryter på en smutsig arbetskatalog, och
`ops/build-runtime.sh` stämplar körmiljön med sin härkomst — så en körmiljö
stegad före commiten kunde inte paketeras efteråt. Artefakten identifieras av
sin commit, eller inte alls.

## Payload-granskningen

```
BRFV2_REQUIRE_ARTIFACT=1 BRFV2_RPM=dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  backend/.venv/bin/pytest -q backend/tests/test_desktop_artifact.py
→ 40 passed
```

Reglerna i `ops/forbidden_providers.json` prövas mot det byggda paketet:
distributioner, moduler, attribut, sökvägar, entry points, provideridentiteter
och valbara nycklar. De nya integrationsmodulerna drar inte in någon förbjuden
leverantör — `httpx` fanns redan i nyttolasten för den självhostade
modellklienten, och integrationerna använder samma.

## Acceptansen

```
backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
  --application /usr/bin/brfv2-desktop \
  --artifact dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  --run-label integrations-installed
→ exit 0, 132,2 sekunder
```

Evidens: [`integrations-installed-desktop-acceptance.json`](integrations-installed-desktop-acceptance.json)
och de fem skärmbilderna bredvid.

Modelltjänsten som svarade:
`http://127.0.0.1:8000/v1` → `gemma-4-12b-it-UD-Q4_K_XL.gguf` (SSH-tunnel till
`agenntserver`).

### Vad som prövades

* **Första start.** Uppstartsdialogen på en oprovisionerad maskin: förening,
  administratörskonto, modelltjänstens adress.
* **Grundat svar.** "Var har styrelsen sitt säte?" → *"Styrelsen har sitt säte i
  Göteborgs kommun."* med ett citat ur `Stadgar Brf Gjutformen 12.pdf` s. 1, och
  markeringen placerad på sidan (rect 600,0 × 313,3, 101,1 × 13,7 pt).
  Proveniensen under svaret läser **Gemma 4 12B · Self-hosted**.
* **Vägran.** Frågan utan täckning i korpusen avvisas i stället för att gissas.
* **Säkerhetsgränsen.** Sidans skript når inte modelltjänsten — försöket
  blockeras av `connect-src` i CSP:n, vilket är rätt: modellanropet är
  backendens, inte gränssnittets. `window.__TAURI__` är `undefined`, och ett
  IPC-anrop utifrån avvisas av ACL:n (`Command plugin:window|set_title not
  allowed by ACL`). Sex otillåtna modelladresser avvisas med 422.
* **Livscykel.** Ren nedstängning, abrupt död (backendens PID dödad: porten
  stängs, loggen finns kvar, skalet står kvar och förklarar, noll föräldralösa
  processer), backup och återställning, och kvarhållet tillstånd över omstart.
* **Modelltjänst som inte svarar.** Applikationen startar ändå och säger det
  rakt ut i stället för att fallera.

### Vad som inte prövades här, och varför

Acceptansen kör den **verifierade produktslingan** — inloggning, förening,
dokument, fråga, svar, citat, markering — plus livscykel och säkerhetsgräns.
Den startar inte en Microsoft- eller Fortnox-inloggning, av två skäl som båda är
avsiktliga:

1. En device code-inloggning kräver att en människa öppnar en webbläsare, skriver
   en kod och godkänner. Det är inte automatiserbart, och att fejka det i
   acceptansen vore att bevisa att stubben fungerar.
2. Integrationsvägarna är i stället prövade genom en **injicerad transport** som
   kräver exakt rätt URL, metod, huvuden och formfält, och som vägrar allt annat
   — 65 tester i `test_integrations_live.py` och
   `test_integrations_connections_http.py`. Det är strängare än ett verkligt
   anrop mot en förlåtande server, men det är inte samma sak som ett riktigt
   anrop, och det sägs som det är.

Vad som **är** bevisat om integrationerna i det installerade paketet: rutterna
finns (desktopappen byggs på samma `create_app`), payload-granskningen är grön
med dem, och en nyinstallerad applikation gör ingen utgående trafik alls förrän
någon konfigurerar och loggar in.
