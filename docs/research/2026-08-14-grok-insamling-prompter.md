# Tre Grok 4.6-prompter — insamling, inte rekommendationer

Skrivna 2026-08-14. Syftet är att fylla det underlagsglapp som stoppade BRF-1:
allt vi vet vilar på **nio avtal från en enda förening** och på **frågor som en AI
hittat på**. Ingen av prompterna nedan ber Grok om råd. Alla tre ber om **underlag
som går att mäta på**.

Kör var och en i en **egen Grok-session** med webbsökning på. Klistra tillbaka
svaret här, så hämtar och mäter jag.

**Inställningar:** `reasoning_effort: high` räcker för alla tre — bredden kommer
från sökanropen, inte från djupare resonemang. `xhigh` bara om prompt 3 ger tunt
resultat. Kör du via API i stället för appen: sätt `prompt_cache_key` per session,
annars betalar du fullpris varje tur. Skicka inte `presencePenalty`,
`frequencyPenalty` eller `stop` — resonemangsmodellerna avvisar dem.

**Det största felläget är påhittade URL:er.** Alla tre prompterna kräver därför att
Grok faktiskt öppnat varje länk och redovisar hur många försök som misslyckades.
Kontrollera den siffran innan du skickar vidare — saknas den är listan inte
verifierad.

---

## Prompt 1 — Årsredovisningar från många olika föreningar

> Du samlar in ett underlag av **offentligt publicerade svenska BRF-årsredovisningar**
> som ska användas för att utvärdera ett dokumentfrågesystem. Jag behöver PDF:er,
> inte sammanfattningar.
>
> **Vad som gör underlaget värdefullt är spridning, inte volym.** Systemet ska
> prövas mot många olika mallar, eftersom varje förvaltare formger sina rapporter
> olika. Sikta på minst fyra mallfamiljer — HSB, Riksbyggen, SBC, Simpleko, Fastum,
> och föreningar som gör egen mall — och minst 25 olika föreningar. Tio rapporter
> från samma förvaltare är sämre underlag än tio från fem olika.
>
> Sök brett: föreningarnas egna hemsidor, förvaltarnas portaler, allabrf.se,
> mäklarsidor som publicerar årsredovisningen till en försäljning, och
> kommunala/regionala sammanställningar. Räkenskapsår 2022–2025.
>
> **Öppna varje länk innan du listar den.** Listar du en URL du inte har kunnat
> hämta är hela listan värdelös för mig, eftersom jag hämtar dem maskinellt. Om en
> länk inte fungerar: uteslut den och räkna den. Redovisa i slutet hur många länkar
> du prövade, hur många som gav en faktisk PDF, och hur många som föll bort.
>
> Redovisa så här — först en tabell, sedan **enbart URL:erna, en per rad**, i ett
> eget kodblock så att jag kan mata dem rakt in i en nedladdare:
>
> | förening | mall/förvaltare | räkenskapsår | sidor | digital eller skannad | URL |
>
> Vet du inte sidantal eller om den är skannad, skriv `okänt` hellre än att gissa.
>
> Måltal: **40 dokument**. Kommer du inte dit, lämna det du har och säg hur långt du
> kom och var det tog stopp — en kortare verifierad lista är värd mer än en längre
> med gissningar i.

---

## Prompt 2 — Stadgar och ordningsregler

> Du samlar in **offentligt publicerade svenska BRF-stadgar, ordningsregler och
> liknande styrdokument** som ska användas för att utvärdera ett dokumentfrågesystem.
> Jag behöver PDF:er eller webbsidor med hela texten, inte sammanfattningar.
>
> Den här dokumenttypen är viktigare än den låter: det är den styrelser och boende
> faktiskt ställer frågor om — *får jag hyra ut i andra hand, vem ansvarar för
> fönstren, vad gäller för balkonginglasning, får jag ha katt*. Föreningar publicerar
> dem nästan alltid själva.
>
> Ta med, i fallande prioritet:
> 1. **Stadgar** (registrerade, ofta i PDF på föreningens sida)
> 2. **Ordningsregler / trivselregler**
> 3. **Andrahandsuthyrningspolicy** och regler för renovering eller balkong
> 4. **Underhållsansvarsfördelning** — vem svarar för vad, förening mot medlem
>
> **Spridning är poängen.** Minst 20 olika föreningar, och blanda mallfamiljer:
> HSB:s och Riksbyggens normalstadgar ser likadana ut mellan föreningar, så ta med
> både sådana och föreningar som skrivit egna. Om du ser att två stadgar är i
> praktiken samma normalstadga, notera det — det är i sig användbar information för
> mig.
>
> **Öppna varje länk innan du listar den.** En URL du inte kunnat hämta får inte
> stå med; jag hämtar dem maskinellt. Redovisa i slutet hur många du prövade, hur
> många som fungerade och hur många som föll bort.
>
> Redovisa som en tabell, och därefter **enbart URL:erna, en per rad, i ett eget
> kodblock**:
>
> | förening | dokumenttyp | normalstadga eller egen | format (PDF/HTML) | URL |
>
> Måltal: **30 dokument**. Kortare och verifierad slår längre och gissad.

