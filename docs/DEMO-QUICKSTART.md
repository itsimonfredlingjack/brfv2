# Demo Quickstart

Cheat sheet for running the demo away from home (e.g. a café). Full detail
and recovery steps: [`DEMO-RUNBOOK.md`](./DEMO-RUNBOOK.md).

## Start (2 commands)

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver   # leave running in its own terminal
make demo                                     # from /Users/coffeedev/Projects/brfv2
```

`agenntserver` resolves over Tailscale now, so this works on any wifi — not
just home. If SSH ever asks for an extra Tailscale browser check-in, click
the link it prints.

## URL

http://127.0.0.1:5173/brfv2/

## Logins

| Email | Password | Note |
|---|---|---|
| anna@gjutformen12.se | gjutformen-demo-2026 | admin — main demo account |
| max@demo.se | max-demo-2026 | two BRFs — use to show tenant switching |
| bo@gjutformen12.se | gjutformen-medlem-2026 | member — use to show no upload/delete |

## The flow (5 min)

1. Login as Anna → open a document → ask *"Vilka datum gäller för snöröjningsjouren?"* → click citation → highlight in PDF.
2. Upload `DONT_PUSH_brf_stuff/[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf` → ask *"Vad är den totala utgiften enligt underhållsplanens ekonomiska analys?"* → answer + citation both say **15 659 566 kr**.
3. Switch to Max, flip BRF in the header → different docs, no bleed-through.
4. Show Bo (or Max on Sjöutsikten 7) has no upload/delete controls.
5. Delete the test upload as admin.

## If something's wrong

| Symptom | Fix |
|---|---|
| `SSH-tunneln ... saknas` | Tunnel not up — run the `ssh -N -L ...` command above. |
| Port 8787/5173 busy | `make demo-status` to see what's using it, then `make demo-stop` or investigate manually. |
| Logged out mid-demo | Just log back in with any account above. |
| Data looks wrong | `make demo-reset` — **destructive**, wipes and reseeds both BRFs. |
| Model unreachable | Check `agenntserver` itself is up; re-verify with `ops/demo.sh check-tunnel`. |

## Stop

```bash
make demo-stop
```
