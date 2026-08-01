# BP6 — beslutsunderlag, Fedora desktop-pilot

**Grind:** BP6 (Avslut)
**Projekt:** brfv2 Desktop — Fedora app shell
**Underlag daterat:** 2026-08-01
**Gren:** `bp6/fedora-pilot-closeout`
**Avstamp (förälder):** `d6e73bf280390995847b87cdd092acc9fa211014` — BP5-kallgranskningen
**Tagg som sätts på den godkända closeoutcommiten:** `v0.2.0-fedora-pilot`

Agenten **rekommenderar**. Det formella BP6-beslutet fattas av människan efter
leverans, och projektet markeras inte Completed av byggsessionen.

---

## 1. Vad som avgörs

Om den kontrollerade Fedora-skrivbordspiloten kan **avslutas** — inte om
produkten kan distribueras, breddas eller sättas i produktion. De frågorna
besvaras av kravlistorna i `SLUTRAPPORT-DESKTOP-PILOT.md` §5 och §6 och ligger
utanför BP6.

---

## 2. Integrationspolicy — läget som faktiskt gäller

Den ursprungliga briefen antog att `main` fortfarande låg på
`1cd65cae755b72f753b1d36ab4a1d5314fe2ea79`. Det stämmer inte: mobil-PR #1 har
flyttat `origin/main` till `acd39de0ce7e46e94786ba3aafa33fb22ee20ad7`.

Linjerna divergerar från samma webbaslinje och mobilspåret ändrar delade
backend- och authfiler (`backend/app/auth.py`, `backend/app/main.py`,
`backend/tests/test_api.py`). En merge i BP6 hade därför varit **ny
produktintegration** och lämnat den kallgranskade pilotens scope.

**Beslutad och tillämpad policy:**

* `main` och mobilspåret lämnas orörda;
* ingen merge, squash, rebase, cherry-pick eller force-push mellan linjerna
  görs i BP6;
* Fedora-piloten avslutas på en separat, fryst släpplinje;
* den verifierade desktophistoriken bevaras oförändrad och görs nåbar genom
  branch och annoterad tagg.

Den tidigare STOP-rekommendationen var korrekt mot den gamla ff-only-briefen och
utgör **inte** ett projektstopp efter detta policybeslut.

---

## 3. Grindkriterier och utfall

| # | Kriterium | Utfall | Bevis |
| -- | -- | -- | -- |
| G1 | Pilotens fråga är besvarad, inte bara arbetad på | **Uppfyllt** | Slutrapport §2 och §9; fyra slingor genomförda med committad evidens |
| G2 | Ett oberoende utfall finns som inte byggsessionen själv producerat | **Uppfyllt** | BP5-kallgranskning 2026-07-31, granskare utan bygghistorik: `PASS BP5 — CONTROLLED SINGLE-OPERATOR FEDORA PILOT VERIFIED` |
| G3 | Inget stoppkriterium har utlösts | **Uppfyllt** | Alla sju prövade var för sig i varje slinga och av kallgranskaren; noll utlösta |
| G4 | Artefaktidentiteten är oförändrad genom hela piloten | **Uppfyllt** | RPM `6ba028fb…`, `deliveryTree` `a702a337…`, `rpm --verify` 0 — omkört idag, §4 |
| G5 | Kända begränsningar är fullständigt redovisade, inte sammanfattade bort | **Uppfyllt** | Slutrapport §4, tolv namngivna begränsningar plus tio dokumentationsluckor |
| G6 | Det som accepterades bara inom enanvändarpiloten är skilt från det som är bevisat | **Uppfyllt** | Slutrapport §2 mot §3 |
| G7 | Kraven före bredare pilot och före distribution är utskrivna och åtskilda | **Uppfyllt** | Slutrapport §5 (B1–B12) och §6 (P1–P10) |
| G8 | Closeouten ändrar inte produktbeteende | **Uppfyllt** | Diffen mot `d6e73bf…` är dokument-only, §5 |
| G9 | Överlämningen går att följa av någon annan | **Uppfyllt** | `OVERLAMNINGSINDEX-DESKTOP.md` |
| G10 | Repositorytopologin är dokumenterad och `origin/main` orörd | **Uppfyllt** | Slutrapport §7; `origin/main` = `acd39de…`, oförändrad, §4 |

