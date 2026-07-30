# BP4-4 — beslutsunderlag

**Grind:** Genomförande → BP4-4, *avstämning efter slinga 4 — den sista i
pilotens fyra slingor.*
**Datum:** 2026-07-30. **Uppgift:** XS-57.
**Underlag:** [PILOTPLAN.md](PILOTPLAN.md) §5, §7 · [JOURNAL.md](JOURNAL.md) ·
[`slinga4-sakerhetskopiering-och-paketbyte.md`](../evidence/pilot/slinga4-sakerhetskopiering-och-paketbyte.md) ·
[RUNBOOK-PILOT.md](RUNBOOK-PILOT.md) · föregående grind:
[BP4-3-BESLUTSUNDERLAG.md](BP4-3-BESLUTSUNDERLAG.md)

Agenten sammanställer, människan beslutar. **Ingenting nedan är ett beslut.**

---

## 1. Vad grinden ska fastställa

Att **data överlever både operatörsmisstag och paketbyte**. Inte att produkten är
redo för bred distribution, inte att uppgraderingsvägen fungerar, och inte något
om verklig korpus.

## 2. Vad slingan skulle göra demonstrerbart, och vad som observerades

| # | Arbete | Utfall | Belägg |
| --- | --- | --- | --- |
| D1 | Säkerhetskopia från UI:t, kopierad till annan media | **Uppfyllt** — 16 poster, `unzip -t` rent, index 5/13, `auth.db` bit-identisk med den levande, matchande SHA-256 på annan media, `0700`/`0600` | evidensfilen §2 |
| D2 | Återställ ur kopian; bytet sker vid start och data stämmer efteråt | **Uppfyllt** — prövad mot en avsiktlig avvikelse skapad *efter* kopian; produkten stagade bit-identiskt arkiv, bytte vid start, och trädet återgick **exakt** till utgångssumman | evidensfilen §3 |
| D3 | Avinstallera, bekräfta att datakatalogen ligger kvar, installera om från arkivet, bekräfta att data läses | **Uppfyllt** — data byte-identisk genom hela cykeln, artefaktidentiteten återställd, fem dokument lästa tillbaka genom produkten | evidensfilen §4 |
| D4 | Katastrofövning: datakatalogen borta, återställ ur kopia | **Uppfyllt med förbehåll om metod** — frånvaron åstadkoms genom **karantänflytt**, inte radering av bytes; produkten mötte en tom installation och återställde till exakt utgångsläget | evidensfilen §9 |

**Mätvärden:** **M8 = 1 kopia + 2 återställningsövningar** (D2 och D4), båda med
korrekt data efteråt. **M9 = 1 av-/ominstallationscykel** med bevarad data.

**Artefakten är orörd genom hela slingan:** RPM `6ba028fb…`, `deliveryTree`
`a702a337…` (installerat och i repot), `rpm --verify` = 0, leverantörsgränsen
45 kontroller / **0 fynd**.

**Inget stoppkriterium i §8 inträffade.**

## 3. Det enda som gör D4:s bevis svagare än det ser ut

D4 bevisar att produkten återhämtar sig när **den förväntade aktiva
`data/`-sökvägen är helt frånvarande**. Den bevisar **inte** beteendet när bytes
fysiskt raderas, eftersom katalogen flyttades till karantän i stället för att
raderas.

Skillnaden är liten men den är verklig, och den ska stå i BP5-underlaget som den
står här: för produkten är driftvillkoret identiskt — `open()` på sökvägen
misslyckas likadant — men fallet "filsystemet har återanvänt blocken" är inte
prövat. Metoden valdes av ett skäl som också hör till beslutet: den kräver inte
att agentens spärr mot rekursiv radering kringgås.

**Att besluta:** räcker karantänmetoden som bevis för D4, eller ska övningen
göras om med verklig radering av en engångsinstallation innan BP5?
Agentens uppfattning är att den räcker för *pilotens* syfte och bör noteras som
förbehåll i BP5 — men det är inte agentens beslut.

## 4. Fynd från slingan som grinden bör ta ställning till

### 4.1 `restore-staging/pending-restore.zip` skrivs `0644`

Kopian den kommer från är `0600`, och filen innehåller `auth.db` med operatörens
verkliga namn och e-postadress. Katalogen är `0700`, så den är inte läsbar för
andra konton — men filläget är lösare än originalets utan att något kräver det.
Ligger i `backend/app` och **får inte** åtgärdas under piloten.

**Att besluta:** klass **F** (uppföljning efter piloten) — eller strängare?

### 4.2 Sessionen överlever allt som prövats

Fjorton dagars giltighet, och den har nu överlevt tre appstarter, en
backendkrasch, en återställning, ett paketbyte **och** en fullständig
återuppbyggnad av `data/`. Efter D4:s återställning var installationen inloggad
igen utan att någon behövde kunna lösenordet.

Det är inget fel mot skriven kravbild, men för en produkt vars poäng är att data
stannar lokalt hör det hemma i BP5-underlaget.

**Att besluta:** ska sessionslängden ändras före en bredare pilot, eller
uttryckligen accepteras för en enanvändarmaskin?

### 4.3 Karantänkopians disposition

`~/pilot-quarantine-xs57/data-20260730-xs57-d4`, `0700`, 15 filer, trädsumma
`23e27246…`, utanför Git, klassad som identitetsbärande.

**Behålls tills vidare.** Radering kräver uttryckligt tillstånd, som inte har
givits. Den är i praktiken en tredje återställningspunkt utöver de tre
säkerhetskopiorna och skyddsnätskopian.

**Att besluta:** ska den raderas nu när aktiv data är verifierad, eller behållas
till efter BP5?

### 4.4 Kvarstående från BP4-3, oförändrat

Fyra punkter lämnades till BP4-3 och tre av dem verkställdes som
dokumentändringar; **villkoret för obesvarbara frågor** lämnades medvetet
oförändrat och är fortfarande obesvarat. Det påverkar inte slinga 4, men det är
fortfarande öppet inför BP5.

## 5. Rekommendation

**Rekommendation: passera BP4-4.** Slingans fyra övningar är körda, var och en med
belägg som inte vilar på produktens eget påstående: trädsummor före och efter,
bit-jämförelse mot korpusen, `auth.db`-summa, och ett grundat svar med citat löst
mot extraherad sidtext.

**Rekommendation i övrigt: gå *inte* direkt till BP5.** Två saker bör avgöras
först — D4:s metodförbehåll (§3) och det öppna villkoret från BP4-3 (§4.4) — och
BP5 kräver dessutom enligt pilotplanen §5 en **kall granskning av en fristående
session utan bygghistorik**. Den har inte gjorts.

## 6. Vad piloten som helhet nu har visat, och inte

**Visat:** att artefakten går att återställa från arkiv (slinga 1); att en
okonfigurerad maskin blir en fungerande installation utan terminalarbete utöver
tunneln (slinga 2); att produkten beter sig som acceptansen lovar över upprepade
pass och under två felinjektioner (slinga 3); och att data överlever
operatörsmisstag och paketbyte (slinga 4).

**Inte visat:** något om verklig korpus — den är syntetisk hela vägen; något om
andra maskiner, andra OS eller bred distribution; att `dnf upgrade` fungerar;
att en människa vid ett fysiskt tangentbord upplever samma sak som agenten gjorde
i slingorna 3 och 4; och att `Appinställningar` går att nå utan pekare
(begränsning 13).
