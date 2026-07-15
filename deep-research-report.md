# Rekommendation i korthet

- **Arkitektur:** Använd en förlängd RAG-arkitektur där PDF → OCR/layout → strukturerade textblock med sid- och koordinatdata → textchunks → hybrid-sök (embeddings + BM25) → eventuell omrankning → LLM-svar med citerad källa → markering i PDF. Huvudkomponenter blir ett OCR- och layoutverktyg (t.ex. Mistral OCR eller open source Surya/Docling), en vektor-DB (t.ex. Qdrant) med hybrid-sök, en lämplig embeddingmodell (BGE-M3 eller liknande) plus BM25, ett cross-encoder-omrankningsskikt, och en EU-hostad LLM (t.ex. Mistral Large 2 och/eller AMD Silo Viking som reserv). Frontend använder pdf.js eller React-PDF för att visa markerade segment. 

- **Återanvändning vs nybyggnad:** Återanvänd befintlig FastAPI/RAG-motor där det är möjligt. Byt ut OCR-modulen mot en med bättre stöd för svenska och bounding boxes (vi rekommenderar Mistral OCR 4 eller Surya/Docling med svenska språkdata). Behåll hybrid-sökidéer (dense+BM25) men överväg att uppgradera embeddings från `jina-embeddings-v3` till kraftfullare flerspråkiga modeller (t.ex. BGE-M3 eller Jina v3). Bevara ChromaDB bara om enklast – annars migrera till exempelvis Qdrant för bättre hybrid-stöd och EU-kompatibilitet. 

- **Operativ drift:** Hela kedjan måste köras i EU (t.ex. EU-datacenter hos Hetzner eller liknande). Prioritera självkörda komponenter med öppna modeller för GDPR- och suveränitetskrav. Mjukvaran bör vara enkel nog för ett litet team att underhålla; minimera komplexitet som inte löser ett konkret problem. 

- **Nyckelskäl:** Mistral OCR 4 ger ledande OCR-precision och behåller sid-koordinater samt kan köras on-prem eller i EU. BGE-M3 och Jina-embeddings stöder svenska med hög kvalitet och långa kontexter. Qdrant erbjuder hybrid-sök, flerspråkstöd och GDPR-kompatibelt förvaltad drift. EU-baserade LLM (Mistral, AMD Silo) kan köras med öppna vikter under EU-lagar. 

- **Huvudsaklig osäkerhet:** Kvaliteten hos OCR och tabelltolkning på skannade svenska dokument. Detta avgör hur bra svar kan grundas på exakta textutdrag. En teknisk spik (proof-of-concept) behöver jämföra alternativ (t.ex. Mistral vs Surya/Tesseract) mot verkliga BRF-dokument och verifiera koordinatprecision.

## Rekommenderad målarkitektur

Vi föreslår följande komponenter och datamodell:

1. **Dokumentintag:** Styrelsen laddar upp PDF-filer via API/GUI. Filerna associeras med en `brf_id` och `document_id`.
2. **OCR och layout:** För varje sida i PDF körs ett OCR/layout-verktyg (t.ex. Mistral OCR 4 eller Surya) som extraherar text och strukturell information. Resultatet är **OCR-block** med textinnehåll, bounding boxes (x0,y0,x1,y1 i PDF-koordinater) och informationskategori (t.ex. ”body text”, ”table”, ”rubrik”). Dessa block behåller sidnumret. (Se [7] för hur Mistral OCR kan ge block med koordinater.)  
3. **Lagring av grunddata:** Varje block lagras med attributen: 
   - `page` (sidanummer), 
   - `bbox` (bounding box-koordinater), 
   - `text`, 
   - eventuellt `block_id`.  
   Även sidans storlek och rotation sparas. Detta möjliggör exakt mappning till pdf.js.  
   Tabellen kopplas till motsvarande dokument och BRF via `brf_id` och `document_id`. 

