# -*- coding: utf-8 -*-
"""Synthetic (fictional) Swedish BRF corpus B for Brf Sjöutsikten 7 (Göteborg).

Second tenant corpus for multi-tenant tests. Every fact — avgifter, bank,
lånenummer, leverantörer, datum, personer och regler — skiljer sig avsiktligt
från korpus A (Brf Gjutformen 12) så att läckage mellan tenants blir
detekterbart. Struktur identisk med scripts/seed_content.py: varje dokument är
en lista av sidor; varje sida en lista av stycken. "# "-prefix renderas som
rubrik. "\n" inuti ett stycke är en hård radbrytning (används för att plantera
en avsiktlig avstavning: "trädgårds-/skötseln"). Alla belopp, namn och
organisationer är påhittade.
"""

FOOTER_B = "Brf Sjöutsikten 7 | Org.nr 769633-8821 | Utskrift ur föreningens digitala arkiv"

DOCUMENTS_B: list[dict] = [
    {
        "name": "Stadgar Brf Sjöutsikten 7.pdf",
        "pages": [
            [
                "# STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN SJÖUTSIKTEN 7",
                "Antagna vid extra föreningsstämma den 14 oktober 2023 och registrerade hos Bolagsverket den 3 januari 2024.",
                "# § 1 Föreningens firma och säte",
                "Föreningens firma är Bostadsrättsföreningen Sjöutsikten 7. Föreningen har sitt säte i Göteborgs kommun, Västra Götalands län.",
                "# § 2 Ändamål och verksamhet",
                "Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att i föreningens fastighet upplåta bostäder åt medlemmarna till nyttjande utan tidsbegränsning. Föreningen upplåter därutöver en gästlägenhet och en bastu till medlemmarnas gemensamma bruk.",
                "# § 3 Medlemskap",
                "Fråga om att anta en medlem avgörs av styrelsen. Styrelsen är skyldig att snarast, normalt inom en månad från det att skriftlig ansökan kom in till föreningen, avgöra frågan om medlemskap.",
                "# § 4 Insats, årsavgift och upplåtelseavgift",
                "Insats, årsavgift och i förekommande fall upplåtelseavgift fastställs av styrelsen. Årsavgifterna fördelas mellan bostadsrätterna i förhållande till lägenheternas insatser. Årsavgiften betalas månadsvis i förskott och skall vara föreningen tillhanda senast den tjugofemte dagen i månaden före den månad avgiften avser.",
            ],
            [
                "# § 5 Särskilda avgifter",
                "För arbete vid övergång av en bostadsrätt får föreningen ta ut en överlåtelseavgift om högst 3,5 procent av prisbasbeloppet. Överlåtelseavgiften betalas av överlåtaren. Pantsättningsavgift får tas ut med högst 1,5 procent av prisbasbeloppet. Avgift för andrahandsupplåtelse får tas ut med högst 8 procent av prisbasbeloppet per år.",
                "# § 6 Andrahandsupplåtelse",
                "Upplåtelse av lägenheten i andra hand kräver styrelsens skriftliga medgivande. Medgivande lämnas för högst sex månader åt gången. Ansökan skall vara skriftlig och innehålla skälet för upplåtelsen, vilken tid den avser samt uppgift om vem som skall bo i lägenheten.",
                "# § 7 Inre underhåll",
                "Bostadsrättshavaren svarar på egen bekostnad för det inre underhållet av lägenheten. Till det inre räknas bland annat ytskikt, vitvaror, sanitetsporslin och innerdörrar. Föreningen svarar för underhållet av fastigheten i övrigt, däribland de ledningar för avlopp, värme och vatten som föreningen försett lägenheten med.",
                "# § 8 Styrelsens sammansättning",
                "Styrelsen består av lägst fyra och högst sju ledamöter med högst tre suppleanter. Styrelseledamöter väljs av föreningsstämman för en mandattid om två år. Styrelsen är beslutför när minst fyra ledamöter är närvarande.",
                "# § 9 Firmateckning",
                "Föreningens firma tecknas av ordföranden i förening med ytterligare en styrelseledamot.",
            ],
            [
                "# § 10 Revisor",
                "Föreningsstämman skall årligen välja minst en revisor. Revisorn skall vara auktoriserad eller godkänd.",
                "# § 11 Ordinarie föreningsstämma",
                "Ordinarie föreningsstämma hålls årligen före maj månads utgång. Kallelse till föreningsstämma sker genom anslag i entréerna samt via föreningens digitala medlemsportal tidigast fyra veckor och senast två veckor före stämman.",
                "# § 12 Gemensamma utrymmen",
                "Föreningens bastu och gästlägenhet upplåts till medlemmarna enligt de ordningsregler och avgifter som styrelsen beslutar. Bokning sker via den digitala medlemsportalen. Gästlägenheten får hyras i högst fem nätter i följd av samma hushåll.",
                "# § 13 Fond för yttre underhåll",
                "Avsättning till fonden för yttre underhåll skall ske årligen med ett belopp om lägst 425 000 kronor i enlighet med den underhållsplan som styrelsen fastställer.",
                "# § 14 Vinstdisposition och upplösning",
                "Om föreningsstämman beslutar att uppkommen vinst skall delas ut skall vinsten fördelas mellan medlemmarna i förhållande till lägenheternas insatser. Vid föreningens upplösning skall behållna tillgångar fördelas på samma sätt.",
            ],
        ],
    },
    {
        "name": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf",
        "pages": [
            [
                "# ÅRSREDOVISNING 2025 — BOSTADSRÄTTSFÖRENINGEN SJÖUTSIKTEN 7",
                "Styrelsen för Bostadsrättsföreningen Sjöutsikten 7, organisationsnummer 769633-8821, avger härmed årsredovisning för räkenskapsåret 1 januari till 31 december 2025.",
                "# Förvaltningsberättelse",
                "Föreningen äger och förvaltar fastigheten Sjöutsikten 7 i Göteborg. Byggnaden uppfördes 1978 och rymmer 62 bostadslägenheter samt en kommersiell lokal som är uthyrd till en frisörsalong. Den totala boytan uppgår till 4 875 kvadratmeter och lokalytan till 210 kvadratmeter.",
                "Den ekonomiska förvaltningen har under året skötts av Kajkanten Ekonomiförvaltning AB. Fastighetsskötsel och felanmälan har hanterats av Fastighetspartner Hisingen AB. Trappstädning och skötsel av utemiljön har utförts av Rent & Grönt i Väst AB.",
                "Föreningen är ett privatbostadsföretag enligt inkomstskattelagen och betecknas därmed som en äkta bostadsrättsförening.",
                "# Väsentliga händelser under räkenskapsåret",
                "Under våren 2025 byttes fjärrvärmecentralen ut till en kostnad av 985 000 kronor, vilket beräknas sänka byggnadens energianvändning med omkring åtta procent. Under hösten installerades ett digitalt passersystem med taggläsare i samtliga entréer till en kostnad av 315 000 kronor.",
            ],
            [
                "# Ekonomisk ställning och resultat",
                "Nettoomsättningen uppgick till 6 180 000 kronor, varav årsavgifter utgjorde 5 240 000 kronor samt hyres- och lokalintäkter 940 000 kronor. Driftskostnaderna uppgick till 3 610 000 kronor, avskrivningarna till 1 237 000 kronor och räntekostnaderna till 1 118 000 kronor. Årets resultat blev 215 000 kronor.",
                "Föreningens fastighetslån uppgick vid årets utgång till 32 400 000 kronor, fördelade på två lån hos Skärgårdsbanken Hypotek AB med lånenummer 220445 och 220446. Den genomsnittliga räntesatsen var 3,65 procent. Lånet med nummer 220445 villkorsändras i september 2027.",
                "Styrelsen beslutade i december 2025 att höja årsavgifterna med 6 procent från och med den 1 juli 2026 för att möta stigande räntekostnader och ökade avsättningar enligt underhållsplanen.",
                "# Fond för yttre underhåll",
                "Till fonden för yttre underhåll avsattes under året 425 000 kronor i enlighet med stadgarna. Fonden uppgick vid räkenskapsårets slut till 2 890 000 kronor.",
            ],
            [
                "# Flerårsöversikt",
                "Årsavgiften uppgick 2025 till i genomsnitt 1 075 kronor per kvadratmeter boyta och år. Soliditeten uppgick till 27 procent och belåningen till 6 646 kronor per kvadratmeter boyta. Likvida medel vid årets slut uppgick till 1 340 000 kronor.",
                "# Förslag till resultatdisposition",
                "Styrelsen föreslår att årets resultat om 215 000 kronor jämte balanserat resultat om 480 000 kronor, sammanlagt 695 000 kronor, balanseras i ny räkning.",
                "# Revision",
                "Revisionen har utförts av auktoriserade revisorn Gunnel Hammarlind vid Granit Revision Väst AB. Revisorn tillstyrker att föreningsstämman fastställer resultat- och balansräkningen samt beviljar styrelsens ledamöter ansvarsfrihet för räkenskapsåret 2025.",
            ],
        ],
    },
    {
        "name": "Styrelseprotokoll 2026-04-20.pdf",
        "pages": [
            [
                "# PROTOKOLL FRÅN STYRELSEMÖTE — BRF SJÖUTSIKTEN 7",
                "Datum: 20 april 2026. Plats: Gästlägenheten, Sjöutsiktsgatan 7, Göteborg. Närvarande: Marta Ceder (ordförande), Oskar Vinterberg (kassör), Lena Bäckström (sekreterare), Tobias Ek (ledamot) och Ruben Skoglund (ledamot). Anmält förhinder: Sara Malm (suppleant).",
                "# § 1 Mötets öppnande",
                "Ordföranden Marta Ceder öppnade mötet och hälsade alla välkomna. Protokollet från föregående möte den 9 mars 2026 godkändes och lades till handlingarna.",
                "# § 2 Renovering av bastun",
                "Styrelsen beslutade att anta offerten från Västkustbastu & Relax AB om 138 000 kronor inklusive moms för renovering av föreningens bastu. Arbetet omfattar nytt bastuaggregat, ny lavning i asp samt förbättrad ventilation och skall vara färdigställt senast den 31 augusti 2026. Under renoveringstiden håller bastun stängt.",
                "# § 3 Avgift för gästlägenheten",
                "Styrelsen beslutade att avgiften för gästlägenheten höjs från 250 kronor till 350 kronor per natt från och med den 1 juni 2026. Bokning sker liksom tidigare via medlemsportalen och gästlägenheten får hyras i högst fem nätter i följd.",
            ],
            [
                "# § 4 Byte av garageportar",
                "Styrelsen har inhämtat två offerter för byte av de tre garageportarna mot gården. Styrelsen beslutade att tilldela uppdraget till Portmontage Lindholmen AB enligt offert om 264 000 kronor exklusive moms. Arbetet planeras till vecka 38.",
                "# § 5 Bastuns ordningsregler",
                "Styrelsen fastställde uppdaterade ordningsregler för bastun. Bastun får användas mellan klockan 06:00 och 22:00, bokas via medlemsportalen och varje hushåll får boka högst tre pass per vecka. Engångsgrill och medhavd alkohol är inte tillåtna i relaxutrymmet.",
                "# § 6 Motion till föreningsstämman",
                "En motion om installation av en solcellsanläggning på det södra taket har lämnats in av medlemmen i lägenhet 41. Styrelsen beslutade att förorda avslag med hänvisning till den kommande takrenoveringen och hänskjuter frågan till den ordinarie föreningsstämman den 28 maj 2026.",
                "# § 7 Nästa möte och mötets avslutande",
                "Nästa ordinarie styrelsemöte hålls måndagen den 25 maj 2026 klockan 19:00 i gästlägenheten. Ordföranden förklarade därefter mötet avslutat.",
            ],
        ],
    },
    {
        "name": "Städ- och trädgårdsavtal 2026.pdf",
        "pages": [
            [
                "# AVTAL OM TRAPPSTÄDNING OCH TRÄDGÅRDSSKÖTSEL",
                "Mellan Bostadsrättsföreningen Sjöutsikten 7, org.nr 769633-8821, nedan kallad Föreningen, och Rent & Grönt i Väst AB, org.nr 559284-7130, nedan kallad Leverantören, har denna dag träffats följande avtal.",
                "# § 1 Städning av gemensamma utrymmen",
                "Trappstädning utförs varje helgfri måndag och omfattar sopning och våttorkning av samtliga trapphus, entréer och hissar samt avtorkning av ledstänger och postboxar. Storstädning med maskinskurning av entrégolven utförs två gånger per år, i april och i oktober. Fönsterputsning av entrépartierna ingår fyra gånger per år.",
                "# § 2 Trädgårdsskötsel",
                "Under perioden 1 april till 31 oktober ansvarar Leverantören för trädgårds-\nskötseln, vilket omfattar gräsklippning varannan vecka, ogräsrensning av rabatterna en gång per månad, vårstädning av gården samt beskärning av häckar och vresrosor två gånger per säsong. Ansvaret för trädgårdsskötseln får inte överlåtas till en underentreprenör utan Föreningens skriftliga godkännande.",
                "# § 3 Ersättning",
                "Föreningen betalar ett fast månadsarvode om 31 800 kronor exklusive mervärdesskatt. I arvodet ingår samtliga maskiner, redskap och förbrukningsmaterial. Extrabeställda arbeten utförs mot timpris om 495 kronor per person och timme efter skriftlig beställning av styrelsen.",
            ],
            [
                "# § 4 Avtalstid och uppsägning",
                "Avtalet gäller från och med den 1 februari 2026 till och med den 31 januari 2028. Om avtalet inte sägs upp förlängs det med tolv månader i taget. Avtalet får sägas upp skriftligen senast sex månader före avtalstidens utgång.",
                "# § 5 Kvalitet, försäkring och reklamation",
                "Leverantören skall inneha ansvarsförsäkring med ett försäkringsbelopp om lägst tio miljoner kronor samt följa Föreningens miljökrav, vilket bland annat innebär att endast miljömärkta rengöringsmedel får användas. Anmärkningar mot utfört arbete skall lämnas till Leverantörens arbetsledning inom fem arbetsdagar.",
                "# § 6 Avgränsning",
                "Snöröjning, halkbekämpning och invändig städning av lägenheter omfattas inte av detta avtal. Vid behov av vinterväghållning träffas separat överenskommelse mellan parterna.",
                "# § 7 Kontaktpersoner",
                "Leverantörens kontaktperson är arbetsledare Paulina Nyqvist, nåbar helgfria vardagar klockan 07.00 till 16.00. Föreningens kontaktperson är styrelsens ordförande.",
            ],
        ],
    },
]

