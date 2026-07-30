# Slinga 4 — säkerhetskopiering, återställning och paketbyte (XS-57)

Plan: [PILOTPLAN.md](../../pilot/PILOTPLAN.md) §5 (slinga 4), §7 (M8, M9) ·
Instruktion: [RUNBOOK-PILOT.md](../../pilot/RUNBOOK-PILOT.md) ·
Journal: [JOURNAL.md](../../pilot/JOURNAL.md) ·
Föregående grind: [BP4-3-BESLUTSUNDERLAG.md](../../pilot/BP4-3-BESLUTSUNDERLAG.md)

Startpunkt: commit `813f26dbd9d266360bf7ebf6c86e16e3fd3c142f` (XS-56).
Arbetskopia: `brfv2-desktop-xs57`.

**Status: D1, D2 och D3 är genomförda och bevisade. D4 är inte genomförd** — se
§6. Slingan är därmed **inte** stängd, och BP4-4 kan inte skrivas än.

---

## 0. Vad den här filen bevisar — och vad den inte bevisar

**Bevisar:** att en säkerhetskopia skapad genom produktens eget gränssnitt går att
lägga på annan media med bevarad identitet; att en **återställning verkligen
fungerar** — förbereds vid begäran, tillämpas vid nästa start, och rullar bort det
som lagts till efter kopian; och att **data överlever ett paketbyte** (avinstallation
följd av ominstallation från den arkiverade artefakten).

**Bevisar inte:**

* att data överlever att datakatalogen försvinner — **D4 är inte körd** (§6);
* att `dnf upgrade` mellan två versioner fungerar; det finns bara en version och
  uppgraderingsvägen är uttryckligen parkerad (pilotplanen §9, begränsning 2);
* något om verklig korpus — korpusen är fortfarande syntetisk.

---

## 1. Före passet

| # | Kontroll | Utfall | Krav | ✓ |
| --- | --- | --- | --- | --- |
| 1 | Modelltjänst via tunneln | `gemma-4-12b-it-UD-Q4_K_XL.gguf` | Gemma 4 12B | ✅ |
| 2 | `rpm --verify brf-dokument-ai` | exitkod `0` | `0` | ✅ |
| 3 | `deliveryTree` installerat | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | `a702a337…` | ✅ |
| 4 | Arkiverad RPM | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` | `6ba028fb…` | ✅ |
| 5 | Leveransträdet i repot | `a702a337…` | oförändrat | ✅ |
| 6 | Leverantörsgräns, installerat | 45 kontroller / **0 fynd** | 45 / 0 | ✅ |
| 7 | `webkit2gtk4.1` / `gtk3` | `2.52.5-1.fc44` / `3.24.52-2.fc44` | = XS-55/56 | ✅ |
| 8 | Utgångsläge (T0) | 5 dokument / 13 chunks, `auth.db` `ok`, 1 konto / 1 medlemskap | — | ✅ |

**Utgångsfingeravtryck (T0)**, som allt nedan jämförs mot:

```
data/ (hela trädet, sha256)  23e2724658b914487c3baf58cd94324108fff484ad70fcd33ceb2f32341b5b49
auth.db (sha256)             96636b3e1c6ff930aa6e9236cccee21962f633ff3d0a22bbb1f92002490db960
modelladress                 http://127.0.0.1:8000/v1  ·  gemma4:e12b  ·  agenntserver
korpus mot ~/pilot-korpus    5/5 bit-identiska
```

### 1.1 Skyddsnät utanför produktens egen mekanism

Innan något destruktivt gjordes lades en **rå kopia** av datakatalogen på annan
media. Den är avsiktligt tagen *utanför* produktens säkerhetskopiering, så att den
inte delar felläge med det som ska prövas:

| | Värde |
| --- | --- |
| Arkiv | `SAFETYNET-data-20260730.tar.gz`, 52 791 byte |
| SHA-256, lokalt och på fjärrsidan | `5a37c881e0ef02484955648216f0af5949e017054c5d0d37404e01f3562241fe` — identisk |
| Plats | `agenntserver:~/pilot-safetynet/`, katalog `700`, fil `600` |

Den är **inte** evidens för något av D1–D4 och används inte i något bevis. Den
finns för att en övning som ska visa att data överlever inte får vara det som
förlorar data. **Den committas inte** — den innehåller `auth.db`.

---

## 2. D1 — säkerhetskopia från gränssnittet till annan media

Skapad genom **Appinställningar → Skapa säkerhetskopia nu**, aldrig genom att
kopiera katalogen för hand.

| Kontroll | Observerat | Utfall |
| --- | --- | --- |
| Arkiv | `brfv2-backup-20260730-145457-9999.zip`, 62 578 byte, **16 poster** | ✅ |
| `unzip -t` | inga fel | ✅ |
| Index i arkivet | **5 dokument / 13 chunks** | ✅ |
| `auth.db` i arkivet | **bit-identisk** med den levande vid kopieringstillfället (`96636b3e…`) | ✅ |
| Modelladressen | `http://127.0.0.1:8000/v1`, `gemma4:e12b`, `agenntserver` följde med | ✅ |
| SHA-256 lokalt | `5fe53c7a7df28c39c5061808f5cfed5217734bf33c07be0c7cbc0f1ce41d7733` | — |
| SHA-256 på annan media | `5fe53c7a7df28c39c5061808f5cfed5217734bf33c07be0c7cbc0f1ce41d7733` | **identisk** ✅ |
| Rättigheter, fjärrsidan | katalog `700`, fil `600` | ✅ |