---

## 4. Verifieringar körda för detta underlag

Alla körda 2026-08-01 på pilotmaskinen (Fedora 44), mot det arkiverade paketet
och den installerade produkten.

| Kontroll | Kommando | Resultat |
| -- | -- | -- |
| Artefaktens hash | `sha256sum ~/pilot-artefakter/…rpm` | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` ✅ |
| Artefaktens storlek | `stat -c%s` | `574604029` byte ✅ |
| Arkiv = installation | `rpm -q --qf '%{SHA256HEADER}'` | `5fc97bcef7da938e658cd486443f5110d97f26ce7b86bd0facadc9ae233243fe` ✅ |
| Signatur | `rpm -q --qf '%{SIGPGP}'` | `(none)` — osignerad, som påstått ✅ |
| Paketintegritet | `rpm --verify brf-dokument-ai` | exitkod **0**, inga skillnader ✅ |
| Skalbinären | `sha256sum /usr/bin/brfv2-desktop` | `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` ✅ |
| `deliveryTree` ur repot | `repro_delivery_tree` på denna gren | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` ✅ |
| `deliveryTree` ur installationen | `BUNDLE.json` | `a702a337…` — **identisk med repots** ✅ |
| Leverantörsuteslutning | `ops/inspect_payload.py --installed --scope installed` | `ok: true`, **45 kontroller, 0 fynd**, 21 frånvarande / 24 godkända / 0 utanför omfång, payload `55c20520e4a5054c…`, 4 675 filer, regler `500e8c85…` ✅ |
| Full regressionssvit | `pytest -q` med `BRFV2_REQUIRE_ARTIFACT=1 BRFV2_RPM=<arkiverad>` | **657 passed, 3 skipped** — exakt pilotens baslinje ✅ |
| Artefakttester ensamt | `make desktop-verify-artifact` | **40 passed** ✅ |
| Evidensskyddet (A3) | `pytest tests/test_desktop_acceptance_evidence.py` | **7 passed** ✅ |
| Blanksteg/konflikt­markörer | `git diff --check` | rent ✅ |
| Persondataskanning | reguljär sökning över spårade filer | Endast syntetiska adresser: `@exempel.se`, `@demo.se`, `@acceptans.example`, `@brf.example`, `@example.invalid`, `@gjutformen12.se`, `@sjoutsikten7.se`. Inga verkliga adresser. ✅ |
| Hemlighetsskanning | mönster för `sk-*`, `ghp_*`, `AKIA*`, PEM-nycklar | Endast avsiktliga attrapper: `sk-ant-must-never-be-used`, `sk-ant-should-never-be-used`, `sk-super-secret-token`, `sk-finns-men-ska-inte-väljas` — samtliga finns för att *bevisa* att nyckeln tas bort eller inte väljs ✅ |
| Databärande artefakter i git | `git ls-files` mot `.db/.sqlite/.zip/.pdf/.eml/.pem/.env` | Endast `brfv2-mockup/e2e/fixtures/pilot-upload.pdf`, en syntetisk testfixtur. Ingen `auth.db`, ingen säkerhetskopia, ingen korpus ✅ |
| Kundkorpus i git | `git ls-files` mot `DONT_PUSH*`, `wetransfer*`, `docs-external/` | Inget spårat ✅ |

**Anmärkning om personuppgifter:** operatörens namn förekommer i
rollbeskrivningar (`PILOTPLAN.md` §12, `SLUTRAPPORT.md`,
`DRIFT-FORVALTNINGSPLAN.md`, `JOURNAL.md`, `slinga1-startevidens.md`). Det är en
namngiven projektroll, inte läckt driftdata, och är avsiktligt. Den
personuppgift som *inte* är committad är den i `data/auth.db` — se slutrapport
§3.14.

---

## 5. Closeoutens omfattning

Diffen från `d6e73bf280390995847b87cdd092acc9fa211014` till closeoutkandidaten
innehåller **endast**:

```
docs/pilot/SLUTRAPPORT-DESKTOP-PILOT.md    (ny)
docs/pilot/BP6-BESLUTSUNDERLAG.md          (ny)
docs/pilot/OVERLAMNINGSINDEX-DESKTOP.md    (ny)
```

