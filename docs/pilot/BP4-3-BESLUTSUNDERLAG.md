# BP4-3 — beslutsunderlag

**Grind:** Genomförande → BP4-3, *avstämning efter slinga 3.*
**Datum:** 2026-07-30. **Uppgift:** XS-56.
**Underlag:** [PILOTPLAN.md](PILOTPLAN.md) §5, [JOURNAL.md](JOURNAL.md),
[`slinga3-upprepade-arbetspass.md`](../evidence/pilot/slinga3-upprepade-arbetspass.md),
[`EVIDENSREGISTER-XS56.md`](../evidence/pilot/EVIDENSREGISTER-XS56.md).

Agenten sammanställer, människan beslutar. **Ingenting nedan är ett beslut.**

---

## 1. Vad grinden ska fastställa

Att **produkten beter sig som acceptansen lovar även utanför acceptansens
isolerade `XDG_DATA_HOME`** — i pilotens egen installation, med pilotens egen
data, över upprepade pass. Inte att produkten är färdig, inte att korpusen är
verklig, inte att slinga 4:s frågor är besvarade.

## 2. Vad slingan skulle göra demonstrerbart, och vad som observerades

| # | Arbete | Utfall | Belägg |
| --- | --- | --- | --- |
| C1 | Upprepade arbetspass enligt sessionsrutinen, journalförda | **Uppfyllt** — tre pass, fyra menystarter, M1–M7 per pass | journalen; evidensfilen §3, §4, §5 |
| C2 | Uppsättningen körd per pass, jämförd mot baslinjen | **Uppfyllt** — tre körningar, identiskt utfall: 10/10 · 2/2 · 3/3 · 0 fabricerade | maskinläsbara svar i `docs/evidence/pilot/xs56/`; evidensfilen §3.2, §4.4, §5.7 |
| C3 | Tunneln stängd mitt i ett pass | **Uppfyllt** — vägran med leverantörsfel, noll citat, inget påhittat svar | evidensfilen §4.2–4.3 |
| C4 | Backendprocessen dödad | **Uppfyllt** — arbetsfönstret stängdes, produktens eget felfönster namngav `signal 15`, data och loggar bit-identiska | evidensfilen §5.2–5.6 |
| C5 | Omkörning om `webkit2gtk4.1`/`gtk3` bytt version | **Utlöstes inte** — båda oförändrade sedan slinga 1 | evidensfilen §1, punkt 6–7 |

**Mätvärdena över de tre passen:** M1 4/4 menystarter · M2 **0** ingripanden som
krävdes för att använda produkten · M3 0/0/0 · M4 0 oförklarade · M5 10/10 ×3 ·
M6 0 ×3 · **M7 0 ×3**, med 42 av 42 citat lösta mot extraherad sidtext.

**Artefakten är orörd:** RPM `6ba028fb…`, `deliveryTree` `a702a337…` (installerat
*och* i repot), `rpm --verify` = 0, leverantörsgränsen 45 kontroller / **0 fynd**,
index 5 dokument / 13 chunks — före och efter alla tre passen och båda
injektionerna.

**Inget stoppkriterium i §8 inträffade.** Alla sju prövades var för sig
(evidensfilen §7.1). Särskilt kriterium 2: samtliga URL:er i produktens loggar är
`http://127.0.0.1:8000` — ingen annan värd kontaktades ens när leverantören föll
bort.

## 3. Rekommendation

**Rekommendation: passera BP4-3 och påbörja slinga 4 (XS-57).**

Skälet är inte att utfallet var bra, utan att det var **reproducerbart och
förklarat**: tre pass gav identiskt resultat ned till vilka två frågor som blir
överinkluderande, båda felinjektionerna gav säkert beteende med namngiven orsak,
och varje avvikelse har ett belägg i stället för en gissning.

## 4. De fyra sakerna grinden bör **besluta** om

De tre första har agenten redan **verkställt som dokumentändring** där ändringen
inte är ett omdöme — grinden bör bekräfta eller riva dem. Den fjärde är
**oförändrad och kräver ett beslut**.

### 4.1 Rättelsen av g24 och metodregeln — *verkställd, bör bekräftas*

Slinga 2:s baslinje godkände `Driftia Fastighetsservice AB` som svar på frågan om
**ekonomisk** förvaltning. Driftia är teknisk förvaltare; facit är `SBC Sveriges
BostadsrättsCentrum AB`. Citatet löste — ordet `Driftia` står på den citerade
sidan — men svaret var fel.

Gjort: raden är **rättad i journalen med den ursprungliga bedömningen kvar**, och
baslinjens fragment-fakta är därmed **9 av 10**, inte 10 av 10. Regeln som
förhindrar upprepning står nu i §6.3: *citatupplösning och svarsriktighet är två
kontroller och båda måste hålla*.

Varför agenten verkställde den: att Driftia är teknisk och SBC ekonomisk förvaltare
är läsbart ur sidans text, inte en bedömningsfråga; och regeln **höjer** ribban,
vilket är den riktning §6 tillåter utan att bli efterrationalisering.

**Att besluta:** bekräfta rättelsen och regeln — eller avvisa dem med skäl.

### 4.2 `M4`-definitionen — *verkställd, bör bekräftas*

§7 sade "oväntade" backend-dödsfall, §8:s stoppkriterium 7 säger "oförklarade".
Skillnaden avgör när piloten stoppas. Tre fall har nu inträffat på riktigt:
oförklarat dödsfall (räknas), värdorsakad avslutning (slinga 2, räknas inte),
avsiktlig injektion (slinga 3, räknas inte). Definitionen med de tre fallen står
nu under §7:s tabell, med kravet att ett dödsfall som *inte* räknas ändå
journalförs med sitt belägg.

**Att besluta:** bekräfta — eller formulera om.