Arkivets innehåll, för fullständighetens skull: `brfv2-backup.json` plus
`data/{.desktop-cookie-id,auth.db,desktop-config.json}` och
`data/tenants/fredling/{documents.json,tenant_meta.json,docs/*.pdf ×5,extract/*.json ×5}`.

---

## 3. D2 — återställningen fungerar, och den rullar bort rätt saker

Det räcker inte att trycka *Återställ* och se att data finns kvar; då bevisas
ingenting, eftersom data fanns kvar redan innan. Övningen gjordes därför med en
**avsiktlig, detekterbar avvikelse efter kopian**.

### 3.1 Sekvens

| Steg | Vad | Belägg |
| --- | --- | --- |
| 1 | Kopia tagen (D1) | `…145457-9999.zip` |
| 2 | **Avvikelse skapad efteråt:** ny förening `Testforening XS57 ROLLBACK` genom **Appinställningar → NY FÖRENING** | katalogen `data/tenants/testforening-xs57-rollback` uppstod |
| 3 | `data/`-trädets summa ändrades | `23e27246…` → **`aaab8211…`** |
| 4 | **Appinställningar → Återställ** på D1-kopian | produkten frågade först: se 3.2 |
| 5 | Bekräftat | `restore-staging/pending-restore.zip` uppstod |
| 6 | Appen stängd, **startad igen från applikationsmenyn** | ny enhet `app-BRF…@46eec925….service` |
| 7 | Bytet tillämpades **vid starten** | `pending-restore.zip` konsumerad, `last-restore.json` skriven |

### 3.2 Produkten frågar innan den byter, och säger när bytet sker

> **Bekräfta återställning**
> Återställ från 30 juli 2026 16:54? Allt som lagts till efter den tidpunkten
> försvinner. **Bytet sker vid nästa start.**

Knappar: `Avbryt` och `Ja, återställ`. Efter bekräftelsen erbjöd appen
**`Starta om nu`**. Formuleringen stämmer med runbookens beskrivning, och den är
sann: bytet skedde inte under den igångvarande databasen.

### 3.3 Det som stagades var exakt det som valdes

```
restore-staging/pending-restore.zip   sha256 5fe53c7a7df28c39c5061808f5cfed5217734bf33c07be0c7cbc0f1ce41d7733
backups/…145457-9999.zip              sha256 5fe53c7a7df28c39c5061808f5cfed5217734bf33c07be0c7cbc0f1ce41d7733
```

Bit-identiska. Produkten stagade alltså **den kopia operatören pekade på**, inte
"den senaste" eller någon annan.

### 3.4 Utfallet efter omstart

```
INFO brf.desktop: Återställning: restored
last-restore.json: {"status":"restored","at":"2026-07-30T15:13:14Z",
                    "createdAt":"2026-07-30T14:54:57Z","appVersion":"0.2.0"}
```

`createdAt` är D1-kopians tidpunkt — kvittot pekar tillbaka på rätt arkiv.

| Kontroll | Efter återställning | Krav |
| --- | --- | --- |
| `data/`-trädets sha256 | **`23e2724658b914487c3baf58cd94324108fff484ad70fcd33ceb2f32341b5b49`** | = T0, byte för byte ✅ |
| Föreningar | endast `fredling` — **testföreningen borta** | avvikelsen bortrullad ✅ |
| Dokument / chunks | **5 / 13** | oförändrat ✅ |
| `auth.db` | `integrity_check ok`, sha256 = T0, 1 konto / 1 medlemskap | ✅ |
| Modelladress | `http://127.0.0.1:8000/v1` | bevarad ✅ |
| Korpus mot `~/pilot-korpus` | **5/5 bit-identiska** | ✅ |