4. **Chunkning:** Blocksluten sammanfogas till större **chunks** (t.ex. 300–1000 ord) för effektiv embedding. Varje chunk refererar till en lista med block-id och ackumulerade `bounding_boxes`. Exempel: ett chunk kan täcka flera lätta textblock på samma sida, och dess bounding box kan bestå av de enskilda blockens boxar. 

5. **Embedding och index:** För varje chunk beräknas en embeddingsvektor med vald modell (t.ex. BGE-M3 1024-d). Vektorerna lagras i en vektor-databas (föreslaget: **Qdrant** eller liknande) med metadata (t.ex. `brf_id`, `document_id`, `page`, lista med block-ID). Samtidigt indexeras texten i en fulltextsökningstjänst (BM25) med samma metadata. Detta möjliggör hybrid-sök (se [56] och [83]). 

6. **Frågebehandling och retrieval:** När styrelsen ställer en fråga (på svenska) görs följande: 
   - **Preprocessing:** Ev. språkbehandling (skippa om irrelevant). 
   - **Hybrid Retrieval:** Utför semantisk sökning med embeddings (dense) och text-matchning (BM25) parallellt, t.ex. med Qdrant:s RRF-fusion. Filtrera per `brf_id` för tenants. Hämta top N-kandidater. 
   - **Reranking:** Kör en cross-encoder (t.ex. Jina-reranker eller BGE-reranker för svenska) på kandidaternas text mot frågan för att förbättra ordningen. (Vill träffa exakt passage.) 

7. **Svarsgenerering och källhänvisning:** Skicka de högst rankade textutdragen tillsammans med frågan till LLM. LLM genererar svaret på svenska och formulerar källreferenser genom att infoga `\[källa\]` med referenser enligt `{brf_id, document_id, page, bbox, passage}`. Ett exempel på citation kan vara `Föreningens stadgar (side 3) säger att …[källhänvisning]`. För att säkerställa källkoppling kontrolleras att LLM bara återger text som finns i ett av de hämtade styckena – man bör överväga kontrollsteg (se kvalitetskontroll nedan). 

8. **PDF-markering:** Frontend (pdf.js) tar LLM-svaret och motsvarande referenser. För varje refererat stycke hämtas sidans PDF och de relevanta bounding boxarna markeras visuellt (t.ex. gul highlight). Eftersom bounding boxes bevarats stabilt kan markören visas korrekt på rätt sida.

Mermaid-diagram (översikt):

```mermaid
flowchart LR
  A[PDF-inläsning (styrelsen)] --> B[OCR \n& layout]
  B --> C[Strukturerade block \n(text + bbox)]
  C --> D[Chunkning]
  D --> E[Embeddings & BM25-index]
  E --> F[Hybrid-sök & Rerank]
  F --> G[LLM (svarsgenerering)]
  G --> H[Citat-format]
  H --> I[PDF viewer \n(highlight)]
```

**Datamodell (exempel):**
- `Document { brf_id, document_id, title, upload_date }`
- `Page { document_id, page_number, width, height, rotation }`
- `Block { block_id, document_id, page_number, bbox, text, block_type }`
- `Chunk { chunk_id, text, embedding, block_ids[], brf_id, document_id }`
- `RetrievalResult { query_id, chunk_id, score, rank }`
- `Citation { answer_id, brf_id, document_id, page, bbox, passage_text }`

**Tenant- och säkerhetsmodell:** Varje BRF har ett eget `brf_id` och data är namespace-separerat via metadata-filtrering i vektor-DB och relations-DB. Åtkomst till data styrs av rollbaserad autentisering (endast föreningens styrelsemedlemmar har rättigheter). All data krypteras i vila och transport. OCR och LLM ska hanteras i EU. 

**Fel- och fallbackflöden:** Om OCR missar text eller ger låg säkerhet kan fallback till enklare OCR (Tesseract) eller manuell granskning övervägas. Om LLM:s svar blir självsäker utan källa ska systemet flagga eller avböja (se kvalitetskontroll). Obligatoriska komponenter i MVP är OCR-pipeline med koordinater, vektorsök och svarsgenerering med citationer. Förbättringar som exempelvis multimodal behandling eller flerspråkig UI kan senare tillkomma. 

