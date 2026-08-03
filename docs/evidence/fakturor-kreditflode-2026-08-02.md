# Fakturaresan i den riktiga applikationen — kreditflödet och regelversionen, 2026-08-02

Fyra saker som stod som antaganden stängs här: att kreditflödet fungerar i den
**riktiga** applikationen och inte bara i enhetstest, att regelversionen inte
kan halka efter reglerna, att acceptansens evidens överlever en omstart, och att
de två acceptanserna kan köras under samma etikett utan att skriva över
varandra.

Ingenting nedan är simulerat: applikationen är release-binären, fönstret är
riktig Tauri/WebKitGTK, klicken går genom WebDriver, och maskinens utgångsläge
är genuint oprovisionerat (isolerad `XDG_DATA_HOME` i en slängbar
temporärkatalog).

## Körningen

| | |
| -- | -- |
| Kommando | `RUN_LABEL=fakturor make invoice-acceptance` (och därefter `make desktop-acceptance-full`) |
| Applikation | `src-tauri/target/release/brfv2-desktop`, SHA-256 `460686a0c964fb05481ef59da74db24ac005a5f6259c0c17ff96015f2a6d0c49` |
| Regelversion | `regelmotor 2026.08.2` |
| Modell | **ingen** — `modelRequired: false` i kvittot |
| Evidens | `fakturor-invoice-*.png` + `fakturor-invoice-acceptance.json` |
| Värd | Fedora 44 |

Att den går grön utan modell är en egenskap hos funktionen och inte hos
skriptet: fakturagranskningen är deterministisk hela vägen.

## Kreditfakturan, verifierad i fönstret

Fjärde inläsningen i resan är `SI-2027-024`, en kreditnota på `-6 250,00 SEK`
från samma leverantör som `SI-2027-018`. Vad skärmen visade
(`fakturor-invoice-credit.png`):

* beloppet som **negativt** — `−6 250,00 SEK` i rubriken, i fältlistan, i raden
  (`-4 × 1 250,00 = −5 000,00 SEK`) och i kön — inte ett positivt tal vars
  tecken läsaren ska härleda ur ordet "kredit";
* signalen **Möjlig kreditfaktura** som *info*, inte som en varning: ett par som
  tar ut varandra exakt är en normal och riktig sak att hitta;
* fyndet namnger fakturan det tar ut, och säger i samma andetag vad det inte kan
  avgöra — *"Att två belopp tar ut varandra betyder inte att krediteringen avser
  just den här fakturan. Ingenting i underlaget säger vilken faktura en
  kreditnota hör till."*;
* inget citat på fyndet, vilket är rätt: ett citat betyder en ordagrant
  verifierad passage i ett dokument, och bakom en jämförelse mot en annan
  faktura finns ingen sådan;
* ingen kontroll som **kvittar**, **matchar**, godkänner, attesterar eller
  betalar — 40 knappar på skärmen, noll som avslutar paret. Att kvitta sker i
  ekonomisystemet.

### Ett fel som E2E-verifieringen hittade

Fyndet stod åt fel håll. Meningen var skriven för fallet *"jag tittar på den
vanliga fakturan och en kreditnota finns"*, och användes även i det omvända
fallet — så öppnad **på kreditnotan**, vilket är precis det en granskare gör med
en kreditnota, läste den som om den vanliga fakturan krediterade kreditnotan. Ett
negativt belopp krediterar ett positivt och aldrig tvärtom.

Rättningen är riktningsberoende och ligger i `duplicate_findings`. Enhetstestet
som fanns kodade in den felaktiga riktningen (det analyserade kreditnotan och
förväntade sig meningen som beskriver det andra hållet), så det är utökat med
ett test per riktning.

## Regelversionen, verifierad genom att den felade

Rättningen ovan **är** en regeländring, vilket gjorde den till första skarpa
provet på den nya kontrollen:

```
$ pytest -q tests/test_invoice_rules_version.py
AssertionError: Granskningsreglerna har ändrats utan att ANALYSIS_ENGINE_VERSION höjts.
    ändrade regelkällor: app/invoices/compare.py
    Fynd som redan är stämplade med 2026.08.1 skulle då påstå att de skrevs av de nya reglerna.
    Höj ANALYSIS_ENGINE_VERSION i app/invoices/models.py och kör sedan:
      backend/.venv/bin/python -m app.invoices.rules --write
```

