# Träff Mobile RC1 — slutrapport

**Status:** kärnflöde och visuell identitet godkända på fysisk Android-enhet,
2026-08-01.

RC1 är den första bygget där Träff-identiteten och hela frågeflödet har körts
och granskats på riktig hårdvara mot en riktig backend — riktig inloggning,
riktig återvinning, riktig citatverifiering, riktig siduppritning och riktig
markeringsplacering. Endast den genererade texten är deterministisk.

## Artefakt

Byggd APK:

```
kalla-native/android/app/build/outputs/apk/release/app-release.apk
```

Arkiverad kopia (`expo prebuild` raderar alltid `android/`, så sökvägen ovan
överlever inte nästa prebuild):

```
artifacts/traff-mobile-rc1/traff-mobile-rc1.apk
```

| Egenskap | Värde |
| --- | --- |
| Storlek | 46 465 696 byte |
| SHA-256 | `39069ceb9b7ce6c2c3ce11f3e914673d6bf7cb26220114067410b2478be13cc6` |
| ABI | arm64-v8a |
| JS-bunt | inbäddad (Hermes) |
| versionName | 1.0.0 |
| Applikationsetikett | Träff |
| Paket | se.gjutformen.kalla |

Hashen för `base.apk` på enheten är identisk med den byggda filen, så
verifieringen nedan gjordes mot exakt denna artefakt.

**Signering:** bygget använder fortfarande Expo-mallens debug-keystore. Måste
bytas före extern distribution.

## Kontroller

| Kontroll | Resultat |
| --- | --- |
| `npm run typecheck` | PASS |
| `npm run lint` | PASS — 0 fel, 0 varningar |
| `npm test` | 44 tester, samtliga PASS |

## Testrigg

- **Enhet:** Samsung SM-F766B (Galaxy Z Flip7), Android 16 / SDK 36,
  arm64-v8a, 1080×2520 @ 480 dpi, innerskärmen, stående format.
- **Backend:** `backend/scripts/e2e_server.py` med `BRF_LLM=scripted`, nådd
  över `adb reverse tcp:8787 tcp:8787`.

Riggen äger en egen temporär datarot under hela sin livstid och rör aldrig
`backend/data`.

### Sessionsspärr efter omstart av riggen — förväntat beteende

Startar man om den efemära backenden hamnar appen på inloggningsskärmen.
**Detta är förväntat riggbeteende, inte ett appfel.** `e2e_server.py` bygger en
ny autentiseringsdatabas i en ny temporärkatalog vid varje start, så kakor
signerade av föregående instans avvisas korrekt. Appens egen data överlever:
journalen under SENAST var intakt efter både omstarten och två ominstallationer.

## Visuell verifiering på enheten

Skärmbilder i [`rc1/skarmbilder/`](rc1/skarmbilder), animationsremsor i
[`rc1/strips/`](rc1/strips).

| Yta | Verifierat | Bild |
| --- | --- | --- |
| Låsikon och etikett | fullständigt ◉ på nästan svart squircle, etikett "Träff" med korrekt Ä | `09-ikon.png` |
| Inloggning | ◉ Träff-lockup i Instrument Serif, tvåradig serif-ingress, Ä återges korrekt, tangentbordet lyfter formuläret över IME | `01-login.png` |
| Fråga / vila | ◉ Träff-header, stiliserad dokumenthög, ljussvepet passerar över papperet, `◯ INGEN FRÅGA STÄLLD` | `02-fraga-vila.png` |
| Högen, detalj | mörk rubrik, sex brödtextrader med raggade slut, gul överstrykning, underrubrik, svag foliorad | `03-hogen-detalj.png` |
| Söker | bruten ring roterar, mitten tom, riktiga träffar med poäng i mono och två decimaler | `strips/soker-rotation-4-bilder.png` |
| Belagt | ◉ BELAGT, fullständig ring med koncentrisk kärna, ORDAGRANT VERIFIERAT | `04-belagt.png` |
| Källa | markeringen landar exakt på "§ 6 Upplåtelse i andra hand", sidfoten helt synlig | `05-kalla.png` |
| Visa | VISA-LÄGE-överlägget intakt | `07-visa.png` |
| Ej belagt | stor bärnstensfärgad ring med helt tom mitt, ◉ EJ BELAGT, HÖGEN GENOMSÖKTES ÄNDÅ | `06-ejbelagt.png` |
| Konto | ◉ Träff-sidfot, VERSION 1.0.0, MODELL faller korrekt tillbaka | `08-konto.png` |
| Android Back | ett lager per tryck: Visa → Källa → Svar → Fråga | `strips/back-fraga-svar-fraga.png` |
| Kärnflöde | fråga → söker → svar → källa → tillbaka, nytt svar dyker upp i SENAST | `strips/kalla-svar-fraga.png` |
| Ljussvep | ett enda band vandrar hela bredden, ovanpå papperet i varje fas | `strips/ljussvep-6-bilder.png` |