# Golden set B: besvarbara frågor med ordagranna passager (verifieras med
# fitz search_for vid seedning) samt obesvarbara frågor. Minst två frågor är
# parafraserade utan nyckelordsöverlapp med passagen, och flera passager
# spänner över två renderade rader.
GOLDEN_ANSWERABLE_B: list[dict] = [
    # --- Stadgar ---
    {"question": "Hur fördelas årsavgifterna mellan lägenheterna?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Årsavgifterna fördelas mellan bostadsrätterna i förhållande till lägenheternas insatser"},
    # Lång passage (>12 ord) som spänner över flera renderade rader.
    {"question": "När ska månadsavgiften senast vara betald?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Årsavgiften betalas månadsvis i förskott och skall vara föreningen tillhanda senast den tjugofemte dagen i månaden före"},
    {"question": "Hur stor överlåtelseavgift får föreningen ta ut och vem betalar den?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "en överlåtelseavgift om högst 3,5 procent av prisbasbeloppet. Överlåtelseavgiften betalas av överlåtaren"},
    # Parafraserad fråga utan nyckelordsöverlapp med passagen; flerradig passage.
    {"question": "Kan min kusin bo i min bostad medan jag arbetar utomlands i ett år?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Upplåtelse av lägenheten i andra hand kräver styrelsens skriftliga medgivande. Medgivande lämnas för högst sex månader åt gången"},
    {"question": "Hur många ledamöter ska styrelsen bestå av?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Styrelsen består av lägst fyra och högst sju ledamöter med högst tre suppleanter"},
    {"question": "Vem tecknar föreningens firma?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Föreningens firma tecknas av ordföranden i förening med ytterligare en styrelseledamot"},
    {"question": "Måste föreningens revisor vara auktoriserad?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Revisorn skall vara auktoriserad eller godkänd"},
    # Parafraserad fråga utan nyckelordsöverlapp med passagen.
    {"question": "Hur länge i sträck kan mina föräldrar sova över när de kommer och hälsar på?", "document": "Stadgar Brf Sjöutsikten 7.pdf", "passage": "Gästlägenheten får hyras i högst fem nätter i följd av samma hushåll"},
    # --- Årsredovisning ---
    {"question": "Vilket år byggdes huset och hur många lägenheter finns det?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "Byggnaden uppfördes 1978 och rymmer 62 bostadslägenheter samt en kommersiell lokal"},
    {"question": "Vilket bolag sköter den ekonomiska förvaltningen?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "Den ekonomiska förvaltningen har under året skötts av Kajkanten Ekonomiförvaltning AB"},
    {"question": "Vad kostade bytet av fjärrvärmecentralen?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "byttes fjärrvärmecentralen ut till en kostnad av 985 000 kronor"},
    # Lång passage (>12 ord) som spänner över flera renderade rader.
    {"question": "Hur stora lån har föreningen och hos vilken bank?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "fastighetslån uppgick vid årets utgång till 32 400 000 kronor, fördelade på två lån hos Skärgårdsbanken Hypotek AB"},
    {"question": "Vilka lånenummer har föreningens fastighetslån?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "lånenummer 220445 och 220446"},
    {"question": "Hur mycket höjs årsavgifterna under 2026?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "höja årsavgifterna med 6 procent från och med den 1 juli 2026"},
    {"question": "Vad blev årets resultat 2025?", "document": "Årsredovisning 2025 Brf Sjöutsikten 7.pdf", "passage": "Årets resultat blev 215 000 kronor"},
    # --- Styrelseprotokoll ---
    {"question": "Vem är ordförande i föreningen?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "Marta Ceder (ordförande)"},
    {"question": "Vem renoverar bastun och vad kostar det?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "offerten från Västkustbastu & Relax AB om 138 000 kronor inklusive moms"},
    # Lång passage (>12 ord) som spänner över flera renderade rader.
    {"question": "Vad kostar gästlägenheten per natt efter höjningen?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "avgiften för gästlägenheten höjs från 250 kronor till 350 kronor per natt från och med den 1 juni 2026"},
    {"question": "Hur många bastupass får ett hushåll boka per vecka?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "varje hushåll får boka högst tre pass per vecka"},
    {"question": "Vilket företag ska byta garageportarna?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "tilldela uppdraget till Portmontage Lindholmen AB enligt offert om 264 000 kronor exklusive moms"},
    {"question": "När hålls föreningsstämman 2026?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "den ordinarie föreningsstämman den 28 maj 2026"},
    {"question": "När är nästa styrelsemöte?", "document": "Styrelseprotokoll 2026-04-20.pdf", "passage": "Nästa ordinarie styrelsemöte hålls måndagen den 25 maj 2026 klockan 19:00"},
    # --- Städ- och trädgårdsavtal ---
    # Lång passage (>12 ord) som spänner över flera renderade rader.
    {"question": "Hur ofta städas trapphusen?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "Trappstädning utförs varje helgfri måndag och omfattar sopning och våttorkning av samtliga trapphus"},
    # Adversariell: stycket innehåller den planterade avstavningen
    # "trädgårds-" / "skötseln"; passagen använder den sammanfogade ordformen
    # "trädgårdsskötseln" (senare i samma stycke) och pipelinen måste slå ihop
    # avstavningen för att förstå stycket (jfr korpus A:s "för-/valtningen").
    {"question": "Får Leverantören anlita en underentreprenör för trädgårdsskötseln?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "Ansvaret för trädgårdsskötseln får inte överlåtas till en underentreprenör utan Föreningens skriftliga godkännande"},
    # Adversariell: passagen ligger på raden direkt efter den planterade
    # avstavningen (samma mönster som korpus A:s golden intill "för-/valtningen").
    {"question": "Hur ofta klipps gräset på gården?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "vilket omfattar gräsklippning varannan vecka"},
    {"question": "Vad betalar föreningen per månad för städning och trädgård?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "fast månadsarvode om 31 800 kronor exklusive mervärdesskatt"},
    # Parafraserad fråga utan nyckelordsöverlapp med passagen.
    {"question": "Med vilken framförhållning måste samarbetet med städfirman avslutas om föreningen är missnöjd?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "Avtalet får sägas upp skriftligen senast sex månader före avtalstidens utgång"},
    {"question": "Ingår snöröjning i städavtalet?", "document": "Städ- och trädgårdsavtal 2026.pdf", "passage": "Snöröjning, halkbekämpning och invändig städning av lägenheter omfattas inte av detta avtal"},
]

GOLDEN_UNANSWERABLE_B: list[str] = [
    "Vilka tider gäller för tvättstugan?",
    "Finns det laddstolpar för elbil på föreningens parkering?",
    "Vad blev resultatet av den senaste OVK-besiktningen?",
    "Får man ha hund eller katt i lägenheten?",
    "Vilket försäkringsbolag har föreningen sin fastighetsförsäkring hos?",
    "Hur hög är insatsen för en trerumslägenhet?",
    "Vad kostar det att hyra föreningens takterrass för privata fester?",
]