Den namngav modulen som rörde sig. Efter bumpen till `2026.08.2` och
`make invoice-rules-lock` är sviten grön, och `RULES.lock.json` bär båda
versionerna — skillnaden mellan dem visar exakt vilken regelkälla som ändrades:

| Regelkälla | 2026.08.1 | 2026.08.2 |
| -- | -- | -- |
| `app/integrations/review.py` | `4ae380874dffa0df` | oförändrad |
| `app/integrations/supplier.py` | `656301fbb2cd0e02` | oförändrad |
| `app/terms.py` | `018b22508562f48e` | oförändrad |
| etikettabellerna i `integrations/models.py` | `45483c855d42d1c9` | oförändrad |
| `app/invoices/compare.py` | `ce19842d32512ae1` | **`4cdb32615d8c1783`** |

## Vad evidensen är, och var

Skärmbilderna och kvittot ligger i `docs/evidence` under körningens etikett i
stället för i `/tmp`, med samma överskrivningsskydd som desktopacceptansen:
evidens som git redan bär skrivs aldrig över utan `--overwrite-evidence`.

| Vy | Fil |
| -- | -- |
| tom kö | `fakturor-invoice-queue-empty.png` |
| ärendet efter inläsning | `fakturor-invoice-case.png` |
| citatet öppnat på rätt sida | `fakturor-invoice-citation.png` |
| ärendet efter mänskligt arbete | `fakturor-invoice-case-worked.png` |
| förändringen mot föregående faktura | `fakturor-invoice-change.png` |
| analyshistoriken, två versioner | `fakturor-invoice-analysis-history.png` |
| den ersatta versionen | `fakturor-invoice-replaced-version.png` |
| **kreditfakturan** | `fakturor-invoice-credit.png` |
| kön med fyra arbetade ärenden | `fakturor-invoice-queue.png` |
| maskinläsbart kvitto | `fakturor-invoice-acceptance.json` |

Den provisionerade `XDG_DATA_HOME` ligger medvetet **inte** i evidensträdet:
evidens committas, en förenings butik gör det inte.

## Den sammanslagna körningen, och vad den visade

`make desktop-acceptance-full` kördes med tunneln till agenntserver uppe.
**Fakturaresan gick grön i den sammanslagna körningen**, och namngivningen höll:
`fakturor-invoice-*` och `fakturor-desktop-*` skrev aldrig över varandra.

Den fulla desktopresan **tajmade ut** i det kedjade körfallet, på steget "en
daterad kandidat från den levererade motorn" i Bevakningar (180 s). Det är inte
en följd av arbetet här, och det kontrollerades i stället för att antas:

| Körning | Utfall |
| -- | -- |
| `desktop-acceptance` direkt efter fakturaresan (kedjad) | tajmade ut på arkivskanningen |
| `desktop-acceptance` ensam, på **ren HEAD** utan det här arbetet | grön |
| `desktop-acceptance` ensam, med hela det här arbetet i trädet | **grön** |
| bevakningsmotorn körd direkt mot samma PDF, in-process | ger kandidaten `2027-07-31`, som väntat |

Slutsatsen är att steget är tidskänsligt när en full resa körs omedelbart efter
en annan, inte att något i fakturaarbetet påverkar Bevakningar — ingen fil som
rörts här ligger i den vägen. Det är ett känt, oundersökt flakighetsfall i
desktopacceptansens bevakningssteg och ligger utanför det här arbetets omfång.
Kör resan ensam om den kedjade körningen tajmar ut.

## Gränsen som inte flyttades

Fortnox-integrationen är kontrakts- och fixturverifierad. **Ingen körning mot
ett skarpt Fortnox-konto har gjorts i det här repot** — fältnamn och sidformer
kommer ur API-dokumentationen, inte ur observerad trafik. Hela
gränsdragningen står i
[INTEGRATION-FORTNOX.md](../INTEGRATION-FORTNOX.md#vad-som-är-verifierat--och-vad-som-inte-är-det).

`ensure_cases`-vägen och revisionshistoriken behandlas som färdiga inom den
enprocessarkitektur backenden har; den kända gränsen (två *processer*) står
oförändrad i [FAKTUROR.md](../FAKTUROR.md) §5 och är inte något den här
körningen påstår sig ha stängt.