## Beslutsmatriser

Vi har utvärderat följande alternativ på skala 1–5 (högre är bättre) för viktiga dimensioner:

**OCR och dokumenttolkning:**

| Alternativ                 | OCR-kvalitet SV | Layout/tabeller | Koordinatprecision | Självhost | Kostnad | EU-drift | Kommentarer |
|----------------------------|:---------------:|:---------------:|:------------------:|:---------:|:-------:|:--------:|------------|
| **Mistral OCR 4 (API)**    | 5               | 5               | 5                  | 3         | 4 (4 $/1k) | 5 (EU-reg) | Topprecision och bounding-box; ger även Tabell-/layoutinfo. Kan köras självhostat. |
| **Surya/Docling (open)**   | 4               | 4               | 4                  | 5         | 5 (gratis) | 5        | Stark multilingual OCR+layout; öppen kod, kräver GPU-inferens. Har god tabellförståelse. |
| **Google Document AI**     | 5               | 5               | 5                  | 2         | 2 ($10/1k) | 3 (EU via GCP) | Mycket bra OCR. Stöder sidlayout. Dyrt i drift. |
| **Azure Document Intelligence** | 4         | 4               | 5                  | 2         | 3 ($10/1k) | 4 (EU)  | Hög OCR-kvalitet. Layout-/tabellmodell finns. API-baserat, EU-region finns. |
| **AWS Textract**           | 3               | 4               | 4                  | 2         | 1 ($15/1k) | 3 (EU)  | OCR OK, tabellinfo finns. Hög kostnad för tabeller. Cloud-lösning. |
| **Tesseract (sv. språk)**  | 3               | 2               | 3                  | 5         | 5 (gratis) | 5        | Öppen, helt självhost. Godkänd textigenkänning men sämre på komplex layout och lågkvalitetsskanning. Koordinater via hOCR. |

*Viktning:* OCR-kvalitet och koordinater är kritiska (vikt 5). EU-drift & GDPR (vikt 4). Kostnad och självhosting (3). Evidens: Mistral visar toppresultat mot Azure/Google, Surya och Docling har bra "table extraction" enligt community. 

**Embeddings och omrankning:**

| Modell/Strategi              | Svenskt stöd | Långtext (BRF-dokument) | Citationsprecision | Licens/äkta | Kostnad | Självhostbar | Kommentar |
|------------------------------|:------------:|:-----------------------:|:------------------:|:-----------:|:-------:|:-----------:|-----------|
| **BGE-M3 (OpenAI/Mistral)**  | 5            | 5                       | 5                  | 5 (MIT)     | 3       | 5          | Multispråkig, hög precision, licens i ordning. Stödjer hybrid-sök inbyggt. |
| **jina-embeddings-v3**       | 5            | 5                       | 4                  | 5 (Apache)  | 5 (EIS) | 5          | 32 språk inkl. svenska. Specialiserad för RAG, högre effektivitet. |
| **Multilingual-e5 (open)**   | 4            | 4                       | 3                  | 5 (MIT)     | 5 (gratis) | 5         | Stöder 94 språk. Mindre kapacitet än BGE, men gratis. |
| **OpenAI text-emb-3 (API)**  | 5            | 4                       | 5                  | 2 (API)     | 1       | 1          | Utmärkt multispråkighet men API, påverkas av GDPR/CLOUD Act. Kostar ~$0.0004/100k tokens. |
| **BM25 (elasticsearch)**     | 3            | 3                       | 2                  | 5 (OSS)     | 5       | 5          | Utför stark exakt matchning (svenska avstavig). Krävs för exakta citat, men ingen semantik. |
| **Reranker (cross-encoder)**| *kompletterande* | *- *                  | 5                  | **         | **      | **         | Vi kan använda t.ex. `jina-reranker-v2` eller svensk BERT finetunad. Förbättrar citationsprecision kraftigt. |

