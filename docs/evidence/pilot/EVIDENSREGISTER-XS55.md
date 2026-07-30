# Evidensregister XS-55 — vad som är preflight och vad som är förstagångsstart

Två sorters evidens uppstår i XS-55, och de bevisar **olika saker**. Blandas de
ihop läser en granskare automatkörd produktverifiering som om den vore
observationen av den genuina förstagångsstarten. Det här registret gör skillnaden
strukturell i stället för att lita på minnet.

---

## Klass P — preflight / formell acceptans (§6.1)

**Vad den bevisar:** att *produkten* uppfyller acceptansen på den här maskinen.
**Vad den inte bevisar:** något alls om pilotens förstagångsstart.

Körd 2026-07-29 **19:38:43–19:40:53**, **före** första start, exitkod 0, 129,9 s,
alla fyra faser. Den körde i ett eget `XDG_DATA_HOME` under
`/tmp/brfv2-acceptance-*` (`backend/scripts/desktop_acceptance.py:378,1861`) och
rörde aldrig `~/.local/share/se.brfdokumentai.desktop`.

Tidsfönstret är avläst ur filernas mtime (första skärmbild 19:38:52,
`acceptance.json` 19:40:53) jämte `durationSeconds`. En tidigare anteckning angav
19:49–19:52; det var när agenten *läste* resultatet, inte när körningen skedde.

Kommandots `--run-label` var `xs55-slinga2`, vilket gav prefixet
`xs55-slinga2-installed-`. **Det prefixet är olyckligt** — det läser som om
filerna vore slinga 2:s huvudevidens, vilket de inte är.

| Fil | SHA-256 | Klass |
| --- | --- | --- |
| `xs55-slinga2-installed-desktop-acceptance.json` | `44b9d33f…` | **P** |
| `xs55-slinga2-installed-desktop-setup.png` | `0032b88a…` | **P** |
| `xs55-slinga2-installed-desktop-documents.png` | `e1ebd2eb…` | **P** |
| `xs55-slinga2-installed-desktop-settings.png` | `eb5d71c1…` | **P** |
| `xs55-slinga2-installed-desktop-refusal.png` | `bc255d57…` | **P** |
| `xs55-slinga2-installed-desktop-answer-highlight.png` | `213354af…` | **P** |

### Varför filerna inte döps om

JSON:en refererar de fem skärmbilderna vid namn på rad 2118–2122. En omdöpning
skulle antingen bryta den interna konsistensen eller kräva att jag redigerar
producerad evidens. Evidens som redigeras i efterhand är inte längre evidens, så
filerna lämnas **bit-exakt som de skrevs** och klassas i stället här.

### Skärmbilderna visar acceptansens data, inte pilotens

`setup.png`, `documents.png`, `settings.png`, `refusal.png` och
`answer-highlight.png` visar acceptansens syntetiska förening `Brf Gjutformen 12`
med kontot `styrelsen@acceptans.example` i ett tillfälligt datahem. Att
föreningsnamnet är detsamma som pilotens är en sammanträffande likhet i
testdata — **det är inte pilotinstallationen**.

### Ingen maskering behövs — och det är bevisat, inte antaget

Kravet på maskering gäller evidens som innehåller personidentitet. Ingen av de sex
klass-P-filerna gör det, och slutsatsen vilar på en tidsordning som inte kan
kringgås:

| | Tidpunkt |
| --- | --- |
| Skärmbilderna skrivna | 19:38:52 – 19:39:02 |
| `acceptance.json` skriven | 19:40:53 |
| **Operatörens konto skapades tidigast** | **21:14:52** (datakatalogens födelse) |

Skärmbilderna togs alltså **1 h 35 min innan operatörens konto existerade**. De kan
inte visa hens namn eller e-postadress, eftersom uppgifterna inte fanns i något
datalager när bilderna togs. Kontrollerat därtill mekaniskt: operatörens verkliga
e-postadress förekommer inte i någon av de sex filerna, inte i `HEAD`, och inte i
någon av XS-55:s evidenstexter.