Ytterligare kontrollerat: sessionsåterställning över `force-stop`, 1,3×
textskala utan avklippning, och att inga tryckytor påverkades av
z-ordningsrättningen.

`07-visa.png` och `08-konto.png` kommer från identitetspasset strax före RC1.
Övriga bilder är tagna på RC1-bygget.

## Identiteten

"Träff · visuell identitet v2" (juli 2026) är högsta visuella sanningskälla.
Den ratificerade den befintliga paletten och typrollerna oförändrade, så
namnbytet rörde namnet och märket — inte betydelserna.

◉ bär två betydelser som aldrig får blandas ihop:

- **Varumärket** (`BrandMark`, `Wordmark`) — alltid fullständigt, alltid
  monokromt. Säger *vem som talar*, så det bär aldrig en tillståndsfärg.
- **Statusmärket** (`StatusMark`, `StatusChip`) — börjar tomt och ritar sin
  kärna först i samma ögonblick en passage verifierats ordagrant.

Status bärs aldrig av märket ensamt: varje tillstånd har sin monoetikett och
en talad form för skärmläsare. Ett äkta fel — nätverk, session, modell — är
*inte* `ejbelagt` och behåller felbehandlingen, eftersom det inte är ett
påstående om korpusen.

`src/theme/brand.ts` håller de fyra låsta talen (ring 8 % av ytterdiametern,
kärna 46 % av innermåttet, minst 16 dp, märket 52 % av ikonfältet).
`scripts/make-brand-icons.py` återskapar samtliga ikonresurser ur dem.

## Ändringar sedan identitetspasset

Allt i `src/components/CorpusStack.tsx`.

**Dokumentsignal på översta arket.** Högen såg tom ut — en vit kartongbit
snarare än papper. Översta arket har nu mörk rubrik, sex brödtextrader som
raggar (100 → 93 → 61 %, 97 → 79 → 46 %), en gul överstruken passage,
underrubrik och en svag foliorad. Allt i en enda bläckfärg vid olika vikt, så
det komponeras som sättning på papper. Stiliserat, aldrig läsbart.

Två avvägningar värda att känna till:

- Den överstrukna raden bär mer bläck (48 %) än övriga brödtextrader (20 %).
  Med samma vikt slukade det gula raden helt och märket slutade läsas som en
  markering.
- Det gula ligger på 0,30 mot `color.hlFill` 0,42. Arket sitter direkt ovanför
  ◉ INGEN FRÅGA STÄLLD; i full styrka skulle illustrationen påstå att något
  redan hittats medan statusmärket säger att inget har det.

**Ljussvepets z-ordning.** `styles.sweep` saknade `zIndex` och hamnade därmed
på 0 medan arken bär `zIndex: 0–4`. De fyra övre arken målade över svepet, så
ljuset föll *bakom* högen och bara den del som stack ut utanför papperet syntes
— en grå klump bredvid stapeln i stället för ett ljus som rör sig över
korpusen. Rättat med `zIndex: LAYERS.length`.

En observation som rättningen blottlade, inte ett fel: svepet är en solid
`color.light`-fyllning, så över vitt papper läses det som en genomskinlig panel
med hårda lodräta kanter snarare än som mjukt ljus. En gradient — samma
`RadialGradient`-idiom som halon i `StatusMark` redan använder — skulle mjuka
upp det. Det ändrar kompositionen och gjordes inte.

## Kända punkter som flyttas vidare utan att blockera RC1

1. Riktig release-signering före extern distribution.
2. Mörk Android-navigation i ljust systemläge.
3. Riktig LLM-verifiering av de svårutlösta vägransvarianterna.
4. Fler enhetsformat och TalkBack.
5. Interna `kalla`-identifierare behålls för uppgraderingskompatibilitet —
   paket-id `se.gjutformen.kalla`, schema `kalla`, lagringsnycklar `kalla.*`.
   Osynliga för användaren; att byta dem installerar en andra app och tvingar
   fram ny inloggning.
