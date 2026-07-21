# Demoguide — BRF Dokument-AI

Kort körschema för demon på Simons Mac. Full recovery och teknisk bakgrund:
[`DEMO-RUNBOOK.md`](./DEMO-RUNBOOK.md).

> **Verkligt i denna demo:** login, föreningsbyte, roller, dokument, PDF,
> upload/delete, global AI-chatt och verifierade källor.
>
> **Visa inte som färdigt:** dokumentchatten och Kvalitetskontroll är mockade.

## Start — två terminalfönster

### Terminalfönster 1 — SSH-tunnel till modellen

Kan köras från valfri mapp. Kopiera hela raden:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Lämna fönstret öppet under demon. Efter eventuell Tailscale-inloggning ska
fönstret normalt vara tyst — **tystnad betyder att tunneln är öppen**.

### Terminalfönster 2 — starta appen

Öppna ett nytt fönster med **Cmd + N**. Kopiera hela raden:

```bash
cd /Users/coffeedev/Projects/brfv2 && make demo
```

Fortsätt när du ser:

```text
Demo igång:
```

Gul text om att en frisk process återanvänds är okej. Rött `FEL:` måste lösas
innan demon fortsätter.

### Webbläsaren

Öppna denna adress i Chrome/Safari — inte i Terminal:

**http://127.0.0.1:5173/brfv2/**

## Login — använd Max genom hela demon

```text
E-post:   max@demo.se
Lösenord: max-demo-2026
```

Max är **admin i Brf Gjutformen 12** och **medlem i Brf Sjöutsikten 7**. Samma
konto visar därför både föreningsisolering och olika behörigheter utan utloggning.

## Demo — 5–7 minuter

### 1. Riktigt dokument

- Börja i **Brf Gjutformen 12**.
- Öppna **Dokument** → **Snöröjningsavtal 2026.pdf**.
- Visa att det är en riktig PDF med sidor och text, inte en förberedd bild.

### 2. Grundat svar med verifierbar källa

Gå till **AI-chatt** och fråga:

```text
Vilka datum gäller för snöröjningsjouren?
```

- Förväntat svar: **15 november–15 april**.
- Klicka på källhänvisningen.
- Visa att rätt PDF öppnas och att den citerade passagen markeras.

**Budskap:** svaret går att kontrollera direkt i originalhandlingen.

### 3. Nytt dokument in → nytt verifierbart svar ut

Gå till **Dokument** → **Ladda upp dokument**.

I Macens filväljare:

1. Tryck **Cmd + Shift + G**.
2. Klistra in hela sökvägen:

```text
/Users/coffeedev/Projects/brfv2/DONT_PUSH_brf_stuff/[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf
```

3. Tryck Enter och välj filen.
4. Vänta tills uppladdningen är klar.

Gå till **AI-chatt** och fråga:

```text
Vad är den totala utgiften enligt underhållsplanens ekonomiska analys?
```

- Svar och källa ska båda visa **15 659 566 kr**.
- Klicka källan: förväntad träff är på **sida 33** i den uppladdade PDF:en.

**Budskap:** systemet kan ta in ett nytt dokument; svaret är inte hårdkodat.

### 4. Föreningsisolering och roller

- Byt förening längst ned i sidofältet till **Brf Sjöutsikten 7**.
- Visa att dokumenten byts helt.
- Visa att **Ladda upp dokument** och raderingskontroller saknas eftersom Max
  bara är medlem där.
- Byt tillbaka till **Brf Gjutformen 12** och visa att adminkontrollerna återkommer.

**Budskap:** både data och rättigheter följer den aktiva föreningen.

### 5. Städa

I **Brf Gjutformen 12**, ta bort den uppladdade filen
`[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf`.

## Stoppa

### Terminalfönster 2

```bash
cd /Users/coffeedev/Projects/brfv2 && make demo-stop
```

### Terminalfönster 1

Tryck **Ctrl + C** för att stänga SSH-tunneln.

## Snabb recovery

### Tunneln saknas eller modellen går inte att nå

Kör tunnelkommandot i Terminalfönster 1 igen. Kontrollera därefter från
Terminalfönster 2:

```bash
cd /Users/coffeedev/Projects/brfv2 && ops/demo.sh check-tunnel
```

Kontrollen ska hitta **Gemma 4 12B**. Appen faller inte tillbaka till Macens
lokala modell.

### Sidan laddar inte eller en port är upptagen

```bash
cd /Users/coffeedev/Projects/brfv2 && make demo-status
```

- Om backend/frontend är stoppad: kör `make demo` igen.
- En frisk befintlig process återanvänds automatiskt.
- Vid rött `FEL: Port ... upptagen av en okänd process`: stäng den gamla
  utvecklingsprocessen. `make demo-stop` dödar aldrig okända processer.

### Demodatan är fel eller testfilen ligger kvar

Kör endast mellan demonstrationer — detta raderar och seedar om båda
föreningarna:

```bash
cd /Users/coffeedev/Projects/brfv2
make demo-stop
make demo-reset
make demo
```

SSH-tunneln i Terminalfönster 1 ska fortfarande vara öppen.

### Utloggad

Logga bara in igen med Max-kontot.

## Reservkonton

| Konto | Lösenord | Roll |
|---|---|---|
| `anna@gjutformen12.se` | `gjutformen-demo-2026` | Admin, Gjutformen 12 |
| `bo@gjutformen12.se` | `gjutformen-medlem-2026` | Medlem, Gjutformen 12 |
| `stina@sjoutsikten7.se` | `sjoutsikten-demo-2026` | Admin, Sjöutsikten 7 |
