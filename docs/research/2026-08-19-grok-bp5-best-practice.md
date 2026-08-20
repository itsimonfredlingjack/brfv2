# BRF Träff: från citatgrundad prototyp till skarp tjänst — best practice-rapport inför BP5

Genererad 2026-08-19 med `grok-4.6` (lokal CLI, webbsök på). Sparad som underlag inför
BP5-grinden. Inte verifierad fakta-för-fakta — se granskningsnot i botten.

## TL;DR
- Projektets grundarkitektur ligger redan rätt: hybridsök, ord-för-ord-citatverifiering, per-tenant-isolering och självhostad modell är alla i linje med 2024–2026 best practice. Den enda tekniskt kritiska avvikelsen är att den lokala 12B-modellen inte producerar konsekventa flerdels-citat — och mätdata visar tydligt att detta löses med **citat-finjustering (LoRA/SFT)**, inte med en större modell eller hårdare schematvång.
- Före BP5 bör tre saker prioriteras: (1) bygg en riktig utvärderingsuppsättning med negativa kontroller och separat mätning av retrieval-recall vs citatkorrekthet; (2) adressera fragmentfakta med layout-medveten tabellextraktion (Docling/Marker lokalt) + LoRA-finjustering på citatformat; (3) inför en relevansspärr (score-tröskel/utility-filter) så att omrankning kan slås på säkert.
- EU AI Act:s högrisk-krav är uppskjutna till 2 december 2027 (Digital Omnibus, nu formaliserad som Regulation (EU) 2026/1744, i kraft 27 juli 2026) men transparenskraven (Art. 50) gäller från 2 augusti 2026 — det påverkar hur BRF Träff måste märka AI-genererat innehåll redan nu. Linear bör städas till en enkel struktur (ett projekt per MVP-domän, milstolpar = BP-grindar, liten labeluppsättning), och Jira bör konsolideras in i Linear för att stoppa dubbelbokföring.

## Nyckelfynd

**Citatgrundning:** Forskningen (LongCite, SelfCite, ALCE) visar entydigt att små basmodeller är dåliga på att generera inline-citat via prompting — Llama-3.1-8B når bara ~20 i citat-F1 på LongBench-Cite. Men samma modell finjusterad på citatformat (LongCite-8B, tränad på LongCite-45k) når 72,0 F1 och slår GPT-4o (65,6). Enligt LongCite-artikeln (arXiv:2409.02897, ACL Findings 2025, THUDM): *"our 8B/9B size model outperforms GPT-4o by 6.4%/3.6% in term of citation F1 score and also achieves twice finer granularity."* Detta är projektets viktigaste enskilda hävstång och bekräftar teamets egen bedömning att det är en modellkapacitetsfråga, inte en arkitekturfråga.

**Fragmentfakta/tabeller:** PyMuPDF är enligt flera 2025-jämförelser inte lämpligt för komplex tabellextraktion. Docling nådde 97,9 % noggrannhet på komplex tabellextraktion i Procycons benchmark "PDF Data Extraction Benchmark 2025" (som jämför Docling, Unstructured och LlamaParse); Unstructured nådde 100 % på enkla men bara 75 % på komplexa tabeller. Docling är det starkaste lokala, integritetsbevarande alternativet. Cellnivå- och flerdelscitat kräver att tabellstrukturen bevaras vid extraktion — annars kan ett belopp i en tabellcell aldrig citeras som sammanhängande.

**Constrained decoding:** Att tvinga ett JSON-schema *under* själva genereringen kan höja parse-validiteten men sänka den semantiska korrektheten hos små modeller ("alignment tax"/"structure snowballing"). Best practice är "reason free, constrain late" — låt modellen resonera fritt, tvinga schemat i ett andra pass.

**Reranking:** Projektets erfarenhet (fler rätta rader men fyra nya fel) är ett dokumenterat fenomen — relevans korrelerar inte alltid med nytta, och rerankers producerar okalibrerade poäng. Att slå på reranking igen kräver en relevansspärr (score-tröskel eller utility-filter), inte bara en bättre rankare.

