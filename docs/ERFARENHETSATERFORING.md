# Erfarenhetsåterföring — BRF Dokument-AI

**Gäller:** hela projektet från BP1 till det formella `PASS BP5` 2026-07-27
och den efterföljande handover-hygienen, granskat mot `main` vid
`37653d7679706edd5badd4fd7e8841c6b0f02d57`.
**Syfte:** fånga vad som materiellt bör ändra hur nästa BRF/RAG-leverans
scopas, byggs, verifieras och överlämnas — inte en generisk
retrospektivmall. Varje större lärdom nedan pekar på en commit, ett issue
eller ett reproducerat resultat.

## 1. Praxis som fungerade och bör upprepas

- **Tenant-isolering som separata objektgrafer, inte ett `WHERE`-villkor.**
  En `TenantRegistry` ger varje `brf_id` sin egen `Store` (eget
  filsystemsträd, egna chunkar, eget index) så att ingen kodväg *kan*
  returnera en annan tenants data — det finns ingen glömd
  `.filter(brf_id=...)` att glömma. En 18-attackers adversarial svit och en
  fristående fresh-context red-team lyckades inte korsa gränsen. Commit
  `6fb6cbe`/`07165c8`; evidens i
  [evidence/isolation-redteam.md](evidence/isolation-redteam.md) och
  [evidence/corpus-isolation.md](evidence/corpus-isolation.md).
- **404, inte 403, för en annan tenants resurser.** En 403 bekräftar att
  resursen finns; en 404 gör inte det. Existens är i sig information på en
  BRF:s skala (vem har dokument, hur många). Samma commit som ovan.
- **En meta-test som skyddar invarianten, inte bara dagens routes.** Arton
  isoleringstester bevisar att *dagens* routes är skyddade; en meta-test som
  vandrar varje `/api/brf/{brf_id}`-routes dependency-träd och fallerar om
  `tenant_store`/`require_admin` saknas gör "vi kom ihåg att skydda varje
  route" till en CI-kontroll i stället för ett granskningslöfte.
- **Bevisa negativ med en tripwire, inte ett påstående.** "Noll externa
  LLM-anrop" går inte att falsifiera genom kodläsning. En instrumenterad
  `socket.connect`-audit som hårdfallerar på icke-loopback/icke-LLM-
  anslutning gör påståendet till ett test som skriker om en framtida ändring
  når ut. Samma princip applicerades senare på PII: en regex-sökning över en
  diff missade en verbatim-tabellrad en människa hittade med ögat; fixen var
  att korsköra varje ≥4-ords-sekvens mot hela den extraherade korpustexten
  genom appens egen normaliserare, validerat med en injicerad positiv
  kontroll. Båda i `NOTES.md` (2026-07-16 resp. 2026-07-18).
- **Rekonstruera SPEC mot källorna och flagga drift explicit, i stället för
  att låtsas att inget ändrats.** [evidence/gate0-spec-drift.md](evidence/gate0-spec-drift.md)
  läste SPEC.md mot varje återvinnbar källa och namngav fem konkreta
  driftpunkter (gate-tal, en uppmjukad highlight-matchningsregel, en
  sida-korsande citatpolicy löst genom konstruktion, en tillagd
  Unicode-täckning, icke-sourcade defaultvärden) i stället för att tysta
  dem. Detta är den evidenshygien som gjorde senare gates pålitliga.