*Viktning:* Svenskt språkstöds viktiga (5). Citationsprecision (4). Self-host/lisenser (4). Kostnad (3). Embed-dimension (2). BGE och Jina är ledande i flerspråkig kvalitet. Tillsammans med BM25 täcks formella dokument väl. Omrankning är nödvändig för källnoggrannhet (exempelvis Jina-vikterna kommer snart).

**Vektordatabas (index) och metadata:** 

| Databas               | Hybrid-sök | Metadatafilter | Multi-tenant | EU-drift | Driftbarhet  | Kostnad   | Kommentar |
|-----------------------|:----------:|:--------------:|:-----------:|:--------:|:------------:|:--------:|-----------|
| **Qdrant**            | 5          | 5              | 5           | 5        | 4            | 5 (OSS)  | Stöder inbyggd hybrid-sök (sparse+dense), avancerade filter. GDPR-ready och självhostbar. Bra för flera tenants. |
| **Weaviate**          | 4          | 5              | 4           | 5        | 3            | 3 (OSS)  | Har hybrid via moduler, bra filtrering, inbyggd RAG-stöd. Komplex drift (ramverk). EU-variant finns. |
| **ChromaDB**          | 3          | 3              | 2           | 5 (OSS)  | 3            | 3 (OSS)  | Enkel att använda, men enklare funktionalitet. Svårt med per-tenant isolering och avancerade filter. |
| **PostgreSQL/pgvector** | 3        | 4              | 4           | 5 (OSS)  | 3            | 3 (OSS)  | Kombinerar BM25 (PG-text) med pgvector. Hög kostnad i implementation, men EU-hostbar. |
| **Milvus**            | 4          | 4              | 3           | 5 (OSS)  | 3            | 3 (OSS)  | Stark på vektorer, stöd för filtrering. Färre färdiga multi-tenant-funktioner, kräver separat texthantering. |

*Viktning:* Hybrid-sök och filter (5), GDPR/EU (5), drift (4). Qdrant klarar hybrid med filter bäst, plus EU/OSS för GDPR. Weaviate likaså, men mer komplex. PostgreSQL/pgvector ger frihet men kräver mycket förarbete. Chroma saknar filtret och multi-tenant-stöd.

**LLM och genereringsmodell:**

| Modell/leverantör      | Svenska förmåga | Källhärdighet | Struktur (lista/tabeller) | Öppen & EU | Kostnad | Latens/hårdvara | Kommentar |
|------------------------|:---------------:|:-------------:|:------------------------:|:---------:|:-------:|:---------------:|-----------|
| **Mistral Large 2**    | 4               | 4             | 4                        | 5 (Apache2) | 3      | 3 (30B param)   | Generell toppmodell för EU. Öppna vikter (Apache2), kan köras on-prem eller via API. Starkt flerspråkig. |
| **Mistral 7B**         | 3               | 3             | 3                        | 5 (Apache2) | 4      | 5 (7B, snabbt)   | Liten och snabb. Ändvänder ej finreflektion, men lämplig vid stor volym. |
| **AMD Silo (Poro/Viking)** | 4           | 3             | 3                        | 5 (Apache2) | 4      | 4 (11–34B)      | Utvecklad i Norden med fokus på nordiska språk. Bra svenska, öppen. |
| **Llama 3 / Falcon (öppen EU)** | 3      | 3             | 3                        | 5 (open)   | 4      | 3–4 (variabel)  | Generella open-modeller, mjölkspråkiga (sv). Kan finjusteras, men juridiskt ok i EU. |
| **OpenAI GPT-4o (API)**| 5               | 5             | 5                        | 1 (USA/API) | 2      | 2 (egen infra)   | Mycket stark svenska och faktor. API med EU-zoner men Cloud Act-risk. Dyr. Begränsat EU-anpassat (Data zone). |
| **DeepL Write / Anthropic Claude** | 3   | 3             | 4                        | 3 (Tyskland) | 3      | 4                | Fokuserar mer på formatering/översättning. Kan övervägas för specialfall. |

*Viktning:* Svensk och källhärdighet (5), GDPR/EU (5), kostnad (4). Mistral och AMD Silo är bäst för EU-krav och performance. Vi väljer Mistral Large 2 som primär (öppen, high-end) och har Mistral 7B eller Silo Viking som backup. GPT-4o har suverän kvalitet men juridisk osäkerhet (US Cloud Act) samt hög kostnad. 

