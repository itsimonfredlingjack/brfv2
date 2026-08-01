# -*- coding: utf-8 -*-
"""Synthetic (fictional) Swedish BRF corpus for Brf Gjutformen 12.

Structure: each document is a list of pages; each page a list of paragraphs.
"# " prefix renders as heading. "\n" inside a paragraph is a hard line break
(used to plant one deliberate hyphenation split). All numbers, names and
organisations are invented.
"""

FOOTER = "Brf Gjutformen 12 · Org.nr 769621-4455 · Handlingen förvaras hos styrelsen"

DOCUMENTS: list[dict] = [
    {
        "name": "Stadgar Brf Gjutformen 12.pdf",
        "pages": [
            [
                "# STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN GJUTFORMEN 12",
                "Antagna vid ordinarie föreningsstämma den 21 maj 2024 och registrerade hos Bolagsverket den 2 september 2024.",
                "# § 1 Firma och säte",
                "Föreningens firma är Bostadsrättsföreningen Gjutformen 12. Styrelsen har sitt säte i Göteborgs kommun.",
                "# § 2 Ändamål",
                "Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att i föreningens hus upplåta bostadslägenheter och lokaler under nyttjanderätt och utan tidsbegränsning.",
                "# § 3 Medlemskap",
                "Medlemskap kan beviljas fysisk person som övertar bostadsrätt i föreningens hus. Ansökan om medlemskap prövas av styrelsen. Juridisk person som förvärvat bostadsrätt till en bostadslägenhet får vägras medlemskap.",
                "# § 4 Insats och årsavgift",
                "Insats och årsavgift fastställs av styrelsen. Årsavgiften fördelas på bostadsrätterna i förhållande till lägenheternas andelstal. Årsavgiften betalas månadsvis i förskott senast sista vardagen före varje kalendermånads början.",
            ],
            [
                "# § 5 Överlåtelse- och pantsättningsavgift",
                "Överlåtelseavgift får tas ut med högst 2,5 procent av prisbasbeloppet och betalas av förvärvaren. Pantsättningsavgift får tas ut med högst 1 procent av prisbasbeloppet och betalas av pantsättaren.",
                "# § 6 Upplåtelse i andra hand",
                "En bostadsrättshavare får upplåta sin lägenhet i andra hand endast om styrelsen ger sitt skriftliga samtycke. Avgift för andrahandsupplåtelse får tas ut med högst 10 procent av prisbasbeloppet per år. Samtycke lämnas normalt för högst ett år i taget.",
                "# § 7 Bostadsrättshavarens ansvar",
                "Bostadsrättshavaren skall på egen bekostnad hålla lägenhetens inre i gott skick. Detta omfattar bland annat ytskikt på väggar, golv och tak, inredning i kök och badrum samt glas i fönster och dörrar. Föreningen svarar för husets skick i övrigt, däribland stammar för vatten- och avloppssystem.",
                "# § 8 Styrelsen",
                "Styrelsen består av lägst tre och högst fem ledamöter med högst två suppleanter. Ledamöter väljs av föreningsstämman för en mandattid om ett år. Styrelsen är beslutför när fler än hälften av ledamöterna är närvarande.",
            ],
            [
                "# § 9 Firmateckning",
                "Föreningens firma tecknas av två styrelseledamöter i förening.",
                "# § 10 Revisor och valberedning",
                "Föreningsstämman väljer årligen en revisor och en suppleant. Revisorn behöver inte vara auktoriserad. Stämman utser även en valberedning om minst två personer.",
                "# § 11 Föreningsstämma",
                "Ordinarie föreningsstämma hålls årligen före juni månads utgång. Kallelse till föreningsstämma skall ske tidigast sex veckor och senast två veckor före stämman. Kallelsen anslås i trapphusen och skickas med e-post till medlemmarna.",
                "# § 12 Vinstdisposition",
                "Fritt eget kapital enligt fastställd balansräkning skall, sedan avsättning till underhållsfonden skett, balanseras i ny räkning.",
            ],
        ],
    },
    {
        "name": "Årsredovisning 2025.pdf",
        "pages": [
            [
                "# ÅRSREDOVISNING 2025 — BOSTADSRÄTTSFÖRENINGEN GJUTFORMEN 12",
                "Styrelsen för Bostadsrättsföreningen Gjutformen 12, organisationsnummer 769621-4455, avger härmed årsredovisning för räkenskapsåret 1 januari till 31 december 2025.",
                "# Förvaltningsberättelse",
                "Föreningens fastighet Gjutformen 12 i Göteborg uppfördes 1962 och omfattar 48 bostadslägenheter samt två kommersiella lokaler. Den totala boytan uppgår till 3 412 kvadratmeter.",
                "Den tekniska förvaltningen har under året skötts av Driftia Fastighetsservice AB medan den löpande ekonomiska för-\nvaltningen har skötts av SBC Sveriges BostadsrättsCentrum AB.",
                "# Väsentliga händelser under året",
                "Under 2025 genomfördes etapp 1 av relining av avloppsstammarna till en kostnad av 1 850 000 kronor. Arbetet slutbesiktigades i oktober utan anmärkning. Vidare färdigställdes en ny gemensam tvättstuga i källarplanet.",
            ],
            [
                "# Ekonomi",
                "Nettoomsättningen uppgick till 4 312 000 kronor, varav årsavgifter utgjorde 3 890 000 kronor. Driftskostnaderna uppgick till 2 780 000 kronor och räntekostnaderna till 645 000 kronor. Årets resultat blev -142 000 kronor.",
                "Föreningens fastighetslån uppgick vid årets utgång till 21 500 000 kronor, fördelade på tre lån hos Stadshypotek. Den genomsnittliga räntan var 3,1 procent.",
                "Styrelsen beslutade i november 2025 att höja årsavgifterna med 4 procent från och med den 1 januari 2026 för att möta ökade räntekostnader.",
                "# Underhållsfond",
                "Avsättning till underhållsfonden sker enligt stadgarna med 300 000 kronor per år. Fonden uppgick vid årets slut till 1 420 000 kronor.",
            ],
            [
                "# Flerårsöversikt",
                "Nettoomsättningen har ökat från 3 995 000 kronor år 2023 till 4 312 000 kronor år 2025. Soliditeten uppgick till 38 procent. Belåningen per kvadratmeter boyta var 6 301 kronor.",
                "# Förslag till resultatdisposition",
                "Styrelsen föreslår att årets resultat om -142 000 kronor jämte balanserat resultat, sammanlagt -389 000 kronor, balanseras i ny räkning.",
                "# Revisionsberättelse i sammandrag",
                "Revisorn tillstyrker att föreningsstämman fastställer resultaträkningen och balansräkningen samt beviljar styrelsens ledamöter ansvarsfrihet för räkenskapsåret.",
            ],
        ],
    },
    {
        "name": "Styrelseprotokoll 2026-03-12.pdf",
        "pages": [
            [
                "# PROTOKOLL FÖRT VID STYRELSEMÖTE — BRF GJUTFORMEN 12",
                "Datum: 12 mars 2026. Plats: Föreningslokalen, Gjutformsgatan 4. Närvarande: Karin Lindqvist (ordförande), Jonas Berg (kassör), Amira Chowdhury (sekreterare), Per Sandin (ledamot). Frånvarande: Eva Norlin (suppleant).",
                "# § 1 Mötets öppnande och föregående protokoll",
                "Ordföranden förklarade mötet öppnat. Föregående protokoll från den 5 februari 2026 lades till handlingarna utan anmärkning.",
                "# § 2 Fasadmålning",
                "Styrelsen beslutade att genomföra fasadmålning av gårdsfasaden under sommaren 2026. Uppdraget tilldelas Måleri Väst AB enligt offert om 450 000 kronor inklusive ställning och materiel. Jonas Berg fick i uppdrag att teckna avtalet.",
                "# § 3 OVK-besiktning",
                "Obligatorisk ventilationskontroll skall genomföras i maj 2026. Driftia Fastighetsservice AB samordnar tillträde till samtliga lägenheter. Besiktningen skall vara genomförd och protokollförd senast den 31 maj 2026, och återkommer därefter vart tredje år.",
            ],
            [
                "# § 4 Laddstolpar",
                "Styrelsen har inhämtat offert från Chargepark AB om 96 000 kronor för installation av sex laddplatser på gårdens parkering. Frågan utreds vidare och beslut fattas vid nästa möte sedan bidragsmöjligheter undersökts.",
                "# § 5 Tvättstugans avgift",
                "Styrelsen beslutade att avgiften för tvättstugan höjs till 20 kronor per bokat pass från den 1 april 2026. Intäkterna öronmärks för underhåll av maskinparken.",
                "# § 6 Motion om cykelrum",
                "En motion om utbyggt cykelrum har inkommit från medlemmen i lägenhet 24. Styrelsen beslutade att hänskjuta motionen till ordinarie föreningsstämma med rekommendationen att bifalla den.",
                "# § 7 Nästa möte och avslutning",
                "Nästa styrelsemöte hålls den 16 april 2026 klockan 18:30. Ordföranden förklarade mötet avslutat.",
            ],
        ],
    },
    {
        "name": "Snöröjningsavtal 2026.pdf",
        "pages": [
            [
                "# AVTAL OM SNÖRÖJNING OCH HALKBEKÄMPNING",
                "Mellan Bostadsrättsföreningen Gjutformen 12, org.nr 769621-4455, nedan kallad Föreningen, och Snösvängen Entreprenad AB, org.nr 556812-3344, nedan kallad Entreprenören, har denna dag träffats följande avtal.",
                "# § 1 Omfattning",
                "Entreprenören åtar sig att utföra snöröjning och halkbekämpning av Föreningens gemensamma körytor, gångbanor, entréer samt parkeringsplatser enligt bifogad områdeskarta.",
                "# § 2 Jourperiod och inställelse",
                "Jourperioden löper från den 15 november till den 15 april. Utryckning sker automatiskt vid ett snödjup om 5 centimeter. Inställelsetiden är högst fyra timmar från avslutat snöfall. Halkbekämpning utförs i förebyggande syfte eller senast en timme efter avslutad snöröjning.",
            ],
            [
                "# § 3 Ersättning",
                "Ersättning utgår enligt följande prislista: maskinell snöröjning med traktor 1 250 kronor per timme, manuell skottning av trappor och entréer 450 kronor per timme samt halkbekämpning med sand eller salt 350 kronor per säck. Samtliga priser är angivna exklusive mervärdesskatt.",
                "# § 4 Avtalstid och uppsägning",
                "Avtalet gäller från den 1 november 2026 och tills vidare. Uppsägning skall ske skriftligen senast tre månader före avtalstidens utgång.",
                "# § 5 Ansvar och anmärkningar",
                "Entreprenören ansvarar för skador på egendom som orsakas av vårdslöshet vid arbetets utförande och skall inneha gällande ansvarsförsäkring. Eventuella anmärkningar mot utfört arbete skall anmälas till Entreprenören inom 24 timmar efter avslutat arbetspass.",
            ],
        ],
    },
    {
        "name": "Underhållsplan 2026-2036.pdf",
        "pages": [
            [
                "# UNDERHÅLLSPLAN 2026–2036 — BRF GJUTFORMEN 12",
                "Denna underhållsplan är upprättad i februari 2026 av Byggkonsult Väst AB på uppdrag av styrelsen. Planen omfattar fastighetens gemensamma delar under perioden 2026 till 2036 och revideras vart tredje år.",
                "# Metodik",
                "Planen bygger på okulär besiktning av fastigheten genomförd i januari 2026 samt på leverantörernas serviceprotokoll. Kostnaderna är angivna i 2026 års prisnivå exklusive mervärdesskatt.",
                "# Sammanfattning",
                "Det samlade underhållsbehovet under planperioden bedöms till 18 650 000 kronor. De största posterna är stambyte av badrumsstammarna år 2032 samt takomläggningen år 2028.",
            ],
            [
                "# Åtgärdsplan 2026–2030",
                "År 2026 genomförs etapp 2 av relining av avloppsstammarna till en beräknad kostnad av 1 900 000 kronor.",
                "År 2027 planeras fönsterbyte på söderfasaden till en beräknad kostnad av 2 400 000 kronor. Befintliga tvåglasfönster ersätts med energiglas.",
                "År 2028 genomförs takomläggning inklusive ny plåtbeslagning till en beräknad kostnad av 3 100 000 kronor.",
                "År 2029 renoveras hissen i port 4 till en beräknad kostnad av 850 000 kronor.",
                "År 2030 utförs omputsning av gårdsfasadens sockel till en beräknad kostnad av 1 200 000 kronor.",
            ],
            [
                "# Åtgärdsplan 2031–2036",
                "År 2032 genomförs stambyte av badrumsstammarna med tillhörande våtrumsrenovering till en beräknad kostnad av 8 500 000 kronor. Åtgärden samordnas med byte av elstigare.",
                "År 2034 byts ventilationsaggregatet på vinden till en beräknad kostnad av 700 000 kronor.",
                "# Finansiering",
                "Underhållet finansieras genom årlig avsättning till underhållsfonden om 300 000 kronor samt genom nyupplåning i samband med stambytet. Styrelsen bör inför år 2031 uppdatera finansieringskalkylen tillsammans med föreningens bank.",
            ],
        ],
    },
]