**Regelverk:** GDPR uppfylls redan genom självhosting och nätverksrevisionsspår. EU AI Act:s transparensdel gäller från augusti 2026; högrisk uppskjutet. Bokföringslagen kräver 7 års arkivering; stadgar, protokoll och lägenhetsförteckning ska sparas för evig tid — vilket är ett produktkrav för reindexering/versionering.

## Detaljer

### A. Citatgrundning och attribuering

**State of the art.** Litteraturen 2024–2026 skiljer på cite-then-answer (inline, strukturerad citering under generering) och answer-then-verify (post-hoc-attribuering). Projektets nuvarande design — LLM-svar följt av ord-för-ord-citatverifiering och koordinatmarkering — är i praktiken en answer-then-verify med hård verifieringsgrind, vilket är en robust och konservativ design. Attribution to Identified Source (AIS)-ramverket argumenterar för just detta: ett attribuerbart svar måste innehålla ett explicit citat från ett existerande dokument. Forskningen på "fine-grained citation" (ALCE, LongBench-Cite) stödjer span-nivå-citat eftersom de gör mänsklig verifiering lättare — precis det BRF Träff gör med koordinatmarkering.

En viktig varning från FullCite-studien (arXiv:2606.07130, testad på Qwen3-8B och Gemma3-12b-it): modeller är bra på dokumentnivå-citat men kämpar konsekvent med att identifiera rätt evidens-span, och uppvisar "primacy bias" (81,8 % av citaten på BioASQ pekar på de första två av fem dokument, i linje med "lost-in-the-middle"). Detta är direkt relevant eftersom Gemma-12B är projektets modell.

**Fragmentfakta och tabeller.** Detta är projektets identifierade kärnproblem. Två spår krävs:
1. *Layout-medveten extraktion.* PyMuPDF räcker för digital brödtext men är enligt LlamaIndex och flera 2025-benchmarks olämpligt för komplexa tabeller. I jämförelser (Procycons; Ertas AI:s "Docling vs Unstructured: PDF Accuracy Benchmark") nådde Docling 97,9 % tabellnoggrannhet, Unstructured hi-res 93,4 % (fel främst i sammanslagna celler/sidbrytningar) och Marker 91,7 % med "a notable weakness in tables" och tendens att slå ihop kolumner i täta layouter; Docling kan i sin tur hallucinera värden i mycket täta tabeller. Eftersom BRF Träff måste hålla allt lokalt (GDPR) är molnbaserade LlamaParse/Reducto uteslutna trots hög precision. Rekommendation: lägg till Docling (eller Marker som snabbare alternativ) som tabell-medveten väg parallellt med PyMuPDF, och bevara cellkoordinater.
2. *Flerdels-citat.* Mekaniken finns redan byggd. Problemet är att 12B-modellen inte producerar den konsekvent. Se sektion B.

**Kalibrerad vägran.** Forskningen (AbstentionBench; "Do RALMs Know When They Don't Know?", arXiv:2509.01476) visar att instruktionstrimmade modeller tenderar till över-compliance (svarar trots otillräcklig evidens) men att rent negativ kontext kan orsaka *över-vägran*. Balansen mäts med separata mått: refusal rate, hallucination rate och "gold leak" (rätt svar trots borttagen evidens). FinRAG-12B och OCC-RAG visar att en dedikerad refusal-kalibreringsdatamängd (frågor med topiskt relevant men otillräcklig kontext, där målsvaret är "vet ej") tränar rätt beteende. BRF Träff:s q11-fall (fortsatt säker vägran) visar att detta redan fungerar — det bör formaliseras som ett mätvärde.

### B. Att pressa strukturerad citatoutput ur en liten lokal modell

Detta är projektets skarpaste öppna fråga, och mätdata ger ett tydligt svar.

