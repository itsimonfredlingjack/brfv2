# Hela acceptansen i den riktiga applikationen, 2026-08-03

Tre resor genom release-binären i ett riktigt Tauri/WebKitGTK-fönster, körda två
gånger i rad utan att något ändrades emellan. Ingenting nedan är simulerat:
klicken går genom WebDriver mot den installerade applikationen, generering sker
mot den självhostade Gemma 4 12B på `agenntserver`, och varje körning startar
från en genuint oprovisionerad maskin (isolerad `XDG_DATA_HOME` i en slängbar
temporärkatalog).

Två tidsberoende fel stängs här, och båda hade samma karaktär: en väntan på
något som aldrig kunde hända. Ingetdera gick att laga med en längre timeout.

## Körningarna

| | |
| -- | -- |
| Kommando | `BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 make desktop-acceptance-full RUN_LABEL=resan-2026-08-03-{1,2}` |
| Applikation | `src-tauri/target/release/brfv2-desktop`, SHA-256 `460686a0c964fb05481ef59da74db24ac005a5f6259c0c17ff96015f2a6d0c49` |
| Modell | `gemma4:e12b` (`gemma-4-12b-it-UD-Q4_K_XL.gguf`) på `agenntserver`, via SSH-tunnel till `127.0.0.1:8000` |
| Värd | Fedora 44, Wayland/KDE, WebKitGTK via `tauri-driver` 2.0.6 |
| Evidens | `resan-2026-08-03-{1,2}-{invoice,intake,desktop}-*.png` + tre kvitton per körning |

| Resa | Modell? | Körning 1 | Körning 2 |
| -- | -- | -- | -- |
| Fakturor (`invoice`) | nej | OK, 17,1 s | OK, 16,7 s |
| Inkommande post (`intake`) | nej | OK, 12,8 s | OK, 12,5 s |
| Full journey + livscykel + säkerhet + felytor (`desktop`) | **ja** | OK, 121,7 s | OK, 119,7 s |

Att två av tre går gröna utan modell är en egenskap hos funktionerna och inte
hos skripten: både fakturagranskningen och köns läsning är deterministiska hela
vägen.

## Fel 1 — bevakningsresan väntade på en genomläsning som aldrig startade

`desktop-acceptance` föll på `Timed out waiting for a dated proposal from the
shipped engine` efter 180 sekunder. Orsaken låg inte i motorn utan i klicket
före den.

`Läs om arkivet` är avstängd (`disabled`) medan bevakningstavlan hämtas — vilket
är rätt beteende. Acceptansen väntade bara på att knappen skulle *finnas*
(`.watches-scan`), och den finns redan i första renderingen. `element.click()`
på en avstängd knapp skickar **inget** event alls, men hjälparen rapporterade
ändå att klicket gått igenom, eftersom den bara kontrollerade att den hittat ett
element. Ingen genomläsning kördes, inget förslag kunde uppstå, och de 180
sekunderna var väntan på något som ingenting någonsin skulle producera.

Mätt vid klickögonblicket, med en sond som registrerade om något event
dispatchades:

```
[probe] click_text('Läs om arkivet') -> {'fired': False, 'disabled': True, ...}
[probe] wait FAILED 'a dated proposal from the shipped engine' after 180.1s
```

**Lagat i orsaken, inte i timeouten.** `WebDriver._press` skiljer nu på två
tillstånd som tidigare var ett: en kontroll som ännu inte går att trycka på är
normalt och väntas in, medan en kontroll som trycktes och inte dispatchade
någonting är ett fel som rapporteras direkt och namnger tillståndet. Väntan före
klicket säger dessutom vad den faktiskt beror på — `.watches-board`, som bara
renderas när tavlan är hämtad, i stället för knappen som alltid finns.

Efter lagningen, båda körningarna: förslaget `Säg upp eller ompröva avtalet
senast 2027-07-31` (2028-01-31 minus sex månader, uppsägningstiden ur det
uppladdade serviceavtalet), godkänt av en människa, i hinken **Senare**, med noll
förslag kvar. Se `resan-2026-08-03-{1,2}-desktop-watches.png`.

## Fel 2 — inbäddaren frågade Hugging Face, med vikterna redan på disken

Samma körning föll därefter på `Timed out waiting for association created` efter
240 sekunder. Att skapa den första föreningen bygger tenantens index, vilket
laddar inbäddaren — och `model2vec` frågar Hugging Face om vikterna vid varje
laddning även när de ligger i cachen. Mätt på den här checkouten:

| | Tid att ladda den *cachade* inbäddaren |
| -- | -- |
| Med Hugging Face onåbart, utan `HF_HUB_OFFLINE` | **136,9 s** |
| Med `HF_HUB_OFFLINE=1` | **2,3 s** |

