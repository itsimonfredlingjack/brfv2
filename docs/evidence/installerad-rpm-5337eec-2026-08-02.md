# Installerad RPM från `5337eec` — acceptans 2026-08-02

Den tidigare artefakten byggdes före bevakningsfunktionen. Den här körningen
gör den nuvarande produkten till en installerbar app och prövar den som en
sådan — inklusive Bevakningar, som annars bara hade varit "med i paketet"
snarare än "fungerar i paketet". Det är två olika påståenden och bara det andra
är värt något.

## Artefakten

| | |
| -- | -- |
| Commit | `5337eec` (main), utcheckad rent i en egen worktree |
| Paket | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| Storlek | 574 850 371 byte |
| SHA-256 | `40857ba1b900da1b877479f2d3df5c400be9beed7fbf8776d44604023fad15ab` |
| Installerad som | `/usr/bin/brfv2-desktop` (`sudo dnf reinstall`) |
| Värd | Fedora 44, KDE/Wayland |

Föregående artefakt, för jämförelse: `a06233fa…`, byggd från `f0e8be1` innan
bevakningsdomänen fanns.

`rpm -V brf-dokument-ai` rapporterar inga avvikelser. Bevakningsdomänen ligger i
paketet där den ska:
`/usr/lib/BRF Dokument-AI/runtime/backend/app/watches/{models,store,derive,routes}.py`,
och `app/terms.py` har flyttat till paketets rot i takt med källträdet.

Bygget kördes från ett rent `make setup` i utcheckningen; ändringen av
acceptansskriptet stashades undan **innan** paketeringen, så artefakten är
byggd ur `5337eec` utan tillägg.

## Payload-policyn

```
BRFV2_REQUIRE_ARTIFACT=1 BRFV2_RPM=dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  backend/.venv/bin/pytest -q backend/tests/test_desktop_artifact.py
→ 40 passed
```

Bevakningsdomänen drar inte in någon förbjuden leverantör: den använder bara
`app.terms`, `app.citations` och `app.store`, och gör inga nätverksanrop alls.

## Acceptansen

```
backend/scripts/desktop_acceptance.py \
  --application /usr/bin/brfv2-desktop \
  --artifact dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  --run-label bevakningar-installed
→ exit 0, 120,8 sekunder
```

Evidens: [`bevakningar-installed-desktop-acceptance.json`](bevakningar-installed-desktop-acceptance.json)
och sex skärmbilder bredvid. Generation gick mot
`gemma-4-12b-it-UD-Q4_K_XL.gguf` på `agenntserver` genom SSH-tunnel.
Utgångsläget var genuint oprovisionerat (isolerad `XDG_DATA_HOME`).

### Bevakningar i det installerade paketet

Det nya steget i acceptansen laddar upp ett serviceavtal, låter **paketets egen
motor** läsa det, och kontrollerar datumet den räknar fram innan en människa
godkänner det:

> "Avtalet gäller från och med den 1 februari 2026 **till och med den 31 januari
> 2028**. Om avtalet inte sägs upp förlängs det med tolv månader i taget.
> Avtalet får sägas upp skriftligen senast **sex månader** före avtalstidens
> utgång."

| Vad | Resultat |
| -- | -- |
| Förslag ur genomläsningen | 1 |
| Rubrik | "Säg upp eller ompröva avtalet senast **2027-07-31**" |
| Uträkning på skärmen | avtalstidens utgång 2028-01-31 enligt citerad avtalstid 2026-02-01 – 2028-01-31, minus 6 månader |
| Citat | ja, klickbart, öppnar `Serviceavtal hiss 2026.pdf` |
| Efter godkännande | hink **Senare**, ansvarig **Karin Lindqvist**, påminnelse 2027-07-01 |
| Kvarvarande förslag | 0 |

Två saker prövas som är lätta att missa: att **uträkningen står på skärmen** och
inte bara stämmer under ytan, och att förslaget **lämnar förslagslistan** när
det godkänns i stället för att dyka upp på två ställen.

Datumet är hårdkodat i acceptansen som `2027-07-31`. Ett paket som visar något
annat — eller ingenting — faller därför, i stället för att bara se ut att ha
funktionen med.

### Resten av resan, oförändrad

* **Första start** på en oprovisionerad maskin: förening, administratörskonto,
  modelltjänstens adress.
* **Grundat svar.** "Var har styrelsen sitt säte?" → *"Styrelsen har sitt säte i
  Göteborgs kommun."* med citat ur `Stadgar Brf Gjutformen 12.pdf` s. 1 och
  markeringen placerad på sidan. Proveniensen läser **Gemma 4 12B ·
  Self-hosted**. Ingestion 0,3 s.
* **Vägran.** Frågan utan täckning avvisas med *OTILLRÄCKLIGT UNDERLAG* och noll
  citat.
* **Säkerhetsgränsen.** Sidans skript når inte modelltjänsten (`connect-src`),
  `window.__TAURI__` är `undefined`, ett IPC-anrop utifrån avvisas av ACL:n, och
  sex otillåtna modelladresser avvisas med 422.
* **Livscykel.** Ren nedstängning, abrupt död, backup och återställning, och
  kvarhållet tillstånd över omstart.
* **Modelltjänst som inte svarar.** Applikationen startar ändå och säger det.

## Vad det här *inte* bevisar

Ingen Microsoft- eller Fortnox-inloggning sker i acceptansen. Ett device
code-flöde kräver att en människa öppnar en webbläsare och godkänner, och att
fejka det hade bevisat att stubben fungerar. Liveintegrationerna är i stället
prövade genom en injicerad transport som kräver exakt rätt begäran (65 tester),
vilket är strängare än ett verkligt anrop mot en förlåtande server — men inte
samma sak som ett riktigt anrop, och det sägs som det är.

En nyinstallerad applikation gör ingen utgående trafik alls förrän någon
konfigurerar och loggar in.