**Finjustering är den största hävstången.** LongCite-studien (arXiv:2409.02897, ACL Findings 2025): finjustering av Llama-3.1-8B på LongCite-45k höjde citat-F1 från 19,7 (promptad bas) till 72,0 — ett hopp på ~52 poäng — och slog GPT-4o (65,6). GLM-4-9B gick från 27,2 till 69,2. Avgörande: SFT *förbättrade även* svarskorrektheten (correctness ratio >100 %), tvärtemot den korrekthetssänkning som uppstår när man bara promptar en basmodell att citera. SelfCite (arXiv:2502.09604, ICML'25, Meta/MIT) adderade +5,3 F1 ovanpå LongCite-8B (73,8→79,1) via självövervakad preferensoptimering utan mänskliga etiketter. En LoRA-studie (arXiv:2509.20859) höjde Qwen2.5-7B till 0,73 citat-F1, och noterar explicit att LoRA fungerar "under limited video memory". IBM:s Granite-3.2-8B LoRA-adapter (arXiv:2504.11704) matchar 70B-modeller på ALCE (F1 59,8) med högre precision. För BRF Träff innebär detta: den mest effektiva åtgärden är att LoRA-finjustera modellen på svenska BRF-citatformat, inte att byta till en större modell.

**Constrained decoding — hjälper och skadar.** vLLM/llama.cpp stöder guided decoding (GBNF-grammatik, JSON-schema via Outlines/XGrammar). Men mätdata varnar: "The Constraint Tax" (arXiv:2605.26128) visade på sub-3B-modeller att hårt schematvång höjde schema-validitet från 61,5 % till 100 % men sänkte svarsnoggrannheten från 19,7 % till 11,0 %, och ett tool-call-test föll 43,5 poäng (91,5 %→48,0 %) trots 100 % giltigt schema ("the error is semantic, not structural"). "Structure Snowballing" (arXiv:2604.06066, Qwen3-8B med Outlines) fann att schematvång under resonemang triggar formateringsfällor. "Let Me Speak Freely?" (EMNLP Industry 2024, arXiv:2408.02442) fann att strikta formatrestriktioner generellt sänker resonemangsförmåga men *höjer* klassificeringsnoggrannhet. Slutsatsen är "reason free, constrain late": generera svar + citat i lätt format, tvinga strikt JSON i ett andra pass. Undantaget är klassificeringsdeluppgifter (t.ex. relevansmärkning) som gynnas av tvång.

**Uppdelning i flera anrop.** Google Research (EMNLP 2025, "Small Models, Big Results: Achieving Superior Intent Extraction Through Decomposition") visade att dekomponering av en uppgift i flera mindre steg gör den "more tractable for small models" och ger resultat jämförbara med mycket större modeller. Detta stödjer projektets flerdels-citatmekanik: att verifiera varje citatdel separat och att dela upp extraktion per fält (org.nr, motpart, belopp) är rätt väg för en 12B-modell.

**Modellval och VRAM.** Gemma 4 12B kör i ~6,6 GB VRAM vid Q4_K_M och får plats på RTX 4070 (12 GB) med gott om utrymme; QAT-varianter (Quantization-Aware Training) återhämtar noggrannheten som annars förloras vid 4-bit. En publicerad RTX 4070-benchmark (carteakey.dev) visade att QAT UD-Q4_K_XL kör upp till 69 tok/s. Viktig varning: det finns **inga publicerade LongBench-Cite/ALCE-siffror för Gemma 3/4 eller Qwen3-14B som citatgeneratorer** — detta är en genuin lucka i litteraturen. Man kan alltså inte anta att ett modellbyte hjälper utan egen mätning. Den bevisade vägen är citat-finjustering av en 8–12B-modell.

### C. Retrieval-kvalitet

**Hybridsök.** Projektets BM25 + embeddings är produktionsstandard. Reciprocal Rank Fusion (RRF, k=60) är den dominanta fusionsmetoden eftersom den arbetar på rang, inte poäng, och därmed löser inkompatibiliteten mellan BM25:s obundna poäng och cosinuslikhet. På WANDS-benchmarken nådde tunad hybrid 0,7497 NDCG mot ~0,698 för endera ensam (+7,4 %). För jargongtunga korpusar (juridik, avtal) rekommenderas fler kandidater till den glesa (BM25) sidan. För en liten korpus per förening är BM25 relativt mer värdefullt eftersom IDF-statistiken är distinkt.

**Chunkning.** För juridiska/ekonomiska dokument rekommenderas strukturell chunkning (respektera §-gränser, tabeller) framför naiv fast storlek, samt parent-child/small-to-big. Anthropics contextual retrieval — att prependa en genererad kontext till varje chunk före embedding och BM25 — gav enligt Anthropics egen blogg ("Contextual Retrieval in AI Systems", sept 2024) 35 % färre retrieval-fel med enbart contextual embeddings (5,7 %→3,7 %), 49 % med embeddings+BM25 (5,7 %→2,9 %) och verbatim *"reduced the top-20-chunk retrieval failure rate by 67% (5.7% → 1.9%)"* med reranking tillagt. Detta är särskilt relevant för fragmentfakta: en tabellrad "3 % ökning" utan förening/kvartal blir sökbar först när kontext prependeras. Prompt caching gör detta överkomligt även med en liten lokal modell.

**Reranking.** Projektets erfarenhet är väldokumenterad. "Less is More for RAG" (arXiv:2601.17532) visade att högre NDCG inte konsekvent ger högre end-to-end-F1, och att korrelationen kan bli *negativ* när flera passager injiceras — reranking-by-relevance över-admitterar relevant-men-tvetydig evidens. Redis och andra påpekar att reranker-poäng är okalibrerade (0,7 från en modell ≠ 0,7 från en annan) och att en fast tröskel måste omkalibreras vid modellbyte. Lösningen är inte en bättre rankare utan en *relevansspärr*: score-floor kalibrerad på egen valideringsdata, eller utility-aware admission control (informationsvinst-tröskel) som filtrerar svag evidens före injektion. Projektets beslut att hålla reranking avstängd tills en relevansspärr finns är korrekt och i linje med best practice.

**Query planning/multi-hop.** Evidensen är blandad. Query rewriting och dekomposition hjälper på genuint flerhopps-frågor men ökar brus och latens på enkla. Reranking löser inte flerhopp — det kräver query-dekomposition eller agentisk sökslinga. Projektets beslut att stänga av fan-out för MVP (falsk clarify regresserade) är försvarbart; mät isolerat med separata golden sets för enkla vs flerhopps-frågor innan det slås på.

**Svensk språkkontext.** Multilingual-E5 (small/base/large) och BGE-M3 är de starkaste öppna, lokalt körbara embeddingmodellerna för svenska; Scandinavian Embedding Benchmark (SEB, arXiv:2406.02396) visar att E5-familjen och kommersiella API:er är mest konkurrenskraftiga på skandinaviska. BGE-M3 stöder dense+sparse+multi-vektor i en modell och 8192-token-kontext. För svensk BM25 krävs svensk tokenisering/stemming och hantering av sammansatta ord (t.ex. "underhållsplan", "föreningsstämmoprotokoll") — annars missar lexikal matchning. Voyage-law-2 leder MMTEB:s juridiska retrieval men är ett moln-API och därmed uteslutet av GDPR-skäl.

### D. Utvärdering och regression

Projektet har redan lärt sig de svåra läxorna (gröna sviter som missar buggar, vakuösa assertions). Best practice bygger vidare:
- **Separera mätningen.** Mät retrieval-recall (hittades rätt chunk?) separat från answer faithfulness (höll svaret sig till kontexten?) och citatkorrekthet. Detta skiljer retrieval-fel från genererings-fel — den enskilt viktigaste observability-principen (Unstructured, Coralogix).
- **Negativa kontroller.** Bygg svarslösa frågor genom att ta bort gold-passager och mät refusal/hallucination/gold-leak. OCC-RAG och LogicalRAG använder just detta.
- **Golden set-storlek.** 50–100 manuellt annoterade representativa frågor räcker för att starta; märk topp-5 som relevant/ej relevant för både gammal och ny konfiguration. Undvik att optimera mot testsetet genom att hålla ett hold-out och rotera frågor.
- **Ramverk.** RAGAS (faithfulness, answer relevancy, context precision/recall), DeepEval (CI/CD-native via pytest, DAG-metriker) och TruLens (RAG Triad). Kända svagheter: LLM-as-judge har verbosity-bias, self-preference och positionseffekter — validera domaren mot mänsklig annotering innan den litas på. Som Atlan påpekar: en 0,95 faithfulness kan ändå ge fel affärssvar om kontexten är inaktuell.
- **Lokal modell i CI.** Projektets scriptade LLM för repeterbar generering är rätt mönster. eval-fast och realkorpusgaten (VERDICT: READY) är redan en evidensbaserad grind — formalisera citat-F1 och refusal-rate som gate-trösklar.

### E. Från vertical slice till skarp tjänst

**Observability.** Logga per retrieval-beslut: query, hämtade chunk-ID:n, filter, similarity-poäng, dokumentversion, retriever-strategi. Detta gör att man kan bevisa om rätt chunk hämtades när ett svar är fel. Span-baserad tracing (query rewrite → embedding → sök → rerank → generering) är standard (Arize Phoenix, Langfuse, Braintrust — självhostbara alternativ finns).

**Reindexering och versionering.** Använd content-hashing (SHA-256) för ändringsdetektering så bara ändrat innehåll omindexeras; arkivera gamla versioner istället för att radera (krav enligt bokföringslagen). Versionera embedding-modell, prompt-mallar och index-snapshots som metadata (t.ex. git-commit/Docker-hash vid ingestion) — kritiskt i en reglerad domän där man måste kunna spåra hur ett svar genererades. Detta är också ett produktkrav: BRF-dokument uppdateras (nya stadgar, nya protokoll) och gamla citat måste förbli spårbara.

**Pilot med icke-tekniska användare.** BRF Eken-piloten bör mäta: andel frågor som besvaras med verifierat citat, andel säkra vägran, tid till första verifierade svar, och supportbörda. Onboarding för ideella styrelseledamöter måste vara minimal (projektets MVP-slinga "logga in → välj förening → fråga → grundat svar → källa" är rätt avgränsad). Feedback bör vara first-class: låt användaren flagga fel citat (Perplexity behandlar "wrong sources" som en egen felkategori).

**Multi-tenant SaaS med självhostad modell.** Projektets per-förening-datastrukturer (inte query-filter) är en starkare isoleringsmodell än branschstandard och har överlevt adversariell testning — detta är en genuin styrka. Skalning begränsas av en enda RTX 4070; en enda modell-runtime är en single point of failure. Planera för kö-hantering vid samtidiga förfrågningar och en tydlig felhanteringsväg när modellen är nere (projektets "ingen tyst fallback" är rätt princip — men användaren behöver ett begripligt felmeddelande, inte en krasch).

**Regelverk 2026.**
- *GDPR:* uppfylls genom självhosting + nätverksrevisionsspår som bevisar att inget dokumentinnehåll lämnar maskinen. Detta är en verklig konkurrensfördel.
- *EU AI Act:* Högrisk-obligationerna för fristående Annex III-system sköts upp till 2 december 2027 genom Digital Omnibus, nu formaliserad som Regulation (EU) 2026/1744 (publicerad i EUT 24 juli, i kraft 27 juli 2026; Annex I → 2 aug 2028). Men Art. 50-transparenskraven gäller från 2 augusti 2026 och sköts *inte* upp: AI-genererat innehåll måste märkas och användare informeras om att de interagerar med AI. Den maskinläsbara märkningen enligt Art. 50(2) har egen deadline 2 december 2026 för system som redan finns på marknaden; nya system måste uppfylla kravet vid utsläppande. Sanktioner för brott mot Art. 50 kan uppgå till €15 M eller 3 % av global omsättning (Art. 99(4)). Kommissionens transparensriktlinjer antogs 20 juli 2026. BRF Träff bör därför märka svar som AI-genererade redan nu. Systemet är sannolikt inte högrisk i sig, men eftersom det stödjer beslut om allvarliga ekonomiska/juridiska frågor bör man dokumentera designbeslut löpande — att rekonstruera teknisk dokumentation 2027 kostar flerfaldigt mer.
- *Bokföringslagen:* räkenskapsinformation (årsredovisningar, verifikationer, avtal) ska arkiveras i ordnat, åtkomligt skick i 7 år (7 kap. 1 § BFL). Sedan 1 juli 2024 får originaldokument kastas efter digitalisering. Stadgar, protokoll från stämmor/styrelsemöten samt medlems- och lägenhetsförteckning ska enligt bostadsrättslagen sparas för evig tid. Detta gör oföränderlig versionering och arkivering till ett produktkrav, inte en nice-to-have.

### F. Frontend och kodbasarkitektur för AI-assisterat arbete

**Bryta upp monoliten.** App.jsx (1 605 rader) och App.css (1 108 rader) är exakt den situation där AI-kodagenter tappar koherens. Best practice 2026:
- *Karakteriseringstester först.* Be agenten skriva tester som bara registrerar vad komponenten gör idag innan refaktorering — nätet under trapetsen.
- *Extrahera custom hooks och mindre komponenter* i separata filer; håll varje fil liten nog att rymmas i agentens kontext.
- *CSS-isolering.* Byt globala CSS-regler mot CSS Modules eller CSS-in-JS (Emotion/styled-components) som skopar stilar per komponent. Detta eliminerar den tysta specificitets-överskrivningen direkt — enligt State of CSS 2025 minskade strukturerade namnkonventioner stilrelaterade buggar med 35 %, och Smashing Magazine 2025 uppskattar att >40 % av frontend-buggar rör missförstådd stilprecedens. Undvik !important och ID-selektorer; använd lägsta möjliga specificitet.

**Kontextfiler för agenter.** Inför AGENTS.md/CLAUDE.md med progressiv disclosure: en rotfil under ~50 rader med enmeningsbeskrivning, pakethanterare och byggkommandon, plus länkar till nästlade, ämnesindelade filer (kodstil, testning, CSS-konventioner). Nästlade AGENTS.md per katalog gör att agenten bara laddar relevanta regler (aihero.dev; Builder.io). Peka på riktiga exempelfiler ("examples beat abstractions"). Ge agenten en escape hatch: om osäker, ställ fråga eller föreslå plan istället för att gissa. Flagga vaga instruktioner för borttagning ("skriv ren kod" är oanvändbart).

**Citation-UX för icke-tekniska användare.** Ledande produkter (Perplexity, Claude, ChatGPT Search) använder inline numrerade chips i slutet av varje påstående, med hover-förhandsvisning som visar källa, titel och relevant utdrag. Projektets modell — öppna exakt PDF-sida med markerad passage — är starkare än de flesta eftersom den visar källan i original. För icke-tekniska styrelseledamöter är detta rätt: förtroende byggs av "evidens i läsflödet" (Perplexity: "sourcing stays tied to claims as you scan"). Kommunicera osäkerhet/vägran begripligt: när systemet vägrar, säg *vad som saknas* (projektets bevaknings-design "säger vad som saknas" istället för att gissa är förebildlig). Behandla fel citat som en first-class felkategori med användarfeedback.

### G. Linear-städning — konkret förslag

Best practice för en-personsteam med AI-agenter: håll strukturen minimal. Linears egen dokumentation säger att projekt är valfria för små team och blir användbara först vid kvartalsplanering eller flera samarbetande team. Övermodellering är det vanligaste misstaget. Rekommenderad struktur:

**Projekt- och milstolpestruktur.** Använd Linears fasmodell Roadmap → Projekt → Cykler → Issues. Skapa ett projekt per MVP-domän (matchar scope): "Dokument & AI-chatt", "E-post", "Kalender", plus ett "Plattform & drift". Lägg allt annat i en backlog-vy, inte som egna projekt. Använd **milstolpar = Tonnquist-grindarna BP1–BP6** inuti projekten. Detta löser dubbelbokföringen: BP-grindar blir Linear-milstolpar med måldatum, och gate-beslutet dokumenteras i milstolpens Project Document. Ingen separat beslutslogg behövs — beslutet bor i milstolpen.

**Labeluppsättning (liten, meningsfull — undvik att replikera statusar som labels).** Föreslagna: `type:bug`, `type:feature`, `type:eval`, `type:infra`, `type:docs`; `area:retrieval`, `area:generation`, `area:frontend`, `area:ops`; `evidence:needed` (issue får inte stängas utan bevis). Max ~12 labels totalt.

**Statusflöde (5–7 statusar, tydliga entry/exit-kriterier).** Triage → Backlog → In Progress → In Review → Done, plus Canceled. Använd Triage-inboxen för allt som kommer från GitHub/integrationer. Exit-kriterium för Done: länkad commit + grön testkörning eller evidensfil (projektet arbetar redan evidensbaserat — koppla issues till `docs/evidence/*`).

**Rutin för vad som dokumenteras var.** Kod-nära beslut → ADR i repo (`docs/adr/`, finns redan). Projekt/fas-beslut → Linear-milstolpens dokument. Löpande status → Linear Project Update (async). Bevis → repo `docs/evidence/`, länkat från issue. Undvik att duplicera samma info på två ställen.

**Konsolidera Jira in i Linear.** BRF-1..BRF-10 (cross-document intelligence) täcker en domän som redan hör hemma i "Dokument & AI-chatt". Att hålla två trackers för ett en-personsprojekt är ren dubbelbokföring. Migrera de 10 Jira-issuena till Linear som issues under rätt projekt, behåll BRF-numren i titeln för spårbarhet, och stäng Jira-projektet. Om någon extern part kräver Jira, spegla då enkelriktat men gör Linear till master.

**Checklista för städpasset:**
1. Skapa fyra projekt (tre MVP-domäner + Plattform & drift); allt annat → backlog.
2. Lägg in BP1–BP6 som milstolpar; markera aktuell position (inför BP5).
3. Skapa labeluppsättningen ovan; ta bort labels som duplicerar status.
4. Gå igenom alla öppna issues: stäng klart/inaktuellt, slå ihop dubbletter, flytta "kanske sen" till backlog med `evidence:needed`.
5. Migrera BRF-1..BRF-10 från Jira; stäng Jira-projektet.
6. Sätt exit-kriterium (commit + evidens) i teamets Done-definition.
7. Rensa backloggen kvartalsvis så den inte blir ett arkiv ingen läser.

## Rekommendationer

**Gör före BP5 (kritiskt):**
1. **Bygg utvärderingsuppsättningen.** 50–100 golden-frågor + negativa kontroller, separat mätning av retrieval-recall, faithfulness och citat-F1, plus refusal/hallucination/gold-leak. Utan detta kan ingen annan förbättring bevisas. Tröskel som ändrar beslut: om citat-F1 < ~0,6 på realkorpus är modellen inte redo för skarp drift.
2. **LoRA-finjustera modellen på svenskt BRF-citatformat.** Detta är den bevisade lösningen på fragmentfakta-problemet (Llama-3.1-8B: 19,7→72,0 F1 vid finjustering). Får plats på RTX 4070. Detta, inte en större modell, är rätt väg.
3. **Lägg till layout-medveten tabellextraktion** (Docling, alternativt Marker, lokalt) parallellt med PyMuPDF och bevara cellkoordinater, så belopp i tabellceller blir citerbara.
4. **Inför "reason free, constrain late"** för citatoutput: fri generering först, strikt JSON-schema (GBNF/Outlines) i andra pass. Tvinga inte schema under resonemang.
5. **Städa Linear** enligt sektion G och konsolidera Jira.
6. **Märk AI-genererat innehåll** inför Art. 50 (gäller aug 2026; maskinläsbar märkning senast dec 2026).

**Kan vänta:**
- Reranking — slå på först när en kalibrerad relevansspärr (score-floor/utility-filter) finns och mätuppsättningen kan bevisa netto-vinst.
- Fan-out/multi-hop — behåll avstängt tills separata golden sets för flerhopps-frågor visar vinst.
- Contextual retrieval (prepend genererad kontext) — hög potential (49–67 % färre retrieval-fel i Anthropics tester) men mät på egen korpus först.
- Frontend-redesign — bryt upp monoliten med CSS Modules + AGENTS.md innan ny design; annars fortsätter tysta CSS-konflikter.

**Fällor att undvika:**
- Att byta till en större modell i tron att det löser citatproblemet — det finns inga mätdata som stödjer att Gemma/Qwen-baser citerar bättre; finjustering är den bevisade vägen.
- Att slå på reranking utan relevansspärr — återinför exakt de fyra nya felen.
- Att optimera mot sitt eget testset — rotera frågor, håll hold-out.
- Att hålla kvar Jira parallellt med Linear — dubbelbokföring i ett en-personsprojekt.
- Att lita på en grön RAGAS-faithfulness-siffra utan att kontrollera att kontexten är aktuell.

## Förbehåll
- Det finns **inga publicerade citat-benchmarkscore** (LongBench-Cite/ALCE) för Gemma 3/4 eller Qwen3 som basmodeller — påståenden om deras citatförmåga kräver egen mätning. LongCite/SelfCite-siffrorna gäller Llama-3.1-8B och GLM-4-9B.
- "Structure Snowballing" och "The Constraint Tax" är färska preprints (2026) med begränsad räckvidd (enstaka modeller); riktningen är samstämmig men behandla som vägledande, inte definitiv.
- Anthropics contextual retrieval-siffror (35/49/67 %) är uppmätta på Anthropics egna korpusar (kod, arXiv, skönlitteratur) — överför inte utan egen mätning på BRF-dokument.
- EU AI Act:s exakta klassificering av BRF Träff (högrisk eller ej) är en juridisk bedömning som bör verifieras med jurist.
- Tabellextraktions-benchmarks (Docling 97,9 %) gäller ESG-/hållbarhetsrapporter respektive DocLayNet, inte svenska BRF-dokument; validera på egen korpus.
- GitHub-repot brfv2 är publikt och bekräftar projektbeskrivningen (READMEn beskriver PDF→extract→chunker→indexer→answer→citations-pipelinen, gemma4:e12b på self-hostad RTX 4070, avstängd reranking och per-tenant-isolering).

## Granskningsnot (Claude, 2026-08-19)

Två arkitekturpåståenden verifierade direkt mot koden i den här checkouten, inte bara mot
rapportens egen text:

- **Reranking av som standard:** `backend/app/schemas.py:192` — `rerankEnabled: bool = False`.
  Matchar rapportens påstående.
- **Reranking-gate ligger efter retrieval, inte i stället för den:** `backend/app/answer.py:228–241`
  — vid `rerankEnabled` hämtas WIDE (`rerankCandidates`) innan omrankning skär till `topK`.
  Matchar "relevansspärr, inte bättre rankare"-resonemanget.

Inte verifierat här (kräver webbåtkomst jag inte körde mot i det här passet): procentsiffrorna
från Docling/Unstructured-jämförelserna, eller EU AI Act-datumen.

**LongCite-siffran (den enskilt viktigaste — hela sektion B:s LoRA-rekommendation vilar på den)
är verifierad mot primärkällan**, inte bara mot Groks egen text. Andra grok-4.6-anrop
(2026-08-19, webbsök på, `reasoning_effort: high`) öppnade arXiv:2409.02897 (abs + PDF v3),
ACL Findings 2025 (`2025.findings-acl.264`) och `github.com/THUDM/LongCite`, och extraherade
Table 2 ordagrant:

```
GPT-4o                     65.6
GLM-4-9B-chat              27.2
Llama-3.1-8B-Instruct      19.7
LongCite-8B                72.0
LongCite-9B                69.2
```

Matchar rapportens siffror. En precisering ovanför texten i sektion B: 19,7 och 27,2 är
**promptade officiella chat/instruct-modeller** (Llama-3.1-8B-**Instruct**, GLM-4-9B-**chat**),
inte oalignade bas-vikter. Ändrar inte slutsatsen — finjustering ger samma ~52-poängshopp på
citat-F1 — men är den korrekta beskrivningen att citera vidare.
