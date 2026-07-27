# Demoguide — BRF Dokument-AI

Kort körschema för kanonisk frontend och live Gemma 4 12B. För recovery och
bevisgränser, se [DEMO-RUNBOOK.md](DEMO-RUNBOOK.md).

> **Verifierat i pilotvyn:** login, aktiv förening, roller, tenant-scopade
> dokument, upload/delete, global AI-chatt, verifierade citat och
> citat→PDF-sida→markering.
>
> **Utanför piloten:** global sök, dokumentchatt, kvalitetskontroll,
> bevakningar och inställningar. De är dolda eller spärrade, inte mockade som
> färdiga systemresultat.

Den senaste oförändrade realkorpusgaten är **READY**: q03 besvarades med två
verifierade citat, q11 vägrades säkert och nätverksrevisionen hade 0 externa
anslutningar. En demo ska fortfarande verifiera det aktuella modellutfallet i
stället för att anta att ett tidigare pass garanterar nästa körning.

## Förbered demodata en gång

Detta är destruktivt för de två lokala syntetiska demoföreningarna. Kör det
bara vid ny miljö eller när demodatan avsiktligt ska återställas:

```bash
make demo-stop
make demo-reset
```

## Start — två terminalfönster

### 1. SSH-tunnel

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Lämna fönstret öppet. Det är normalt tyst när tunneln fungerar.

### 2. Hela appen

```bash
make demo
```

Fortsätt först när `Demo igång:` visas. `make demo` kontrollerar att porten
annonserar Gemma 4 12B, startar backend i pilotläge och startar den kanoniska
`brfv2-mockup`-frontenden.

Öppna: **http://127.0.0.1:5173/brfv2/**

## Login

```text
E-post:   max@demo.se
Lösenord: max-demo-2026
```

Max är admin i Brf Gjutformen 12 och medlem i Brf Sjöutsikten 7. Kontot visar
därför både föreningsisolering och rollskillnad utan utloggning.

## Demo — 5–7 minuter

1. Bekräfta att headern visar **Gemma 4 12B** och
   **Self-hosted · agenntserver**. Avbryt om den visar testleverantör, ingen
   modell eller otillgänglig status.
2. I **Brf Gjutformen 12**, öppna **Dokument** och ett seedat dokument. Visa
   att den riktiga PDF:en renderas med sidkontroller.
3. Gå till **AI-chatt** och fråga:

   ```text
   Vilka datum gäller för snöröjningsjouren?
   ```

4. Acceptera bara resultatet om svaret har ett citat. Klicka citatet och
   verifiera rätt dokument, sida och synlig markering. Den senaste syntetiska
   liveevalen klarade denna kedja; modellresultat ska ändå kontrolleras i den
   aktuella körningen.
5. Fråga en uppenbart ostödd fråga, till exempel:

   ```text
   Hur fungerar kvantdatorer?
   ```

   Förväntat säkert beteende är **Otillräckligt underlag** utan citat.
6. Byt till **Brf Sjöutsikten 7**. Dokument, tidigare svar, väntande svar och
   citat från Gjutformen får inte finnas kvar. Upload- och
   raderingskontroller ska saknas eftersom Max är medlem där.
7. Byt tillbaka och visa att adminkontrollerna återkommer.

### Valfri säker uploadkontroll

Använd endast den versionshanterade syntetiska fixturen:

```text
./brfv2-mockup/e2e/fixtures/pilot-upload.pdf
```

Fråga sedan:

```text
Vilken färgkod använder pilotens kontrollprotokoll?
```

Ett godkänt resultat måste citera `pilot-upload.pdf`, sida 1, och visa en
markering. Denna fixturekedja är automatiskt bevisad med den deterministiska
providern; ett avvikande liveutfall ska rapporteras som livebegränsning, inte
maskeras. Radera filen efter demon.

## Stoppa

```bash
make demo-stop
```

Tryck därefter `Ctrl+C` i tunnelfönstret.

## Snabb recovery

```bash
ops/demo.sh check-tunnel   # måste hitta Gemma 4 12B
make demo-status           # visar backend/frontend och ägarskap
```

`make demo-stop` stoppar bara processer som `make demo` själv startade. Det
dödar inte okända processer på port 8787 eller 5173.

## Reservkonton

| Konto | Lösenord | Roll |
|---|---|---|
| `anna@gjutformen12.se` | `gjutformen-demo-2026` | Admin, Gjutformen 12 |
| `bo@gjutformen12.se` | `gjutformen-medlem-2026` | Medlem, Gjutformen 12 |
| `stina@sjoutsikten7.se` | `sjoutsikten-demo-2026` | Admin, Sjöutsikten 7 |