**Hosting och infrastruktur:** 

| Plattform/leverantör       | EU-kompatibel | Kapacitet/skalning | Prisnivå | Enkel drift | Kommentar |
|----------------------------|:-------------:|:------------------:|:-------:|:----------:|-----------|
| **Hetzner (fyraörn SV)**   | 5             | 4 (eg. dedikerade servrar) | 5       | 4         | Låg kostnad, EU-baserad. Kräver mer drift (self-host). Bra för stora volymer och GPU. |
| **Managed VPS (OVH/Rackspace)** | 5      | 3                 | 4       | 4         | EU-centrerad, låg drift. Mindre flexibel än rent rent HW. |
| **Fly.io (EU-noder)**      | 4             | 3 (microservices)    | 3       | 5         | Enkel plattform för mindre tjänster. Kan deploya nära användare. Begränsad GPU-stöd. |
| **Railway/Vercel**         | 3             | 2                  | 3       | 5         | Mycket enkel utveckling. Helt SaaS, mindre kontroll. Oklart EU-läge. |
| **AWS/Azure/GCP (EU)**     | 4             | 5 (autoskal)       | 2       | 2         | Flexibilitet och skalbarhet, men hög kostnad. Behöver uppsikt för GDPR (Data zone). |

*Viktning:* EU-drift (5), kostnad (4), drift (4), prestanda (3). För MVP och pilot rekommenderas egen server (t.ex. Hetzner) eller VPS i EU för att minimera drift. Fly.io/Railway är lockande för snabb proof-of-concept, men har begränsad GPU/EU-kontroll. 

**Bygga vs köpa RAG-motor:**

| Alternativ                  | Kostnad totalt | Integrationsarbete | Källspårbarhet | Vendor-lock | GDPR | Förvaltning (2 pers) | Kommentar |
|-----------------------------|:-------------:|:------------------:|:-------------:|:----------:|:----:|:-------------------:|-----------|
| **Återanvänd existerande FastAPI/RAG** | 5     | 5                  | 5             | 5          | 5    | 5                   | Minimalt extra arbete. Vi kan uppgradera komponenter stegvis. Full kontroll, anpassat för GDPR. |
| **Införliva RAGFlow/Supavec**        | 3     | 3                  | 4             | 3          | 4    | 4                   | Öppna projekt anpassade för dokument-RAG. Kräver integration, men sparar initial utveckling. Lärandekurva finns. |
| **Managed RAG-tjänst (färdig SaaS)** | 2     | 4                  | 2             | 1          | 1    | 3                   | Snabb start, men leverantörslåsning och osäkerhet kring datalagring (pre-GDPR). Färdiga uppslag och highlight ingår möjligtvis (Weaviate/Pinecone). |
| **Egen plattform (t.ex. Haystack)**   | 4     | 3                  | 5             | 4          | 5    | 3                   | Kontrollerad, fullt anpassningsbar. Kräver betydligt mer utvecklingstid. |

*Viktning:* Vill minimera total cost (5) och datarisken (5). Återanvänd befintlig RAG-motor är mest kostnadseffektivt och GDPR-säkert. Att använda t.ex. RAGFlow/Kotaemon kan ge snabbare funktioner för citationer, men kräver integration och kan delvis byta ut egen kod. Ett managed SaaS är opraktiskt pga GDPR. 

## MVP och fortsatt utveckling

- **MVP (måste ingå):** 
  - Dokumentintag med svensk OCR+layout som bevarar sidnummer och bounding boxes (t.ex. Mistral OCR eller Surya). 
  - Generering av chunkar (300–1000 ord) med metadata för sid- och box-koordinater.
  - Vektor-DB (Qdrant) plus BM25-indexering av all text.
  - Hybridsök (embedding + BM25) och enkel omrankning.
  - Enkel frontend där styrelsen kan ställa fråga, se svar med källhänvisning {brf_id, dokument, sida, bbox, text} och få rätt passage markerad i PDF.
  - Drift i EU och GDPR-kompatibilitet (på plats – Inga externa API:er utanför EU).

