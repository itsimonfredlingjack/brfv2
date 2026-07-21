# Demo Quickstart

Cheat sheet för att köra demot borta från hemmet (t.ex. café). Fullständig
detalj och recovery-steg: [`DEMO-RUNBOOK.md`](./DEMO-RUNBOOK.md).

## Start — två separata terminalfönster

**Terminalfönster 1** — öppna tunneln, lämna fönstret öppet och orört
(inget mer ska hända i det — tystnad = det funkar):

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

**Terminalfönster 2** — ett nytt fönster (Cmd+N), starta demot:

```bash
cd /Users/coffeedev/Projects/brfv2
```

```bash
make demo
```

Vänta tills du ser grön text `Demo igång:` + en URL + inloggningar. Det
tar upp till en minut.

`agenntserver` går över Tailscale nu, så det funkar på valfritt wifi — inte
bara hemma. Om SSH ber om en extra Tailscale-godkänning i webbläsaren,
klicka länken den skriver ut.

## URL

http://127.0.0.1:5173/brfv2/

## Inloggningar

| Email | Lösenord | Vad den visar |
|---|---|---|
| anna@gjutformen12.se | gjutformen-demo-2026 | admin — huvudkonto för demot |
| max@demo.se | max-demo-2026 | två föreningar — för att visa förenings-byte |
| bo@gjutformen12.se | gjutformen-medlem-2026 | medlem — för att visa att upload/delete saknas |

## Flödet (5 min)

1. Logga in som Anna → öppna ett dokument → fråga *"Vilka datum gäller för snöröjningsjouren?"* → klicka källhänvisningen → markering i PDF:en.
2. Ladda upp `DONT_PUSH_brf_stuff/[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf` → fråga *"Vad är den totala utgiften enligt underhållsplanens ekonomiska analys?"* → svar + källhänvisning ska båda säga **15 659 566 kr**.
3. Byt till Max, växla förening i headern → andra dokument, inget läcker mellan föreningarna.
4. Visa att Bo (eller Max i Sjöutsikten 7) saknar upload/delete-knappar helt.
5. Ta bort test-uppladdningen som admin.

## Om något krånglar

| Symptom | Fix |
|---|---|
| `SSH-tunneln ... saknas` | Tunneln (fönster 1) är inte uppe — kör kommandot i "Terminalfönster 1" igen. |
| Port 8787/5173 upptagen | `make demo-status` för att se vad som kör, sen `make demo-stop` eller undersök manuellt. |
| Utloggad mitt i demot | Logga bara in igen med valfritt konto ovan. |
| Data ser fel ut | `make demo-reset` — **destruktivt**, nollställer och återskapar båda föreningarna. |
| Modellen är onåbar | Kolla att `agenntserver` själv är igång; verifiera med `ops/demo.sh check-tunnel`. |

## Stop

I terminalfönster 2 (eller ett nytt, spelar ingen roll — inte fönster 1 med tunneln):

```bash
make demo-stop
```