- **Oberoende kall granskning innan ett regulerat gate.** [XS-35](https://linear.app/ai-sprints/issue/XS-35/independent-cold-bp5-review-and-gate-recommendation)
  kördes i en fräsch session utan byggminne från [XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)
  och reproducerade hela produktresan självständigt innan den rekommenderade
  `PASS BP5`. Den hittade fyra konkreta, icke-blockerande fynd (se §4) som en
  självgranskning rimligen hade missat eller nedprioriterat — precis det
  mönster som Tonnquist-modellens "en agent godkänner aldrig sitt eget gate"
  är till för.
- **En providerabstraktion byggd tidigt gjorde en GPU-servermigrering till
  konfiguration, inte ombyggnad.** `BRF_LLM_BASE_URL` fanns redan som en
  en-rads-växel när [XS-30](https://linear.app/ai-sprints/issue/XS-30/koppla-in-gemma-4-12b-llamacpp-ubuntu-server-rtx-4070-via-ssh-tunnel)
  bytte från en lokal 4B-modell till en 12B-tjänst på en separat
  Ubuntu-server via SSH-tunnel. Ingen kod ändrades för att göra bytet möjligt.

## 2. Praxis som skapade omarbete eller falsk trygghet

- **En bättre rankare kan bryta en garanti den sämre rankaren höll av
  misstag.** Cross-encoder-rerankern löste exakt det diagnostiserade
  problemet (11/13 sanna tabellrader in i topp-6) och producerade samtidigt
  systemets **första felaktiga svar**: fyra verbatim-exakta citat på
  semantiskt fel rad. Recall allena hade läst detta som en vinst; det som
  visade att `rerankEnabled` måste förbli av var att mäta
  fel-rad-**introduktion** (0→4), inte återvunna frågor. Se
  [XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee)
  och `NOTES.md` (2026-07-19). **Lärdom:** för ett produkt vars kärnlöfte är
  "aldrig ett självsäkert fel svar" är rätt nyckeltal alltid
  fel-svar-introducerade, inte frågor-besvarade.
- **En poänggräns på rankarens egen score löste inte problemet ovan.** Den
  antagna fixen (droppa rankade chunkar under ett score-golv) motbevisades
  mätbart: score-fördelningarna för rätt rad och distraktor överlappar, och
  distraktorerna fick höga poäng. En golv-baserad grind hade dessutom
  droppat de flesta sanna raderna. Verifieringen förblev intakt hela tiden —
  felet var relevans, inte fabricering, och verbatim-verifiering skyddar
  bara mot det senare.
- **En hel anrikningsfas byggdes för att undvika en licensfråga som gick att
  testa om på en eftermiddag.** Rerankern som återvinner raderna blockerades
  bara av en CC-BY-NC-licens. I stället för att testa licensierbara
  alternativ direkt spenderades en fas på att anrika chunk-representationer
  för sökning — vilket gav **0 av 13** återvunna rader (dokumentårtal är
  konstant per dokument, sektionsrubriker är ortogonala mot frågevokabulär).
  Den direkta omtestningen (`cross-encoder/mmarco-mMiniLMv2`, Apache-2.0)
  tog en eftermiddag och löste blockeraren. **Lärdom:** när en spak bara är
  blockerad av licens, prisa det licensierbara alternativet **först**.
- **`brfv2-mockup/` låg som ett separat, gitignorerat repo fram till juli
  2026**, vilket gjorde att en ren klon av huvudrepot inte kunde köra
  produkten alls. Detta överlevde flera BP-gates innan [XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)
  (Opus 5, hög insats) upptäckte och löste det genom att göra katalogen till
  vanliga spårade filer (historiken finns kvar på
  `migration/brfv2-mockup/*`). Det här är den tydligaste "överlevde för
  länge"-instansen i hela projektet — se §4.

## 3. Återbrukat kontra genuint BRF-specifikt

BP2-beslutet ([Beslutslogg](https://linear.app/ai-sprints/document/beslutslogg-brfv2-663a4533845b))
var explicit: återbruka fungerande retrieval-/generationsteknik där rimligt,
men bygg BRF-specifik ingestion, tabellhantering, sida/bbox och
tenant-isolering. I efterhand höll den gränsen:

**Återbrukat/generellt** (från tidigare svenskt RAG-arbete, "Svensk Ragg"
enligt [XS-4](https://linear.app/ai-sprints/issue/XS-4/losningsval-aterbruk-vs-nybygge-vs-ragflow)):
hybrid retrieval-idén, flerspråkiga embeddings-tanken, den grundläggande
citat-verifieringsprincipen (verbatim-matchning mot källan).

**Genuint BRF-specifikt, och det som tog mest av projektets faktiska
utvecklingstid:**

- Multi-span-citat för fragmentfakta (org-nr, motpart, belopp utspridda över
  tabellceller) — en citat blev en **mängd** spans där alla måste
  verifieras, inte en enda sammanhängande mening. Detta krävdes för att
  BRF-dokument är tabelltunga på ett sätt generisk prosa inte är.
- Sida+bbox genom hela kedjan ([XS-9](https://linear.app/ai-sprints/issue/XS-9/metadataschema-sida-bbox-genom-hela-kedjan))
  och den strukturerade highlight-overlayn — inget i den återbrukade
  RAG-kärnan bar den datan.
- OCR-ingestion som en adapter in i **samma** verifieringskedja, inte en
  andra väg — motiverat av att en betydande andel BRF-dokument är skannade
  ([XS-16](https://linear.app/ai-sprints/issue/XS-16/bygg-brf-ingestion-docling-ocr-tabeller)).
- Tenant-isolering via separat objektgraf — inget i en enskild-tenant
  RAG-referens behövde lösa detta.
- Det egenutvecklade fel-rad-problemet (q_fee-klassen, §2) är specifikt för
  BRF-årsredovisningars tabellformat, inte ett generiskt RAG-problem.

**Reviderad bedömning:** ursprungsplanen underskattade hur mycket arbete
tabelltunga fragmentfakta och rankningsrelevans (inte bara "hitta rätt
dokument") skulle kräva — merparten av `NOTES.md`s tyngsta poster handlar om
just detta, inte om ingestion eller isolering som var svårare att förutse
fel på.

## 4. Konkreta exempel på antaganden/dokumentation som överlevde för länge

1. **`brfv2-mockup/` som separat nästlat repo** (§2). Root-README beskrev
   detta som arkitektur i flera veckor innan [XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)
   konsoliderade det. **Förebyggande regel:** en "ren klon kör produkten"-
   kontroll hör hemma redan vid första gatet efter att en andra kod-yta
   introduceras, inte vid slutgranskningen.
2. **macOS-specifik `brew install`-vägledning i `backend/scripts/ocr_spike.py`**
   överlevde värdmigreringen till Fedora tills [XS-35](https://linear.app/ai-sprints/issue/XS-35/independent-cold-bp5-review-and-gate-recommendation)s
   kalla granskning hittade den; löst i [XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery).
   **Förebyggande regel:** en plattformsmigrering (§5) bör inkludera en grep
   efter det gamla plattformsnamnet (`brew`, `Darwin`, macOS-sökvägar) över
   hela repot, inte bara de dokument som redan pekats ut.
3. **Icke-verbatim citering av en bevarad artefaktsträng** i ett
   evidensdokument — samma [XS-35](https://linear.app/ai-sprints/issue/XS-35/independent-cold-bp5-review-and-gate-recommendation)-fynd,
   löst i [XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery)
   genom att antingen citera exakt eller regenerera artefakten. **Förebyggande
   regel:** ett evidensdokument som citerar en körning ska citera den
   maskinellt (kopiera ur artefaktfilen), aldrig omformulera den för
   läsbarhet.
4. **Svag readiness-metadata** — `model_readiness.json` saknade tillräcklig
   självbeskrivning (konfigurerat modell-id, runtime-etikett, testad
   commit-SHA, UTC-tidsstämpel) och förlitade sig på kringtext för att pinnas
   till en körning. Löst i [XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery)
   genom att göra artefakten självattesterande. **Förebyggande regel:** varje
   maskinläsbar evidensartefakt ska bära sin egen provenance, inte förlita
   sig på ett omgivande dokument för att förbli sann efter en omkörning.
5. **"Ready" som konfigurationsstatus, inte attestering** — `/api/health`s
   `ready: true` betyder att en riktig provider är konfigurerad, inte att
   servern oberoende verifierats svara med rätt modell. Detta är inte fixat
   än ([XS-37](https://linear.app/ai-sprints/issue/XS-37/post-pilot-attest-the-actual-runtime-model-identity),
   parkerat post-pilot) men är uttryckligen dokumenterat i stället för att
   antas bort — se §6.

## 5. Modellrutt och effortval

Modellroutingen formaliserades i ett eget beslut sent i projektet
(Beslutslogg, 2026-07-27): Sonnet 5 som standard för implementation och
deterministisk verifiering; Opus 5 endast där dess omdöme materiellt
förändrar utfallet. De två faktiska Opus-användningarna i projektets
Linear-historik matchar den regeln i efterhand:

- **[XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)
  (Opus, hög insats)** — en öppen, tvärsystem-arkitekturfråga (konsolidera
  ett nästlat repo, migrera från Mac- till Fedora-antaganden över hela
  kodbasen) utan ett givet svar. Resultatet var en verklig
  arkitekturkorrigering, inte bara en bugfix.
- **[XS-35](https://linear.app/ai-sprints/issue/XS-35/independent-cold-bp5-review-and-gate-recommendation)
  (Opus, hög insats)** — en oberoende, kontradiktorisk gategranskning där
  granskaren uttryckligen inte fick reparera det den granskade. Detta är
  precis den "kall granskning"-roll som kräver ett fräscht, skarpt omdöme
  snarare än fortsatt bekantskap med koden.

**Var Sonnet var tillräckligt:** all löpande implementation (isolering,
citat-verifiering, ingestion, frontend), rutinmässiga evidensomkörningar
([XS-34](https://linear.app/ai-sprints/issue/XS-34/refresh-the-live-real-corpus-gate-after-xs-33)),
och hygienstädning efter en redan avslutad granskning
([XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery)).
Ingen av dessa krävde ett omdöme bortom "följ en tydlig kriterielista och
verifiera".

**Var extra verifiering hade varit slöseri:** anrikningsexperimentet
(§2) avgjordes genom en deterministisk offline-harness (ingen LLM) på
sekunder — en planerad live-körning mot 12B-modellen blev logiskt
överflödig eftersom båda armarna bevisligen skulle skicka identiska
prompts. Att ändå köra den live-passeringen "för säkerhets skull" hade
bränt GPU-tid på att bekräfta en redan avgjord slutsats. **Lärdom:** när en
offline, modellfri mätning kan avgöra frågan deterministiskt, kör den
i stället för nästa dyrare verifieringssteg.

**Ärlig lucka:** modellattribution finns bara för issues skapade eller
redigerade från ungefär 2026-07-27 och framåt ([XS-25](https://linear.app/ai-sprints/issue/XS-25/drift-forvaltningsplan),
[XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout)–[XS-37](https://linear.app/ai-sprints/issue/XS-37/post-pilot-attest-the-actual-runtime-model-identity)).
Den tidigare implementationsfasen (XS-1–XS-32, i praktiken hela kärnbygget)
har ingen registrerad modell/effort-nivå. Det går alltså inte att i
efterhand hävda vilken modell som byggde tenant-isoleringen eller
citat-kedjan — att gissa vore att fabricera evidens. **Regel för nästa
projekt:** registrera modell och effort på varje issue **från BP1**, inte
efter halva genomförandet, så att den här sortens retrospektiv faktiskt går
att skriva fullständigt.

## 6. Parkerade fynd — scope-beslut, inte projektmisslyckanden

- **[XS-21](https://linear.app/ai-sprints/issue/XS-21/efter-pilot-utvardera-token-for-token-sse-i-riktig-chat)
  — token-för-token SSE.** Den synkrona `POST /ask` bevisades tillräcklig
  för hela den definierade pilot-MVP:n (Playwright: fråga → svar → citat →
  PDF-sida → highlight, plus att föreningsbyte avbryter gammalt
  svarstillstånd). SSE är inte en blockerare för den bevisade resan; parkerat
  med tydliga villkor för framtida arbete (cancellation, tenantbyte utan sena
  events, citat först efter fullständig grounding).
- **[XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee)
  — q_fee/reranker.** Se §2. En licensierbar rankare löser återvinning men
  inte relevans; parkerat tills semantisk etikettmatchning (fråga →
  måletikett) finns, med en skarp definition av klart: fel-rad-antal 0 på
  hela årsredovisningssetet innan `rerankEnabled` kan sättas till sant.
- **[XS-37](https://linear.app/ai-sprints/issue/XS-37/post-pilot-attest-the-actual-runtime-model-identity)
  — runtime-identitetsattestering.** `ready=true` är konfigurationsstatus,
  inte oberoende observerad serveridentitet. Blockerade inte BP5 men har en
  definierad kontraktsskiljelinje (konfigurerad vs. observerad vs.
  människoläsbar etikett) redo att implementeras.
- **OCR bortom pilotgränsen.** SPEC:s namngivna högriskpost (OCR-koordinat-
  trohet på verkliga svenska skannade dokument) mättes som **måttlig, inte
  farlig** (konfidens 90–93, boxes-on-ink 0.93–1.0, drift p95 ≈ 0.24 % av
  sidhöjd) — se `NOTES.md` (2026-07-16) och
  [evidence/scanned-ingestion.md](evidence/scanned-ingestion.md). Skannad
  ingestion är verifierad som en isolerad smoke (7 dokument, 63 sidor, 9 572
  ord, 74 chunkar) men ingår **inte** i den formella livefrågesviten, som
  kördes på de två digitala dokumenten. Detta är en avsiktlig, dokumenterad
  gräns (se [Drift-/förvaltningsplanen §7](DRIFT-FORVALTNINGSPLAN.md#7-kända-operativa-begränsningar)),
  inte ett dolt hål.

## 7. Regler för nästa projekt

Varje regel är knuten till en observerad händelse ovan, inte en generisk
best practice.

1. **Konsolidera all produktkod i ett repo innan "ren klon kör produkten"
   hävdas** — ett nästlat, gitignorerat frontend-repo blockerade
   reproducerbarhet i veckor ([XS-33](https://linear.app/ai-sprints/issue/XS-33/make-the-fedora-pilot-reproducible-from-a-clean-checkout), §2/§4.1).
2. **Bygg tenant-isolering som separata objektgrafer från dag ett**, inte
   som filter att komma ihåg — billigast att få rätt tidigt, dyrast att
   bevisa i efterhand (§1, 18-attackers svit).
3. **Bevisa varje negativ (noll egress, ingen fabricering, ingen läckt PII)
   med en tripwire eller en fullständig korpuskorskörning**, aldrig med en
   kodläsning eller en regex-sökning allena (§1, `NOTES.md` 2026-07-16/18).
4. **Mät fel-svar-**introduktion**, inte återvinningsgrad, innan en
   rankande eller relevansförbättrande komponent slås på** — en högre
   recall-siffra kan dölja nya falska positiver som bryter kärnlöftet (§2,
   [XS-31](https://linear.app/ai-sprints/issue/XS-31/efter-pilot-grundningsvarsjustering-semantisk-etikettmatchning-q-fee)).
5. **Håll provider-/runtimekonfiguration bakom en en-rads env-växel från
   arkitekturbeslutet och framåt** — det gjorde en GPU-servermigrering till
   konfiguration i stället för ombyggnad ([XS-8](https://linear.app/ai-sprints/issue/XS-8/arkitekturbeslut),
   [XS-30](https://linear.app/ai-sprints/issue/XS-30/koppla-in-gemma-4-12b-llamacpp-ubuntu-server-rtx-4070-via-ssh-tunnel)).
6. **Schemalägg en oberoende, fräsch-kontext kall granskning före varje
   regulerat gate** — den hittade fyra verkliga fynd en redan noggrann
   leverans hade missat ([XS-35](https://linear.app/ai-sprints/issue/XS-35/independent-cold-bp5-review-and-gate-recommendation)
   → [XS-36](https://linear.app/ai-sprints/issue/XS-36/finalize-bp5-handover-hygiene-and-publish-the-reviewed-delivery)).
7. **Registrera modell och effort per issue från BP1**, inte efter halva
   genomförandet — annars går modellroutingens faktiska värde inte att
   utvärdera i efterhand, vilket just den här retrospektiven fick ärva som
   en lucka (§5).

## 8. Verifieringslogg för den här retrospektiven

- Läst i sin helhet: `NOTES.md` (255 rader, alla poster daterade
  2026-07-16 till 2026-07-19), `git log` (115 commits på `main`),
  [evidence/gate0-spec-drift.md](evidence/gate0-spec-drift.md),
  [evidence/gate0-review-round2.md](evidence/gate0-review-round2.md).
- Korsverifierat mot Linear: samtliga 37 issues i projektet listade och
  klassificerade (status, prioritet, modell/effort där angivet); fulltext
  läst för XS-4, XS-8, XS-9, XS-16, XS-21, XS-22, XS-26, XS-30, XS-31, XS-32,
  XS-33, XS-35, XS-36, XS-37; Beslutslogg och Claude Code delivery protocol
  (modellroutingdokumentet) läst i sin helhet.
- Varje lärdom ovan citerar minst en commit-SHA, ett Linear-issue eller en
  evidensfil i repot — inga generiska påståenden utan spårbar källa.
- **Inte gjort:** ingen ny kod kördes för den här uppgiften (rent
  syntes-/dokumentationsarbete). Modellattribution för XS-1–XS-32 kunde inte
  fastställas eftersom fältet saknas i Linear för den perioden (§5) — det
  redovisas som en lucka, inte gissas fram.