- **Kan vänta (vidare förbättringar):** 
  - Söka över flera språk (primärt svenska behövs nu).
  - Avancerad tabellsextraktion med specialanpassning.
  - Flöde för uppladdning via mobilkamera, OCR av foton.
  - Automatiserad QA-övervakning (CRAG, Self-RAG), endast om problem uppstår.
  - Integration med redan existerande BRF-system (sido-funktion).
  - Finesser som grafbaserad frågeplanerare eller multi-hop.

- **Ej för MVP:** 
  - Funktioner utöver dokument-VR: e-post/kalenderintegration, sociala funktioner, analys av medlemsdata o.s.v.
  - Realtidssynk med externa dokumentkällor (API:er).
  - Fullständig automatisk översättning eller multimodal AI (ex. att förstå diagram med vision).
  - Egendefinierade AI-roller (ReAct- eller agentmetoder) inledningsvis – räcker att LLM-svaret är grundat och källbelagt.

## Kostnadsmodell

Antaganden (exempel): varje BRF laddar upp ~100 dokument på 10 sidor i snitt per år (totalt 1000 sidor). I pilot med 5 BRF:er hanteras ~5 000 sidor initialt, senare kanske 50 BRF (~50 000 sidor).

- **OCR- & layoutkostnad:** Om vi använder Mistral OCR API (~$2–4 per 1000 sidor) skulle 10 000 sidor kosta \$20–\$40. Alternativt självhostad Surya (GPU-kostnad ~\$0,10/sida). 
- **Embedding/Retrieval:** Open source-modeller kan köras självhost: hårdvarukostnad (GPU) kanske \$500–1000/mån för större testkluster. Om man använder API-embeddings (OpenAI) skulle det vara lågt per anrop (~\$0.0004/token) men för 50 000 sidor (30M token) blir \$12k, vilket är orealistiskt högt. Självhostad open modell rekommenderas.
- **LLM-kostnad:** Antag 100 frågor per månad, svarslängd ~200 ord. Med Mistral 7B lokalt på GPU (ej licenskostnad per anrop). Om man istället använde GPT-4o API är priserna ~\$0.06/svar (grov skattning) → \$6/mån, men det är troligtvis dyrare med större volymer.
- **Drift:** En dedikerad server (4-8 CPU, 16–32 GB RAM, 1 GPU) på Hetzner kostar kanske 1000–2000 SEK/mån. Ytterligare DB/disk (2 TB) för ~300 SEK/mån. Molntjänster (DB, övervakning) ca 500–1000 SEK/mån.
- **Totalt (pilot):** En engångskostnad för uppsättning ~50–100 kSEK (utveckling, server). Månadskostnad kanske 5000–10 000 SEK: GPU (5000), storage/DB (2000), övrigt (3000) + OCR API (200) + LLM (0 om on-prem). 
- **Totalt (tiotals BRF):** Skalning: flera servrar eller större instans. Volymer kanske 10×. Då kan priset nå 50–100 kSEK/mån beroende på modellval och dataanrop. Stora osäkerheter i antal frågor och modeller.

Alla siffror är grova uppskattningar. API-kostnader baseras på [7][92][30][40] och hårdvaru- och driftpriser i västeuropeiskt datacenter. 

## Business Case och marknad

- **Marknad:** Sverige har ~30 000 bostadsrättsföreningar. Initialt riktar vi oss mot de ~500 föreningar som visat intresse. Styrelsernas smärta är att dagligen hantera hundratals sidor (protokoll, avtal, bokslut) som ofta är analoga eller splittrade. Enligt Nabo-siffror har många föreningar fortfarande pärmar, vilket gör introduktion av nya ledamöter svår. Att digitalisera och möjliggöra snabb sökning kan ge stora tidsvinster. 