Filerna committas därför **bit-exakt och omaskerade**, vilket är det korrekta
utfallet — en maskerad kopia av evidens som inte innehåller personuppgifter skulle
bara försämra spårbarheten.

**Personuppgifterna finns i stället i pilotinstallationens `data/auth.db`** (och i
varje säkerhetskopia av den). Den katalogen och dess kopior committas aldrig — se
omfångsavvikelsen i journalen.

### Dummy-nyckeln bevaras avsiktligt

`ANTHROPIC_API_KEY: "sk-ant-must-never-be-used"` förekommer i JSON:en. Den är en
attrapp som säkerhetsfasen sätter för att bevisa att skalet *tar bort* variabeln
ur backendprocessens miljö (`src-tauri/src/main.rs`). Den ska stå kvar: det är
den som visar att borttagningen sker. Ingen verklig nyckel, ingen personuppgift.
Granskningen finns i [`slinga2-forstastart.md`](slinga2-forstastart.md).

---

## Klass F — genuin förstagångsstart (B2–B5)

**Vad den bevisar:** att en okonfigurerad maskin blev en fungerande installation,
observerad en enda gång.

Reserverad `--run-label` för eventuella framtida acceptanskörningar som hör till
själva förstagångsstarten: **`xs55-forstastart`** → prefix
`xs55-forstastart-installed-`. Den etiketten är oanvänd i skrivande stund och får
inte återanvändas för preflight.

| Underlag | Klass | Evidensklass |
| --- | --- | --- |
| [`slinga2-forstastart.md`](slinga2-forstastart.md) B0/B1 — kontroller före start | **F** | verifierat |
| B2 uppstartsdialog, förening + konto + modelladress | **F** | **operatörsattestering**, styrkt av logg (`Installation konfigurerad`, probe `200 OK`) |
| B3 tangentbordssmoke — 7 av 8 | **F** | **operatörsattestering med verktygsstöd** — inte automatkörning. Det underkända steget är dessutom **verifierat i källkod** |
| B4 uppladdning av fem PDF:er | **F** | **verifierat** — 5 poster / 13 chunks, bit-identiska med `~/pilot-korpus/` |
| B5 frågeuppsättningen, baslinje | **F** | **operatörsattestering** för svaren, **verifierat** för citaten (rekonstruerad sidtext ur `extract/<id>.json`) |
| [`slinga2-atertagning-efter-vardkrasch.md`](slinga2-atertagning-efter-vardkrasch.md) — värdkrasch, återtagning och efterpass | **F** | **verifierat** — maskinläst, ingen operatörsattestering |
| [`../../pilot/JOURNAL.md`](../../pilot/JOURNAL.md) slinga 2 | **F** | journalförd av operatören |

*Raderna för B2/B4/B5 stod tidigare som "ej utförd ännu". Det var riktigt när
registret skrevs (06:49) men blev fel under samma dygn; de är rättade här i stället
för att lämnas kvar som en motsägelse mot journalen.*

---

## Kontroll: committad evidens är orörd

A3-skyddet prövades skarpt i den här körningen. `--run-label` styrde namnen, och
den committade XS-49-evidensen skrevs inte över:

```
git diff --quiet HEAD -- docs/evidence/   →  ingen spårad evidensfil ändrad
```

De tio `xs49-*`-filerna är bit-identiska med `HEAD`. Det är första gången skyddet
prövas utanför sin egen regressionssvit, och det höll.

---

## Regel för BP5-underlaget

Klass **P** får aldrig citeras som stöd för ett påstående om förstagångsstarten,
och klass **F**:s smoke får aldrig citeras som automatkörd evidens. Skriver någon
"acceptansen visar att första starten fungerade" är det en sammanblandning av
just de här två klasserna.