# Golden set: answerable questions with verbatim passages (page located at
# seed time via search_for — self-validating), plus unanswerable questions.
GOLDEN_ANSWERABLE: list[dict] = [
    # --- Stadgar ---
    {"question": "Var har styrelsen sitt säte?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Styrelsen har sitt säte i Göteborgs kommun"},
    {"question": "Hur fördelas årsavgiften mellan lägenheterna?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Årsavgiften fördelas på bostadsrätterna i förhållande till lägenheternas andelstal"},
    {"question": "När ska årsavgiften betalas?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Årsavgiften betalas månadsvis i förskott senast sista vardagen före varje kalendermånads början"},
    {"question": "Hur stor överlåtelseavgift får föreningen ta ut?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Överlåtelseavgift får tas ut med högst 2,5 procent av prisbasbeloppet"},
    {"question": "Vem betalar pantsättningsavgiften?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Pantsättningsavgift får tas ut med högst 1 procent av prisbasbeloppet och betalas av pantsättaren"},
    {"question": "Vad krävs för att hyra ut sin lägenhet i andra hand?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "får upplåta sin lägenhet i andra hand endast om styrelsen ger sitt skriftliga samtycke"},
    {"question": "Hur hög avgift får tas ut vid andrahandsuthyrning?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Avgift för andrahandsupplåtelse får tas ut med högst 10 procent av prisbasbeloppet per år"},
    {"question": "Vem ansvarar för lägenhetens inre underhåll?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Bostadsrättshavaren skall på egen bekostnad hålla lägenhetens inre i gott skick"},
    {"question": "Vem ansvarar för vatten- och avloppsstammarna?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Föreningen svarar för husets skick i övrigt, däribland stammar för vatten- och avloppssystem"},
    {"question": "Hur många ledamöter ska styrelsen ha?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Styrelsen består av lägst tre och högst fem ledamöter med högst två suppleanter"},
    {"question": "Hur lång är styrelseledamöternas mandattid?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Ledamöter väljs av föreningsstämman för en mandattid om ett år"},
    {"question": "Vem får teckna föreningens firma?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Föreningens firma tecknas av två styrelseledamöter i förening"},
    {"question": "När måste kallelse till föreningsstämman skickas ut?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Kallelse till föreningsstämma skall ske tidigast sex veckor och senast två veckor före stämman"},
    {"question": "Måste revisorn vara auktoriserad?", "document": "Stadgar Brf Gjutformen 12.pdf", "passage": "Revisorn behöver inte vara auktoriserad"},
    # --- Årsredovisning ---
    {"question": "Vilket år byggdes fastigheten?", "document": "Årsredovisning 2025.pdf", "passage": "uppfördes 1962 och omfattar 48 bostadslägenheter samt två kommersiella lokaler"},
    {"question": "Hur många lägenheter finns i föreningen?", "document": "Årsredovisning 2025.pdf", "passage": "omfattar 48 bostadslägenheter samt två kommersiella lokaler"},
    {"question": "Vem sköter den tekniska förvaltningen?", "document": "Årsredovisning 2025.pdf", "passage": "Den tekniska förvaltningen har under året skötts av Driftia Fastighetsservice AB"},
    {"question": "Vad kostade reliningen av avloppsstammarna?", "document": "Årsredovisning 2025.pdf", "passage": "etapp 1 av relining av avloppsstammarna till en kostnad av 1 850 000 kronor"},
    {"question": "Hur stor var nettoomsättningen 2025?", "document": "Årsredovisning 2025.pdf", "passage": "Nettoomsättningen uppgick till 4 312 000 kronor"},
    {"question": "Vad blev årets resultat 2025?", "document": "Årsredovisning 2025.pdf", "passage": "Årets resultat blev -142 000 kronor"},
    {"question": "Hur stora är föreningens lån?", "document": "Årsredovisning 2025.pdf", "passage": "fastighetslån uppgick vid årets utgång till 21 500 000 kronor"},
    {"question": "Med hur mycket höjdes årsavgifterna 2026?", "document": "Årsredovisning 2025.pdf", "passage": "höja årsavgifterna med 4 procent från och med den 1 januari 2026"},
    {"question": "Hur mycket avsätts till underhållsfonden varje år?", "document": "Årsredovisning 2025.pdf", "passage": "Avsättning till underhållsfonden sker enligt stadgarna med 300 000 kronor per år"},
    {"question": "Hur hög var soliditeten?", "document": "Årsredovisning 2025.pdf", "passage": "Soliditeten uppgick till 38 procent"},
    # Adversarial: the passage sits right after the planted hyphenation split
    # ("för-" / "valtningen") — exercises §2.5 through the whole pipeline.
    {"question": "Vilket företag sköter den ekonomiska förvaltningen?", "document": "Årsredovisning 2025.pdf", "passage": "har skötts av SBC Sveriges BostadsrättsCentrum AB"},
    # Adversarial: passage phrased differently from the natural question.
    {"question": "Hur ofta ska underhållsplanen uppdateras?", "document": "Underhållsplan 2026-2036.pdf", "passage": "revideras vart tredje år"},
    {"question": "Vad ersätts de gamla fönstren med?", "document": "Underhållsplan 2026-2036.pdf", "passage": "Befintliga tvåglasfönster ersätts med energiglas"},
    # --- Protokoll ---
    {"question": "Vem är ordförande i styrelsen?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "Karin Lindqvist (ordförande)"},
    {"question": "Vilket företag ska utföra fasadmålningen?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "Uppdraget tilldelas Måleri Väst AB enligt offert om 450 000 kronor"},
    {"question": "Vad kostar fasadmålningen?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "offert om 450 000 kronor inklusive ställning och materiel"},
    {"question": "När ska OVK-besiktningen genomföras?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "Obligatorisk ventilationskontroll skall genomföras i maj 2026"},
    {"question": "Vad kostar installationen av laddstolpar enligt offerten?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "offert från Chargepark AB om 96 000 kronor för installation av sex laddplatser"},
    {"question": "Vad beslutades om tvättstugans avgift?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "avgiften för tvättstugan höjs till 20 kronor per bokat pass från den 1 april 2026"},
    {"question": "När hålls nästa styrelsemöte?", "document": "Styrelseprotokoll 2026-03-12.pdf", "passage": "Nästa styrelsemöte hålls den 16 april 2026 klockan 18:30"},
    # --- Snöröjningsavtal ---
    {"question": "Vilken dag startar snöröjningsjouren?", "document": "Snöröjningsavtal 2026.pdf", "passage": "Jourperioden löper från den 15 november till den 15 april"},
    {"question": "Vid vilket snödjup sker utryckning?", "document": "Snöröjningsavtal 2026.pdf", "passage": "Utryckning sker automatiskt vid ett snödjup om 5 centimeter"},
    {"question": "Hur snabbt efter snöröjning ska halkbekämpning ske?", "document": "Snöröjningsavtal 2026.pdf", "passage": "Halkbekämpning utförs i förebyggande syfte eller senast en timme efter avslutad snöröjning"},
    {"question": "Vad kostar maskinell snöröjning per timme?", "document": "Snöröjningsavtal 2026.pdf", "passage": "maskinell snöröjning med traktor 1 250 kronor per timme"},
    {"question": "Hur lång är uppsägningstiden för snöröjningsavtalet?", "document": "Snöröjningsavtal 2026.pdf", "passage": "Uppsägning skall ske skriftligen senast tre månader före avtalstidens utgång"},
    {"question": "Inom vilken tid ska anmärkningar mot snöröjningen anmälas?", "document": "Snöröjningsavtal 2026.pdf", "passage": "anmälas till Entreprenören inom 24 timmar efter avslutat arbetspass"},
    # --- Underhållsplan ---
    {"question": "Vem har upprättat underhållsplanen?", "document": "Underhållsplan 2026-2036.pdf", "passage": "upprättad i februari 2026 av Byggkonsult Väst AB på uppdrag av styrelsen"},
    {"question": "Hur stort är det samlade underhållsbehovet?", "document": "Underhållsplan 2026-2036.pdf", "passage": "Det samlade underhållsbehovet under planperioden bedöms till 18 650 000 kronor"},
    {"question": "När planeras fönsterbytet och vad beräknas det kosta?", "document": "Underhållsplan 2026-2036.pdf", "passage": "År 2027 planeras fönsterbyte på söderfasaden till en beräknad kostnad av 2 400 000 kronor"},
    {"question": "Vad beräknas takomläggningen kosta?", "document": "Underhållsplan 2026-2036.pdf", "passage": "takomläggning inklusive ny plåtbeslagning till en beräknad kostnad av 3 100 000 kronor"},
    {"question": "Vilket år ska stambytet genomföras?", "document": "Underhållsplan 2026-2036.pdf", "passage": "År 2032 genomförs stambyte av badrumsstammarna med tillhörande våtrumsrenovering"},
    {"question": "Vad kostar stambytet enligt planen?", "document": "Underhållsplan 2026-2036.pdf", "passage": "stambyte av badrumsstammarna med tillhörande våtrumsrenovering till en beräknad kostnad av 8 500 000 kronor"},
]

GOLDEN_UNANSWERABLE: list[str] = [
    "Vad kostar en parkeringsplats i garaget per månad?",
    "Vilka regler gäller för bastun?",
    "Vilket arvode får styrelsens ledamöter?",
    "Vilken bredbandsleverantör har föreningen avtal med?",
    "Vilket försäkringsbolag har föreningen sin fastighetsförsäkring hos?",
    "Vilket datum hålls årsstämman 2026?",
    "Vad kostar det att hyra föreningens övernattningslägenhet?",
    "Hur många hundar får man ha i lägenheten?",
    "Vad blev resultatet av radonmätningen?",
    "Vilken bank gav bäst ränta vid den senaste omsättningen av lån?",
]
