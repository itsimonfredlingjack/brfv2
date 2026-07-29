# Pilotjournal — kontrollerad Fedora-pilot

Plan: [PILOTPLAN.md](PILOTPLAN.md) · Instruktion: [RUNBOOK-PILOT.md](RUNBOOK-PILOT.md)

**Produkten har ingen telemetri.** Varje mätvärde piloten kommer att kunna visa
upp finns bara därför att det skrivs in här, av operatören, efter passet. En rad
som inte skrivs är ett mätvärde som inte finns — det går inte att rekonstruera i
efterhand. Journalraden är därför sista steget i sessionschecklistan, inte något
som görs "när det finns tid".

Journalen är inte en dagbok. Den ska gå att läsa av någon som inte var med, som
underlag för BP4-avstämningarna och för BP5.

---

## Piloten i siffror

| | |
| --- | --- |
| Artefakt | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm`, SHA-256 `6ba028fb…` |
| Arkiv | `~/pilot-artefakter/` (utanför `dist/`, skrivskyddat, med `SHA256SUMS`) |
| `deliveryTree` | `a702a337…` |
| Korpus som filer | `~/pilot-korpus/` (fem PDF:er + `korpus.sha256`) |
| Modelltjänst | Gemma 4 12B på `agenntserver` via `ssh -N -L 8000:127.0.0.1:8000` |
| Modelladress i appen | `http://127.0.0.1:8000/v1` |

---

## Mätvärden (pilotplanen §7)

Uppdateras efter varje pass. `—` betyder att inget pass ännu kunnat mäta det.

| # | Mätvärde | Status |
| --- | --- | --- |
| M1 | Pass startade från applikationsmenyn utan terminalarbete utöver tunneln | 0 av 0 pass |
| M2 | Terminalingripanden under pass, och vad de gällde | — *(effektmålets mätvärde)* |
| M3 | Startmisslyckanden (felfönster) per pass | — |
| M4 | Oväntade backend-dödsfall per pass | — |
| M5 | Fragment-faktafrågor besvarade med korrekt löst citat | — *(baslinjen sätts i B5)* |
| M6 | Felaktiga avvisningar | — |
| M7 | Fabricerade källhänvisningar | 0 — **måste förbli 0** (stoppkriterium 4) |
| M8 | Backup/restore-övningar och om data stämde efteråt | — *(slinga 4)* |
| M9 | Av-/ominstallationscykler med bevarad data | — *(slinga 4)* |
| M10 | Tid från okonfigurerad maskin till första grundade svar | — *(mäts en gång i slinga 2)* |

---

## Frågeuppsättningen (pilotplanen §6.3)

Femton frågor, körda genom appens AI-chatt. Första körningen **sätter** baslinjen;
därefter jämförs varje körning mot den. Ett tapp ska förklaras. En fabricerad
källhänvisning är alltid ett stopp, från första körningen.

| Datum | Fragment-fakta (av 10) | Prosa (av 2) | Obesvarbara avvisade (av 3) | Fabricerade | Anmärkning |
| --- | --- | --- | --- | --- | --- |
| *(baslinje sätts i B5)* | | | | | |

---

## Passmall

Kopiera blocket, fyll i, lägg överst under "Pass".

```
### Pass N — ÅÅÅÅ-MM-DD

Syfte:
Före passet:  tunnel uppe [ ]  probe svarar [ ]  leveransträdet a702a337… [ ]
Vad som gjordes:
Frågeuppsättning:  fragment-fakta _/10 · prosa _/2 · obesvarbara _/3 · fabricerade _
M1 start från menyn: ja/nej
M2 terminalingripanden: antal — vad de gällde
M3 felfönster: _   M4 backend-dödsfall: _
Avvikelser (S1/S2/S3):
Efter passet: säkerhetskopia skapad [ ] flyttad till annan media [ ] pgrep tomt [ ] tunnel stängd [ ]
```

---

## Avvikelser och incidenter

| Datum | Klass | Vad | Åtgärd | Status |
| --- | --- | --- | --- | --- |
| *(inga)* | | | | |

Klasserna S1/S2/S3 definieras i pilotplanen §12. En S1 stoppar piloten och får en
egen anteckning under `docs/evidence/pilot/incident-<datum>/`.

---

## Pass

### Slinga 1 — 2026-07-29 · miljön upprättad (inget pilotpass)

Detta är inget arbetspass med produkten: applikationen startades aldrig,
datakatalogen skapades inte och ingen fråga ställdes. Raden finns för att slingan
ska vara journalförd, inte för att den mätte något.

Utfört (evidens: [`docs/evidence/pilot/slinga1-startevidens.md`](../evidence/pilot/slinga1-startevidens.md)):

* **A1** — artefakten ombyggd i ren checkout av `84b6fc8`; SHA-256
  `6ba028fb…` identisk med den BP2 godkända; arkiverad skrivskyddad i
  `~/pilot-artefakter/` med kvitto och `SHA256SUMS`. Arkivets RPM-header är
  densamma som den installerade (`5fc97bce…`) — arkivet och installationen är
  samma artefakt.
* **A2** — baslinjekontrollerna omkörda: `rpm --verify` = 0, installationens
  `deliveryTree` = `a702a337…`, `inspect_payload --installed` 45 kontroller /
  0 fynd, ingen datakatalog ännu, 356 GB fritt. `webkit2gtk4.1 2.52.5-1.fc44`
  och `gtk3 3.24.52-2.fc44` noterade (risk R1).
* **A3** — acceptansens `xs49-*`-namngivning borta; evidensen namnges av
  `--run-label`, och committad evidens stoppar körningen om inte
  `--overwrite-evidence` anges. Leveransträdet oförändrat före och efter.
  Regression: 657/3 backend (baslinjens 650 + 7 nya tester för just det här
  skyddet), 21 frontend, 11 e2e, 5 Rust, lint rent.
* **A4** — korpusens fem PDF:er utskrivna till `~/pilot-korpus/`, deterministiskt
  (andra körningen: alla oförändrade), med `korpus.sha256`.
* **A5** — den här journalen upplagd.

M1–M10: inget mätt. Terminalingripanden räknas inte i slinga 1 — slingan *är*
terminalarbete, och den mäter inte operatörsfriktion.

Kvar innan första passet (slinga 2): SSH-tunneln uppe och Gemma 4 12B
annonserad, formell pilotacceptans grön (§6.1), mänsklig tangentbordssmoke
attesterad (§6.4). Ingen av dem kunde göras i slinga 1 — acceptansen kräver en
nåbar modelltjänst och tunneln var nere.
