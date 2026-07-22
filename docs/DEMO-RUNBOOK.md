# Demo Runbook — BRF Dokument-AI (pilot, Gemma 4 12B)

Operator guide for running the local desktop demo end to end: start, demonstrate,
stop, restart — without manual debugging. Scope: login, active-BRF switching,
real tenant-scoped documents, PDF upload/delete, real PDF rendering, global
AI chat on self-hosted Gemma 4 12B, verified citations, citation→PDF
navigation/highlight, numeric grounding. Document-bound chat and
Kvalitetskontroll are still mocked in this build — not part of the demo.

## Startup

### 1. Start (or verify) the SSH tunnel to agenntserver

The pilot's only generation service is Gemma 4 12B on `agenntserver`
(Ubuntu, RTX 4070), exposed on its port 8000. From the Mac, forward it:

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
```

Leave that running in its own terminal. `make demo` checks this itself and
refuses to start the backend if it isn't reachable — see Recovery below.

### 2. Start the complete demo

```bash
cd /Users/coffeedev/Projects/brfv2
make demo
```

This:
- verifies port 8000 answers as an OpenAI-compatible endpoint serving a
  Gemma 4 12B model (fails loudly, with the exact `ssh -N -L ...` command, if not);
- never falls back to the Mac's local Ollama/`gemma4:e4b` — there is no
  fallback path in the pilot LLM provider;
- starts the backend in pilot mode on **:8787** with `BRF_MODE=pilot`,
  `BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1`, `BRF_LLM_MODEL=gemma4:e12b`,
  and waits for `/api/health` to report `mode: pilot`, `llm_provider: selfhosted`;
- starts the canonical frontend (`brfv2-mockup`) on **:5173**;
- if either port already hosts a healthy instance it didn't start (e.g. left
  running from a previous session), it **adopts** that instance instead of
  killing or duplicating it, and says so;
- prints the URL, demo credentials, and log file paths.

Logs persist at `.demo/backend.log` and `.demo/frontend.log` (gitignored)
for the life of the demo process.

### URL

http://127.0.0.1:5173/brfv2/

### Demo credentials

| Email | Password | Role |
|---|---|---|
| anna@gjutformen12.se | gjutformen-demo-2026 | admin, Brf Gjutformen 12 |
| bo@gjutformen12.se | gjutformen-medlem-2026 | member, Brf Gjutformen 12 — no upload/delete |
| stina@sjoutsikten7.se | sjoutsikten-demo-2026 | admin, Brf Sjöutsikten 7 |
| max@demo.se | max-demo-2026 | two memberships — shows the BRF switcher |

### Confirm the backend is on self-hosted Gemma 4 12B

```bash
curl -s http://127.0.0.1:8787/api/health | jq .
```

Expect:

```json
{"status":"ok","mode":"pilot","llm_provider":"selfhosted", ...}
```

`llm_provider` must read `selfhosted`, never `fake`, `none`, or `api`. Ask any
grounded question in the UI and open its citation chip — the cited quote must
verbatim-match highlighted text in the PDF viewer.

## Five-minute demo flow

1. **Login as Anna** — anna@gjutformen12.se / gjutformen-demo-2026.
2. **Show the tenant identity** — sidebar shows "Brf Gjutformen 12" and
   Anna Andersson; Anna has one membership, so no BRF switcher shows for her
   (that's expected — switch to Max later to show it).
3. **Open an existing document** — click any row in Dokument, e.g.
   *Snöröjningsavtal 2026.pdf*. Confirm it renders as a real PDF with page
   controls (not a placeholder).
4. **Ask a grounded question** — go to AI-chatt, use the suggestion chip
   *"Vilka datum gäller för snöröjningsjouren?"* (or type it). Answer:
   *"Jourperioden löper från den 15 november till den 15 april."*
5. **Click the citation** and show the PDF opens to the right page with the
   exact quoted passage highlighted.
6. **Upload the BRF Eken maintenance plan** — Ladda upp dokument →
   `DONT_PUSH_brf_stuff/[2026-07-17 13_28_33] Underhallsplan 30 ar.pdf`
   (not committed to the repo; keep it local).
7. **Ask**: `Vad är den totala utgiften enligt underhållsplanens ekonomiska analys?`
8. **Show the exact figure and citation** — answer and citation both read
   *15 659 566 kr*, citation points at the newly uploaded document, page 33.
9. **Switch tenant** — since step 1 logged in as Anna, who has only one
   membership, **log out first** (user menu → Logga ut), then log back in as
   max@demo.se. The sidebar now shows an "Aktiv förening" panel with a real
   dropdown (Anna's showed a static, non-interactive display — that's
   correct for a one-membership account, not a broken switcher). Flip
   between Brf Gjutformen 12 and Brf Sjöutsikten 7. Document counts and
   AI-chatt answers change with the switch; nothing from one tenant is
   visible in the other. The browser session persists for 14 days — if a
   later run of this demo looks "stuck" on one förening with no switcher,
   check the sidebar footer for which account is actually logged in before
   assuming the control is broken.
10. **Show a member can't upload or delete** — while on a tenant where the
    logged-in user is `member` (e.g. Max on Sjöutsikten 7, or Bo on
    Gjutformen 12), the Dokument page has no "Ladda upp dokument" button and
    no "Åtgärder" column at all.
11. **Delete the uploaded test document** (as an admin on Gjutformen 12) —
    click "Ta bort" on its row, confirm in the dialog. It disappears from the
    list immediately and is no longer citable by the AI chat.

## Recovery

**Missing SSH tunnel** — `make demo` prints:
```
SSH-tunneln till agenntserver saknas eller port 8000 svarar inte.
```
Start it: `ssh -N -L 8000:127.0.0.1:8000 agenntserver`, then re-run `make demo`.

**Port 8787 already occupied** — if it's a healthy pilot/selfhosted backend,
`make demo` adopts it automatically and tells you so. If it's occupied by
something else, it fails loudly rather than killing an unknown process; run
`make demo-status` to see what's actually listening, then either
`make demo-stop` (only touches processes `make demo` itself started) or
investigate/stop the foreign process manually.

**Port 5173 already occupied** — same pattern as above, for the frontend.

**Expired login session** — the app redirects to the login screen; log back
in with any demo account above.

**Broken or unwanted demo data** — reset it:
```bash
make demo-reset
```
This is destructive: it wipes and reseeds both demo tenants, their documents,
and the golden eval sets. It never runs automatically as part of `make demo`.

**Remote model endpoint unavailable** — `make demo` fails at the tunnel/model
check before starting anything. Verify the model service on `agenntserver`
itself is up, then re-check with:
```bash
ops/demo.sh check-tunnel
```

## Other commands

```bash
make demo-status   # is the backend/frontend running, and did make demo start it?
make demo-stop     # stop only what make demo started — never touches unrelated processes
make demo-reset    # DESTRUCTIVE — wipe + reseed both demo tenants
```