- **Konkurrenter:** Inga befintliga system erbjuder fråge-SSÖK i PDF med markering. Proptech-aktörer som Nabo, Tydliga och Visma erbjuder digital hantering (dokumentarkiv, e-post, formhantering), men saknar intelligent sök/AI-frågor. Google/Office 365 har generella verktyg men inget skräddarsytt för BRF-säkerhet och GDPR. Internationellt har projekt som Kotaemon och RAGFlow visat prototyper, men inget kommersiellt i Sverige. 

- **Pris och intäkt:** En realistisk prisnivå kan vara några kronor per bostadsrätt och månad (t.ex. 5–20 kr/lgh/mån). Med i snitt 50 lägenheter per förening blir det 250–1000 kr/mån per förening. Detta bör täcka drift och utveckling. Kunderna (styrelser eller förvaltare) sparar tid – t.ex. om varje fråga till systemet sparar 30 min av mödestid, mot en besparing på kanske 200 kr i styrelsekostnad, blir systemet snabbt självfinansierande. 

- **Effektmål (pilot):** 
  - Minskad söktid (mål: halverad tid till relevant dokument).
  - Andel frågor med korrekt källhänvisning ≥ 80%.
  - Användarnas förtroende (surveymätnings).
  - Minskad förberedelsetid inför möten (timmar sparade).
  - Detta kan mätas genom användartester med existerande prototyp. 

- **Kunderbjudande:** Förutom time-savings erbjuder systemet GDPR-säkrat behållande av känsliga dokument. Många föreningar kan betraktas som datakontrollerande organ – de värdesätter EU-lösningar och dokumenttracking. 

## Riskregister

| Risk                                              | Typ             | Sannolikhet | Konsekvens | Tidig varningssignal                  | Förebyggande åtgärd                        | Reservåtgärd                       |
|---------------------------------------------------|-----------------|:-----------:|:----------:|---------------------------------------|--------------------------------------------|-----------------------------------|
| Otillräcklig OCR-kvalitet på skannade dokument    | Teknisk         | Medel       | Hög        | Låg träffsäkerhet; många frågetecken   | Utvärdera flera OCR-verktyg i spik fas     | Lägga till manuell korrektur/varning; utöka OCR (kombinera metoder) |
| Modellhallucination / felaktiga svar             | Teknisk         | Medel       | Medel      | Falska eller irrelevanta uttalanden    | Starkt citeringskrav och fallbacks         | Introducera kontrollsteg (CRAG/Self-RAG)      |
| GDPR- och integritetsöverträdelser                | Juridisk        | Låg         | Hög        | Klagomål från medlemmar; inspektion     | End-to-end-kryptering, EU-drift, databegränsning | Dra in tjänsten och revidera processer    |
| Leverantörslåsning (API/Licens)                   | Strategisk      | Medel       | Medel      | Licensförändringar från leverantör     | Prioritera öppen kod (Apache/MIT) | Byta till alternativ leverantör eller modell      |
| Operativ komplexitet för litet team               | Operativ        | Hög         | Medel      | Buggar eller driftstörningar            | Välj enkla standardkomponenter, automatik  | Outsourca drift eller förenkla funktionalitet    |
| Bristande användaracceptans                      | Marknad         | Låg         | Medel      | Låg användningsfrekvens; negativ feedback | Involvera pilotkunder tidigt, visa mervärde | Utbildning/workshops, förbättra UI/UX           |
| Höga moln-/API-kostnader vid skalning            | Finansiell      | Medel       | Medel      | Överraskande fakturor                  | Optimera modeller; sätt användartak        | Övergå till självhostad open-source istället     |
| Fel i passages-till-markering (sync-problem)      | Teknisk         | Låg         | Medel      | Oväntade highlight-fel rapporteras     | Enhetstest av koordinater, robust datahantering | Lägg till fallbacks (exakta sidantal istället)  |

## Teknisk spik

**Syfte:** Validera de största osäkerheterna innan full skala byggnation. Spiken omfattar:

- **OCR-test:** Samla representativa dokument (skannade protokoll, årsredovisningar med tabeller, stadgar) från föreningar. Jämför OCR-kvalitet på dessa med minst två pipeline-alternativ (t.ex. Mistral OCR vs Surya/Tesseract). Mät: tecken- och ordsaccuracy, tabellsextraktion, antal korrekt identifierade bounding boxes. Godkänd-kriterium: ≥90% ordmatch för ren text, ≥80% av tabellinnehåll korrekt extraherat. 
- **Layout/coordinat-test:** För ett urval sidor kontrollera att sparade bounding-boxar stämmer med PDF-utskriften. Mät minor shift (pixlar) och andel felfria höjder/bredd. Krav: genomsnittlig avvikelse <5% av sidhöjd. 
- **Retrieval-test:** Bygg ett litet index (t.ex. 100 dokument) och testa frågeåtervinning. Jämför embeddingmodeller (BGE-M3 vs multilingual-e5 vs Jina-v3) plus kombinerad med BM25. Mät recall@k på kända frågor (fråga vs svarspassage). Godkänd: recall@5 ≥80%. 
- **Citerings- & highlight-test:** Simulera några frågor i prototyp-UI. Se att modellen bara citerar exakta passager och att pdf.js markerar rätt ställen (många olika sidor, överlappande passager). Kontrollera att block-listningen fungerar (flera bounding boxes per passage). Mått: upplevd korrekta markeringar (manuell granskning). Krav: minst 90% av citerade källor leder till korrekt highlight. 
- **Resultat:** Dokumentera precision i varje steg. Om ett alternativ (t.ex. Tesseract) misslyckas mot kraven byts det ut. Dessa testbestämmelser ska ligga till grund för val av OCR-komponent och dataformat. 

## Öppna frågor

- **Val av OCR:** Vilken pipeline ger bäst trade-off kvalitet/latens för lågkostnadsdrift? Till exempel kan Mistral OCR prestera bäst, men kräver GPU och skillnad mot Surya är ännu inte oberoende verifierad på svenska dokument.  
- **Embeddingmodell:** Behövs mer experiment för att se om BGE-M3 eller Jina-v3 ger reellt bättre resultat än billigare alternativ på våra dokument. Svenska benchmarkresultat är begränsade.  
- **LLM-licenser:** Kan befintliga EU-öppna LLM (som Mistral 7B/2) hålla måttet eller behöver vi köpa API-krediter för högsta precision? Dataskyddsavtal kring kunddata måste klargöras.  
- **Driftssetup:** Ska vi för MVP hantera allt i egna servrar (max kontroll) eller kan vi lita på en hybridlösning (t.ex. Hantera inläsning själva men skicka embeddings till en EU-cloud-tjänst)? 
- **Metadatahantering:** Hur finmaskigt ska vi tillåta filtrering (ex. datum, dokumenttyp, etc.)? Ännu oklart om det behövs som MVP eller senare. 
- **Kostnadskalkyler:** Vi behöver konkreta användningsstatistik från piloter (antal frågor, sidvolymer) för att justera realistik. Våra antaganden är försiktiga men saknar bekräftelse. 

**Slutsats:** Den rekommenderade lösningen är en utökad version av nuvarande RAG-motor med svenskanpassad OCR (prioriterat Mistral eller Surya) och stark europeisk embedding-/LLM-stack (Mistral, Jina, AMD Silo) i ett EU-hostat system. Den största osäkerheten är OCR-kvalitet på skannade dokument – en teknisk spik krävs för att välja slutlig OCR-pipeline. Med rätt val av modeller kommer systemet att kunna ge säkra, källförankrade svar på svenska styrelsefrågor och uppfylla GDPR-kraven. 

**Källor:** Vi har använt officiell pris- och produktdokumentation samt fristående jämförelser för att motivera valen. Till exempel har Microsofts och Googles OCR visat ledande noggrannhet, Mistral OCR lovar toppresultat med bevarade koordinater, BGE- och Jina-modeller har brett flerspråkstöd, och Qdrant/Weaviate erbjuder GDPR-godkända lösningar. Riksbyggen och HSB bekräftar att alla BRF:er omfattas av GDPR. Dessa källor stöder analysen ovan.