### 4.3 Tangentbordsotillgängligheten — *klassad som förslag, bör fastställas*

`Appinställningar` kan inte nås med tangentbordet: fokusringen är en sluten cykel
om sex element och menyns ingång saknar `tabIndex`
(`brfv2-mockup/src/App.jsx:863`). En tangentbordsberoende operatör kan varken
probe:a modelltjänsten, byta modelladress eller skapa säkerhetskopia.

Gjort: införd som **begränsning 13** i §9 med klass **A + F** — accepterad för
den här piloten (en operatör, med mus), uppföljning krävd innan produkten släpps
till någon som inte kan använda mus. Den ligger i `REPRO_DELIVERY_PATHS` och
**får inte** åtgärdas under piloten.

**Att besluta:** är `A + F` rätt klass, eller är det en **M** som ska tvinga en
artefaktändring före fortsatt pilot? Agentens uppfattning är `A + F`, eftersom
piloten har exakt en operatör som bevisligen kan använda mus — men konsekvensen
för en framtida användare är reell och beslutet är inte agentens.

### 4.4 Villkoret för obesvarbara frågor — **oförändrat, kräver beslut**

Villkoret är i dag `OTILLRÄCKLIGT UNDERLAG` **och noll citat**. Slinga 2 gav för
u05 ett kvalificerat icke-svar *med stött citat* och räknades som 2 av 3; slinga 3
gav noll citat i alla tre passen och därmed 3 av 3.

Frågan: **ska ett kvalificerat icke-svar med stött citat räknas som godkänt?**

| Alternativ | Talar för | Talar mot |
| --- | --- | --- |
| **Behåll** "noll citat" | entydigt mätbart; ett citat på en obesvarbar fråga inbjuder operatören att läsa svaret som grundat | straffar ett beteende som i slinga 2 var sakligt korrekt och hjälpsamt |
| **Tillåt** kvalificerat icke-svar med stött citat | speglar vad en kunnig människa skulle svara; citatet var verifierat | villkoret blir svårare att mäta, och gränsen mot "grundat-utseende svar" (stoppkriterium 4) blir suddig |

**Agenten har medvetet inte ändrat villkoret**, eftersom §6 finns för att hindra
att en utvärdering formas efter sitt resultat, och den som körde testet är den
sämst lämpade att avgöra detta. Beslutet är grindens.

## 5. Vad rekommendationen **inte** vilar på

* **Korpusen är syntetisk.** Ingenting i slinga 3 säger något om verkliga stadgar
  eller årsredovisningar.
* **Evidensklassen är agentkörning med verktygsstöd** genom produktens verkliga
  fönster — inte operatörsattestering. Slinga 2:s tangentbordssmoke (7 av 8, med
  Shift+Enter underkänt) är **inte** omprövad och står oförändrad.
* **Tre pass är tre pass**, inte veckor av drift.
* **Återställning är oprövad.** Säkerhetskopian från pass 3 är kontrollerad post
  för post och ligger på annan media med matchande SHA-256, men den har inte
  lästs tillbaka. Det är slinga 4:s första fråga.
* **Uppgraderingsvägen är parkerad** och berörs inte.

## 6. Kvarstående från tidigare grindar som slinga 3 inte stängde

| Från | Vad | Status efter slinga 3 |
| --- | --- | --- |
| Slinga 2 / B3 | **Shift+Enter skickar i stället för att radbryta**, klass F, får inte åtgärdas under piloten | Oförändrad. Blockerar fortfarande att B3 stängs som helt godkänd; beslutet om B3 med 7 av 8 tillhör BP4 |
| Slinga 2 | **Verkliga personuppgifter i installationen** (`auth.db`) mot pilotplanens rad *Personuppgifter → Inga* (§2) | Oförändrad och nu operativt hanterad: XS-56 committade ingen datakatalog och ingen säkerhetskopia, och kontrollerade mekaniskt att evidensen är fri från namn och e-post |
| Slinga 2 | `backend.log` **saknar tidsstämplar** | Oförändrad, och slinga 3 lade till ett näraliggande fynd: loggen innehåller ingen rad om backendens död |
| Slinga 2 | **Sessionen överlever** i fjorton dagar utan ny inloggning | Bekräftad och utvidgad: överlever nu även tre appstarter och en backendkrasch |
| Slinga 2 | `M10` mätt men ogiltigt | Inte ommätt; kräver en ny okonfigurerad installation, vilket slinga 3 inte gör |

## 7. Om grinden passerar — vad slinga 4 börjar med

Ingenting av detta är gjort, och inget av det påbörjades i XS-56:

* **D1** säkerhetskopia från UI:t till annan media — *delvis förberedd:* pass 3
  skapade `brfv2-backup-20260730-110753-c54d.zip` (16 poster, `unzip -t` rent,
  index 5/13) och kopierade den till `agenntserver:~/pilot-sakerhetskopior/` med
  katalog `700`, fil `600` och matchande SHA-256
  `e7fd00d42103789ecd767ebcd06349fc63b4612ab376a6a878055eae92381883`;
* **D2** återställ ur kopian och bekräfta att bytet sker vid start;
* **D3** avinstallera, bekräfta att datakatalogen ligger kvar, installera om från
  arkivet efter SHA-256-kontroll;
* **D4** katastrofövningen — radera datakatalogen medvetet och återställ. Den
  vägen är i dag **`Härlett`**, läst ur koden men aldrig körd.

**D3 och D4 är destruktiva** och rör pilotens enda installation och enda
datakatalog. De bör inte påbörjas på en muntlig impuls, utan efter att den här
grinden är skriven och en operatör uttryckligen släppt fram dem — vilket är
precis vad pilotplanen §5 menar med att nästa slinga börjar när föregående BP4 är
skriven.