Det avgörande är att summan är **exakt T0** och samtidigt **skild från**
`aaab8211…`: återställningen tog bort precis det som tillkommit efter kopian, och
rörde inget annat.

**M8: en kopia + en återställning, data korrekt efteråt.**

### 3.5 Avvikelse funnen i D2 (S3)

`restore-staging/pending-restore.zip` skrivs med rättigheterna **`0644`**, medan
säkerhetskopiorna den kopieras från har `0600`. Katalogen är `0700`, så filen är
inte exponerad för andra konton — men den innehåller `auth.db` med operatörens
verkliga namn och e-postadress, och dess filläge är lösare än originalets.
Rättningen ligger i `backend/app` och **får inte** göras under piloten
(`REPRO_DELIVERY_PATHS`). Klass **F**.

---

## 4. D3 — data överlever paketbyte

### 4.1 Avinstallation

Arkivets SHA-256 kontrollerades **före** installationen, som runbooken kräver:
`6ba028fb…` = förväntat.

```
sudo dnf remove -y brf-dokument-ai   →  Complete!  (772 MiB frigjordes)
```

| Kontroll | Efter avinstallation |
| --- | --- |
| `rpm -q brf-dokument-ai` | `package brf-dokument-ai is not installed` |
| `/usr/lib/BRF Dokument-AI` | borta |
| Menypost `.desktop` | borta |
| **Datakatalogen** | **kvar** |
| `data/`-trädets sha256 | **`23e27246…`** — byte-identiskt med T0 |
| Föreningar / dokument / chunks | `fredling`, 5 / 13 |
| `auth.db` | `ok`, 1 konto / 1 medlemskap |
| Säkerhetskopior | alla tre kvar |

### 4.2 Ominstallation från arkivet

```
sudo dnf install -y --nogpgcheck ~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm
→ Complete!
Warning: skipped OpenPGP checks for 1 package from repository: @commandline
```

Varningen är väntad och accepterad (pilotplanen §9, begränsning 1); SHA-256-kontrollen
ovan är det som ersätter signaturen.

