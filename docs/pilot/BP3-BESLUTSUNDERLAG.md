# BP3 — beslutsunderlag

**Grind:** Planering → BP3, *Starta genomförandet.*
**Datum:** 2026-07-29. **Uppgift:** XS-53.
**Underlag:** [PILOTPLAN.md](PILOTPLAN.md), [RUNBOOK-PILOT.md](RUNBOOK-PILOT.md).

Agenten sammanställer, människan beslutar. Ingenting nedan är ett beslut.

---

## 1. Vad grinden ska fastställa

Att planen är tillräckligt bra att bygga — här: att *bedriva pilot* — mot. Inte
att produkten är bra, inte att piloten kommer att lyckas.

## 2. Kriterier och evidens

| # | Kriterium | Utfall | Hur det kan kontrolleras nu |
| --- | --- | --- | --- |
| K1 | Arkitekturen är beslutad och fryst på den nivå som blir dyr att ändra | **Uppfyllt** | BP2-beslutet `PASS BP2 — TAURI 2 FOR CONTROLLED FEDORA PILOT` (XS-52). Den installerade artefaktens `deliveryTree` = `a702a337…`, kontrollerat 2026-07-29 i `/usr/lib/BRF Dokument-AI/runtime/BUNDLE.json` |
| K2 | Kontrakten är definierade | **Uppfyllt** | Samma-origin-kontraktet och readiness-kontraktet (adr/0001), modellgränspolicyn maskinläsbar på `GET /api/desktop/model-endpoint-policy` (adr/0002), leveranssökvägarna som "vad som får ändras"-kontrakt i `ops/lib/repro.sh`, datalayouten under `~/.local/share/se.brfdokumentai.desktop/` |
| K3 | Utvärderingsplanen är skriven **före** genomförandet | **Uppfyllt** | Pilotplanen §6: acceptanskommando, artefakt- och gränskontroller, femton namngivna frågor med facit ur `backend/eval/golden.json`, godkännanderegeln hämtad från den etablerade readinessgaten, och mänsklig tangentbordssmoke med uttalad evidensklass |
| K4 | Den avgränsade första leveransen är namngiven precist | **Uppfyllt** | Fyra slingor med var sin BP4 (pilotplanen §5), var och en med vad den ska göra demonstrerbart |
| K5 | Kända begränsningar är klassificerade i stället för absorberade | **Uppfyllt** | Pilotplanen §9: XS-53:s sju plus fem ytterligare funna i BP2-evidensen, var och en som accepterad, åtgärdas-före-start eller uppföljning |
| K6 | Risker är namngivna med hantering | **Uppfyllt** | Pilotplanen §10, tolv risker |
| K7 | Framgångs- och stoppkriterier är mätbara | **Uppfyllt** | Pilotplanen §7 (tio mätvärden, varje med insamlingsväg) och §8 (sju stoppkriterier, tre pauskriterier) |
| K8 | Installation, återgång och dataåterställning är beskrivna som körbar procedur | **Uppfyllt** | Runbooken. Ett steg är märkt *Härlett* — återställning efter raderad datakatalog — och är precis vad övning D4 ska bevisa |
| K9 | Backloggen är seedad med det arbete som verkligen är känt | **Uppfyllt** | Fyra Linear-issues, en per slinga, i Backlog och blockerade av det här beslutet |
| K10 | Piloten kan inte tyst ändra den granskade artefakten | **Uppfyllt** | Leveransträdets summa (pilotplanen §4.1) körs före och efter arbetspass som rört repot; avvikelse är ett stopp |

Inget kriterium vilar på "det ser rätt ut". De fem kontrollerna i pilotplanen §1
kördes 2026-07-29 på den tänkta pilotmaskinen och gav de utfall som står där,
inklusive `ops/inspect_payload.py --installed` → 45 kontroller, 0 fynd.

## 3. Vad som saknas, och varför det inte blockerar grinden

| Saknas | Varför det inte blockerar BP3 |
| --- | --- |
| Paketfilen finns inte i den här arbetskopian (`dist/` är tom) | Arbetspunkt A1 i slinga 1. Artefakten är reproducerbar från `84b6fc8`, och den installerade kopian är redan den godkända |
| `backend/.venv` saknas | `make setup`, arbetspunkt A1 |
| Tre M-klassade åtgärder (acceptansens `xs49-*`-namn, arkivering utanför `dist/`, versionsbytespolicyn) | Alla ligger i slinga 1, före första pilotpasset, och ingen rör artefakten |
| Mänsklig tangentbordssmoke har aldrig gjorts | Planerad som B3 med namngivna steg; att den inte är gjord är själva skälet att den står i planen |

## 4. Uttryckligen parkerat — blockerar inte den här grinden

* **Signering av paketet.** Ingen distribution sker i piloten. Krävs innan
  artefakten lämnar maskinen.
* **Uppgraderingsmigrering (`dnf upgrade`).** Piloten kör en version.
  Versionsbyte sker som avinstallation + installation med säkerhetskopia först.
* **Automatiserad fysisk tangentbordsinjektion.** Ersatt av operatörsattestering
  under piloten.
* **Bred distribution, andra operativsystem, andra Fedora-versioner.**
* **Riktig BRF-korpus och personuppgifter.** Kräver eget gate-beslut och att
  ägarfrågorna i drift- och förvaltningsplanen §8 stängs först.
* **Kvantisering av embeddervikterna** (halverar paketet, ändrar
  retrievalvektorerna, kräver egen utvärdering).
* **Strängen `claude-opus-4-8` i `Settings.aiModel`.** Ligger i en leveranssökväg
  — att ändra den flyttar artefaktens bytes och upphäver BP2-underlaget.
* **Ägarfrågorna för modellruntime, korpusförvaltning och produktionsändringar**
  i drift- och förvaltningsplanen. Piloten stänger endast backup/återställning
  och incidenthantering, och endast för sin egen omfattning.

## 5. Det beslutsfattaren bör väga

Piloten som den är avgränsad — en maskin, en människa, syntetisk korpus — mäter
**om produkten går att leva med**, inte **om den är redo för en förening**. Den
kan inte visa att någon annan kan installera paketet, och inte att svaren håller
mot verkliga stadgar och årsredovisningar. Är avsikten med piloten det senare, är
den här planen fel avgränsad och grinden bör returneras för omplanering snarare än
passeras. Det är inte planerarens bedömning att göra.

Det piloten däremot mäter är exakt det Effekt-milstolpen frågar efter:
operatörsfriktion, installation och användbarhet — med mätvärde M2
(terminalingripanden) som den ärligaste indikatorn.

## 6. Rekommendation

**`PASS TO EXECUTION`** — i Tonnquists termer *fortsätt enligt plan, med
uttrycklig avgränsning*: allt i §4 är parkerat och blockerar inte, och de tre
M-klassade åtgärderna görs i slinga 1 före första pilotpasset.

Skälet i en mening: arkitekturen är fryst och oberoende granskad, artefakten är
bevisligen den granskade och sitter redan på pilotmaskinen, och utvärderingsplanen
är skriven före piloten med namngivna kommandon, facit och stoppkriterier.

Beslutet fattas av människan och skrivs in i beslutsloggen. Den här filen ändras
inte i efterhand.
