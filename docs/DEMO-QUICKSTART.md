# Så startar du demot

Den här guiden är skriven för att du ska kunna starta och visa demot även om
du aldrig har använt Terminal-appen förut. Följ stegen i ordning, i den
takten du behöver. (Vill du ha mer teknisk bakgrund finns det i
[`DEMO-RUNBOOK.md`](./DEMO-RUNBOOK.md) — men den behöver du inte för att
klara det här.)

Allt nedan görs på Simons Mac.

## Innan du börjar

Du kommer att behöva öppna en app som heter **Terminal**. Det är en svart
(eller vit) ruta där du skriver eller klistrar in text och trycker Enter.
Det ser läskigt ut men du gör bara två saker i den: klistrar in en rad text,
och trycker Enter. Så här öppnar du den:

1. Tryck **Cmd + mellanslag** (Command-tangenten, längst ner till vänster
   eller höger på tangentbordet, + blanksteg).
2. Skriv `terminal`.
3. Tryck Enter.

Ett fönster med text öppnas. Det är rätt ställe.

## Steg 1 — öppna anslutningen till AI-datorn

Demot pratar med en AI-modell som körs på en annan dator hemma. För att det
ska funka på cafét behöver du öppna en anslutning dit först.

1. Öppna Terminal (se ovan).
2. Klistra in exakt den här raden och tryck Enter:

   ```
   ssh -N -L 8000:127.0.0.1:8000 agenntserver
   ```

3. **Lämna det här Terminal-fönstret öppet och orört** hela tiden du visar
   demot. Det ska inte hända något mer i det fönstret — ingen text, ingen
   prompt. Tystnad = det funkar. Stäng du fönstret av misstag slutar demot
   fungera tills du öppnar en ny anslutning igen.

   Om det istället dyker upp en webbadress (en länk som börjar på
   `https://login.tailscale.com/...`) — öppna den länken i webbläsaren och
   klicka igenom godkännandet där. Sen ska Terminal-fönstret bli tyst igen,
   precis som ovan.

## Steg 2 — starta själva demot

1. Öppna **ett nytt** Terminal-fönster (tryck **Cmd + N** medan Terminal är
   öppen — rör inte fönstret från Steg 1).
2. Klistra in den här raden och tryck Enter:

   ```
   cd /Users/coffeedev/Projects/brfv2 && make demo
   ```

3. Vänta. Det tar upp till någon minut. Du ska till slut se en grön text som
   säger `Demo igång:` följt av en webbadress och inloggningsuppgifter.
   Det betyder att allt är klart.

## Steg 3 — öppna demot i webbläsaren

Gå till den här adressen i valfri webbläsare:

**http://127.0.0.1:5173/brfv2/**

## Inloggningar

| E-post | Lösenord | Vem är det? |
|---|---|---|
| anna@gjutformen12.se | gjutformen-demo-2026 | Admin — huvudkontot du kör demot med |
| max@demo.se | max-demo-2026 | Har tillgång till två föreningar — visar att man kan byta förening |
| bo@gjutformen12.se | gjutformen-medlem-2026 | Vanlig medlem — visar att medlemmar inte kan ladda upp/ta bort dokument |

## Det du visar (ca 5 minuter)

1. Logga in som Anna. Öppna ett dokument i listan — visa att det är en
   riktig PDF, inte en bild.
2. Gå till "AI-chatt" och fråga: *"Vilka datum gäller för
   snöröjningsjouren?"* Klicka på källhänvisningen i svaret — den öppnar
   rätt PDF och markerar exakt den mening svaret kommer från.
3. Ladda upp filen `DONT_PUSH_brf_stuff/[2026-07-17 13_28_33] Underhallsplan
   30 ar.pdf` (ligger på Simons dator). Fråga sedan: *"Vad är den totala
   utgiften enligt underhållsplanens ekonomiska analys?"* Svaret och
   källhänvisningen ska båda visa samma summa: **15 659 566 kr**.
4. Logga ut, logga in som Max, och byt förening i menyn högst upp. Visa att
   dokumenten byts helt — ingenting från den ena föreningen syns i den andra.
5. Logga in som Bo (eller titta på Max i den förening där han bara är
   medlem) — visa att det inte finns någon "Ladda upp"-knapp eller
   "Ta bort"-knapp för en vanlig medlem.
6. Logga in som Anna igen och ta bort test-dokumentet du laddade upp i steg 3
   (knappen "Ta bort" på dess rad, bekräfta i rutan som dyker upp).

## Om något krånglar

| Vad du ser | Vad du gör |
|---|---|
| Sidan laddar inte alls / "kan inte nå servern" | Kolla att Terminal-fönstret från Steg 1 fortfarande är öppet och tyst. Om det är stängt — öppna ett nytt och gör om Steg 1, sen Steg 2. |
| Du blir utloggad mitt i demot | Logga bara in igen med valfritt konto ovan — inget är trasigt. |
| Terminal-fönstret i Steg 2 säger något om "upptagen"/"occupied" | Något körs redan sedan tidigare — det är oftast okej, testa att gå till adressen i Steg 3 direkt, det kan redan fungera. Fungerar det inte, ring/messa Simon. |
| Dokumentlistan ser konstig ut eller saknar demo-dokument | Det kan lösas, men kräver en kommando till (`make demo-reset`) som **raderar och återskapar all demodata**. Gör det inte på egen hand mitt under en pågående demo — messa Simon istället. |
| Något helt annat/oväntat | Ta en skärmdump om du kan och messa Simon — chansen är stor att det löser sig på en minut. |

## När du är klar

Öppna Terminal och klistra in:

```
cd /Users/coffeedev/Projects/brfv2 && make demo-stop
```

Det stänger av demot snyggt. Terminal-fönstret från Steg 1 kan du bara
stänga helt när du är klar för dagen.