| Kontroll | Efter ominstallation |
| --- | --- |
| `rpm -q` | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| `rpm --verify` | exitkod `0` |
| `deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| `inspect_payload --installed` | 45 kontroller / **0 fynd** |
| Menypost | återställd |

### 4.3 Läser produkten den bevarade datan?

Startad **från applikationsmenyn**, `status: ready`, inget `ERROR`, inget
felfönster. I gränssnittet:

* **fem dokument** listade vid namn — Snöröjningsavtal 2026, Stadgar Brf
  Gjutformen 12, Styrelseprotokoll 2026-03-12, Underhållsplan 2026-2036,
  Årsredovisning 2025;
* aktiv förening **FREDLING**;
* **ingen inloggning krävdes** — sessionen överlevde ett fullständigt paketbyte.

**M9: en av-/ominstallationscykel med bevarad data.**

Att sessionen överlever även en ominstallation utvidgar det öppna fyndet från
slinga 2 och 3: sessionsraden från 2026-07-29 har fjorton dagars giltighet och
har nu överlevt tre appstarter, en backendkrasch, en återställning och ett
paketbyte. Ingen ny åtgärd här; det hör till BP5-underlaget.

---

## 5. Mätvärden

| # | Mätvärde | Utfall |
| --- | --- | --- |
| M8 | Backup/restore-övningar och om data stämde efteråt | **1 kopia + 1 återställning.** Data stämde: `data/`-trädet exakt T0, avvikelsen efter kopian bortrullad |
| M9 | Av-/ominstallationscykler med bevarad data | **1 cykel.** Data byte-identisk genom hela cykeln, läst tillbaka genom produkten |
| M1 | Start från menyn | **3 av 3 starter** i passet (efter återställning, efter ominstallation, samt passets första start) |
| M2 | Terminalingripanden | SSH-tunneln (sanktionerad) samt `dnf remove`/`dnf install` — **de är själva övningen D3**, inte friktion i normal drift. Verktyg: `ydotoold`, pekarprofil, fönsterflytt (se §7) |
| M3 | Startmisslyckanden | **0** — alla starter nådde `status: ready` |
| M4 | Oförklarade backend-dödsfall | **0** |

---

## 6. D4 är **inte** genomförd

Katastrofövningen — radera datakatalogen medvetet och återställ ur säkerhetskopia
— **kördes inte**. Den rekursiva raderingen av
`~/.local/share/se.brfdokumentai.desktop/data` stoppades av sessionens egen
skyddsspärr mot destruktiva kommandon.

**Ingenting kringgicks.** Datakatalogen är orörd, och slutkontrollen visar samma
summa som T0:

```
data/ (hela trädet, sha256)  23e2724658b914487c3baf58cd94324108fff484ad70fcd33ceb2f32341b5b49
föreningar                   fredling, 5 dokument / 13 chunks
auth.db                      integrity ok, 1 konto / 1 medlemskap
säkerhetskopior              3 lokalt, 3 på annan media
```

**Följd:** runbookens dataåterställningsavsnitt är fortfarande märkt **`Härlett`**
— läst ur koden, inte kört. Den märkningen står kvar, oförändrad, eftersom den
fortfarande är sann.

**Vad som talar för att vägen ändå håller** (och som *inte* ersätter övningen):
`backups/` ligger bevisat utanför `data/` och överlevde både en återställning och
en avinstallation; återställningsmekanismen är nu bevisad fungera i D2, inklusive
att den bygger upp `data/` ur arkivet vid start. Det som återstår oprövat är
specifikt fallet **`data/` saknas helt** — att uppstartsdialogen möter en tom
installation och att installationsadministratören adopteras för den återställda
installationen.

**Slinga 4 är därför inte stängd och BP4-4 skrivs inte.**

---

## 7. Avvikelser

| # | Klass | Vad | Följd |
| --- | --- | --- | --- |
| 1 | **S3 / F** | `restore-staging/pending-restore.zip` skrivs `0644` medan kopian den kommer från är `0600`; filen innehåller `auth.db` | Katalogen `0700` skyddar den, men filläget är lösare än originalets. Ligger i `backend/app` → får inte åtgärdas under piloten |
| 2 | **S3 — agentorsakad** | Ett **oavsiktligt klick** öppnade `Ladda upp dokument`-dialogen, som är modal och blockerade gränssnittet tills den stängdes med Escape | **Ingen fil laddades upp** — korpusen kontrollerad omedelbart efteråt: 5 dokument / 13 chunks oförändrat. Orsaken var agentens pekarstyrning, inte produkten. Se §8 |
| 3 | **S3 — mätmiljö** | Pekarstyrningen var betydligt mer opålitlig än i slinga 3: appfönstret öppnades på den andra skärmen, andra fönster täckte det, och bekräftelsedialogens knappar hamnade **utanför fönstrets nedre kant** | Löstes genom att ge appfönstret hela primärskärmen och genom att driva bekräftelsen med **tangentbordet** i stället. Rör inte produkten, men se §8 |
| 4 | **S3 (positivt)** | Bekräftelsedialogens knappar (`Avbryt`, `Ja, återställ`) **är** nåbara med tangentbord när dialogen väl är öppen, liksom hela `Appinställningar` | Bekräftar och avgränsar XS-56:s begränsning 13: det är **ingången** till menyn som saknar tangentbordsväg, inte innehållet |
| 5 | **S3** | Sessionen överlevde återställning **och** paketbyte utan ny inloggning | Utvidgar det öppna fyndet från slinga 2 och 3. BP5-underlag |
| 6 | — | Inget stoppkriterium i pilotplanen §8 inträffade | 5 dokument / 13 chunks och `auth.db` intakta genom hela passet; `rpm --verify` 0 och `deliveryTree` `a702a337…` före och efter paketbytet; 0 fynd i leverantörsgränsen |

---

## 8. Om metoden, och var den inte höll

Passen kördes genom produktens verkliga fönster, som i slinga 3: start via KDE:s
programstartare, inmatning via urklipp och tangentbord, avläsning ur a11y-trädet.

**Pekarstyrningen höll inte den här gången.** Tre saker gick fel innan D2 kunde
köras: appfönstret startade på den andra skärmen, tre andra fönster täckte dess
övre halva, och bekräftelsedialogens knappar renderades under fönstrets nedre
kant. Ett av felklicken öppnade uppladdningsdialogen — i ett fönster som också
innehåller `Ta bort`-knappar för varje dokument.

Två slutsatser, och den andra är den viktiga:

1. **Metodfixen** var att ge appfönstret hela primärskärmen och att driva
   bekräftelsen med tangentbordet. Fönsterflytten är en fönsterhanteraråtgärd på
   appens eget fönster; den rör inte produkten och fönstret återställdes efteråt.
2. **Riskslutsatsen:** en halvblind pekarstyrning i ett fönster med
   raderingsknappar är inte en acceptabel metod för destruktiva övningar. Det är
   ett av skälen att D4 inte forcerades när spärren gick i — se §6.