---

## Prompt 3 — Hur en styrelseledamot faktiskt formulerar sig

> Jag bygger ett system som svarar på frågor om en bostadsrättsförenings egna
> handlingar. Jag har testat det på frågor som en AI har formulerat, och de är
> systematiskt för välskrivna. **Jag behöver verkliga frågor, ordagrant, från
> verkliga människor.**
>
> Sök upp svenska källor där styrelseledamöter och boende i bostadsrättsföreningar
> ställer frågor med egna ord: forumtrådar, öppna Facebook-grupper för
> BRF-styrelser, frågelådor hos Bostadsrätterna, HSB, Riksbyggen och
> Hyresgästföreningen, juristbyråers FAQ-sidor, Reddit, X, och kommentarsfält under
> artiklar om bostadsrätt.
>
> **Kopiera frågan exakt som den står.** Städa inte språket, rätta inte stavning,
> gör den inte tydligare. Det slarviga är hela poängen. Många i en BRF-styrelse är
> vanliga boende som blivit invalda, inte jurister eller ekonomer — och det är
> precis deras sätt att uttrycka sig jag saknar. Är en fråga välformulerad och
> facktermsrik är den mindre värdefull för mig än en som är vag och halvfärdig.
>
> Skriv för varje fråga:
>
> | frågan ordagrant | var den kommer ifrån (URL) | vilken sorts handling som skulle svara | facktermen frågeställaren *inte* använde |
>
> Sista kolumnen är den viktigaste. Skriv någon *"vem betalar om det blir vattenskada
> i badrummet"* när handlingen säger *"underhållsansvar"* eller *"ansvarsfördelning"*
> — då är glappet mellan de två orden precis det jag mäter. Lämna kolumnen tom om
> det inte finns något glapp; hitta inte på ett.
>
> Gruppera i slutet efter dokumenttyp: stadgar, årsredovisning, avtal,
> stämmoprotokoll, underhållsplan.
>
> Måltal: **60 frågor**, varav minst 20 med ett tydligt ordglapp. Hittar du inte 60
> äkta, lämna färre — **hitta inte på frågor för att fylla kvoten**, det förstör hela
> underlaget och jag kan inte se skillnaden i efterhand. Säg hur många du hittade och
> var de tog slut.

---

## Vad som händer med svaren

**Prompt 1 och 2** → jag hämtar PDF:erna till en katalog **utanför repot** (som den
tidigare `~/brf-corpus-public/`), kör dem genom den riktiga ingestionsvägen och
mäter. Handlingarna är offentliga men innehåller styrelseledamöters namn; korpusen
committas därför aldrig, och rapporterna innehåller enbart siffror — samma disciplin
som `docs/evidence/annual-reports.md` och `corpus-isolation.md`.

**Prompt 3** → frågorna blir mätfall mot den korpusen. Det är första gången
utvärderingen använder frågor som ingen av oss har hittat på.

**Det som därmed går att svara på för första gången:** håller sig felet "fel handling
överst" (10 av 11 idag) när det finns dokument från många föreningar, eller är det en
egenhet hos just de nio avtalen? Och är ordförrådsglappet verkligt utanför ett enda
arkiv?

Fan-out-frågan återöppnas **inte** av det här. Den mättes på avtalsspråk och ligger
avstängd. Villkoret för att ta upp den igen står kvar oförändrat i
`docs/evidence/fan-out-mvp-beslut.md`.