Ingen produktkod, ingen paketering, ingen historisk pilotevidens och inget
`REPRO_DELIVERY_PATHS`-innehåll ändras. `repro_delivery_tree` är därför
oförändrat `a702a337…` före och efter — vilket är den mekaniska bekräftelsen på
att closeouten inte kan ha rört artefaktens identitet.

XS-58 (radbrytning i chattfältet) och samtliga övriga förbättringar är backlog
och har inte implementerats.

---

## 6. Vad ett `PASS BP6` **inte** får läsas som

Kallgranskningens formulering gäller oförändrat. Ett godkännande här säger
ingenting om:

* distribution eller bruk på fler maskiner eller av fler människor;
* produktions- eller supportåtaganden;
* kvalitet mot verkliga BRF- eller kunddokument;
* säkerhet på en delad maskin bortom en OS-användares tillitsgräns;
* tillgänglighetskompletta arbetsflöden;
* signerade paket eller uppdateringskanaler;
* `dnf upgrade`;
* andra OS-familjer eller andra Fedora-majorversioner;
* fysisk säker radering eller blocköverskrivning;
* ett giltigt M10-friktionsmått.

---

## 7. Öppna punkter som avslutet **inte** stänger

| # | Punkt | Var den hör hemma |
| -- | -- | -- |
| Ö1 | Villkoret för obesvarbara frågor — noll citat, eller kvalificerat icke-svar med stött citat? Öppen sedan BP4-3. | Bredare pilot (B9). Det enda formellt oavgjorda utvärderingsvillkoret. |
| Ö2 | D4:s karantänmetod vs. verklig radering. Kallgranskningen accepterade den inom bevisad omfattning; BP4-4 begärde ett grindbeslut. | Distribution (P3). |
| Ö3 | Aggregatsummans formel för `data/`-trädet är odokumenterad. | Bredare pilot (B11) — en evidenskedja som inte går att återskapa är ingen evidenskedja. |
| Ö4 | M10 är ogiltigt och möjligheten förbrukad; en omtagning kräver en ny okonfigurerad installation. | Distribution (P10). |
| Ö5 | Begränsning 3:s premiss om Wayland-tangentbordsinjektion motsägs delvis av piloten själv. | Bredare pilot — påverkar hur tillgänglighet kan verifieras (B3, P4). |
| Ö6 | Dokumentationsrättelser: PILOTPLAN §2 `Personuppgifter: Inga`, §4.3 datakontraktet, §6.5 regressionsbaslinjen, runbookens S1-formulering, M4-etiketten, `slinga2-forstastart.md` §B5:s orättade 10/10. | Får **inte** göras här — de skulle ändra historisk pilotevidens. Hör till en framtida pilots planeringsfas, med rättelserna som ingång. |

Punkterna är redovisade, inte lösta. Att stänga dem i BP6 hade krävt att
historisk evidens ändras, vilket policyn i §2 uttryckligen förbjuder.

---

## 8. Rekommendation

Piloten har svarat på sin fråga, gjort det med committad evidens, blivit
oberoende granskad, inte utlöst något stoppkriterium, och kan redovisa både vad
den bevisade och vad den uttryckligen inte kan bära. Artefaktidentiteten är
verifierad idag och är oförändrad. Closeouten ändrar inget produktbeteende och
rör inte mobilspåret.

De öppna punkterna i §7 är alla korrekt placerade *efter* piloten: de är krav på
en bredare pilot eller på distribution, inte på avslutet. Att hålla piloten
öppen för att lösa dem skulle bevara en fryst släpplinje som ingen längre
utvecklar, samtidigt som fortsatt produktarbete redan sker på produktlinjen.

> ## `PASS BP6 — PROJECT MAY CLOSE`

Med tre villkor på formuleringen av beslutet:

1. Beslutet gäller **den kontrollerade enanvändarpiloten**, inte produkten.
2. §6 citeras i beslutstexten, så ett `PASS` inte senare läses bredare än det är.
3. Ö1–Ö6 förs över som backlog i projektet
   `brfv2 Desktop — Styrelsearbetsyta & integrationer` eller i ett nytt
   pilotprojekt, inte som stängda punkter.