Mot en väntan på 240 sekunder betyder det att en acceptanskörning kunde falla på
någon annans nätverk utan att ha testat någonting alls om den här produkten.
Fakturaresan satte redan flaggan för hand av precis det skälet; den paketerade
applikationen sätter den också. Utvecklingskörningen hade helt enkelt aldrig
fått den. Den ligger nu i `isolated_environment`, alltså i alla faser och alla
tre resorna.

## Fel 3 — ett tapppat paket avslutade en frisk resa

Fakturaresan föll två gånger av nio på `Remote end closed connection without
response`, alltid på begäran direkt efter en skärmbild. Sessionen var oskadd —
nästa begäran på en ny anslutning fungerade — men en resa som behandlar ett
tappat paket som ett produktfel går inte att köra rent två gånger i rad.

`tauri-driver` håller poolade anslutningar mot `WebKitWebDriver`, som stänger
sina lediga. En begäran kan alltså skickas ned i en anslutning som andra sidan
redan släppt. Att blint göra om begäran vore fel — ett omtaget klick är ett andra
beslut i den här produkten, inte ett andra försök — så varje skript lämnar nu ett
signerat spår av sin egen fullbordan i sidan. Vid ett tappat paket frågar
harnesset sidan om skriptet hann köra: hann det, tas värdet det lämnade efter
sig; hann det inte, skickas det om. Antalet står i kvittot (`transportRetries`)
i stället för att döljas — körning 1 behövde 2, körning 2 behövde 0.

## Fel 4 — ett bevarat meddelande syntes inte i arkivet

Det här hittades av den nya postresan och sitter i produkten, inte i harnesset.

Arbetsytans dokumentlista hämtas när föreningen byts. Granskningskön skapar
dokument *medan* arbetsytan är öppen — att bevara ett meddelande gör ett, att
adoptera en bilaga gör ett till — och ingenting berättade det för listan. Följden:
efter `Ta in` fanns meddelandet inte under **Dokument**, och knappen
`Öppna dokumentet` bredvid beslutet gjorde ingenting alls, eftersom
`openDocument` slog upp id:t i en lista det inte kunde stå i. Först vid byte av
förening eller omstart dök det upp.

Lagat på båda ställena: ett beslut i kön säger till arbetsytan att hämta om
dokumenten, och `openDocument` hämtar om listan själv när id:t inte finns i den
i stället för att tyst returnera. `inArchiveWithoutReload: true` i postresans
kvitto är påståendet som nu bevakas.

## Vad postresan går igenom

`make intake-acceptance`, kedjan `docs/INKOMMANDE-POST.md` beskriver, från
vänster till höger:

1. En tom kö **säger att den är tom**.
2. En `.eml` någon plockat fram blir ett kort med sin proveniens —
   `manual-file-import / eml-file`, vem som importerade, och innehållshashen
   dubblettregeln bygger på.
3. Läsningen visas som en läsning: varje signal bär orden den lästes ur, och
   frågan rapporteras som `Fråga som väntar svar`.
4. Beslutet **går inte att spara utan ett angivet skäl** — knappen är avstängd
   och säger varför.
5. Ett beslut bevarar meddelandet **och** gör en uppgift av det. Uppgiften bär
   ett *verifierat citat in i det bevarade dokumentet* — vilket är hela skälet
   till att ordningen är "bevara först".
6. Det bevarade meddelandet öppnas i arkivet, renderat (595×842), med sin
   proveniens tryckt på sidan.
7. **Att öppna igen raderar ingenting.** Uppgiften står kvar, `resolution` är
   tom, och det tidigare avgörandet ligger i postens `decision_history`.
8. **Ett nytt beslut är ett nytt beslut**: bevaka till 2026-10-01 hamnar på
   tavlan med samma citat, arkivet växer inte med en dubblett
   (`preserved_document_id` oförändrat), och det tidigare avgörandet ligger
   kvar i historiken bredvid.

## Vad som inte prövas här

* Resorna körs mot checkoutens release-binär, inte mot den installerade RPM:en.
  För artefaktidentitet finns `make desktop-acceptance-installed RPM=...`.
* Tunneln till `agenntserver` upprättades över LAN-aliaset `agenntserver-lan`
  (samma värd, samma modelltjänst) eftersom Tailscale SSH kräver en interaktiv
  webbinloggning som inte kan göras från en körning.
* Postresans kö matas av en `.eml` en människa väljer. Hämtning mot en riktig
  Graph-brevlåda ingår inte — den har inga inloggningsuppgifter här.
