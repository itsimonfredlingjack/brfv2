# XS-46 — Tauri 2 på Fedora/KDE/Wayland

Datum: 2026-07-28

## Verdict

**ACCEPT WITH CONDITIONS.** Spiken bevisar att den kanoniska BRF-klienten kan
köras i en minimal Tauri 2/WebKitGTK-wrapper på den faktiska
Fedora/KDE/Wayland-miljön, med samma slumpmässiga loopback-origin för UI och
FastAPI. Rekommendationen är att gå vidare med Tauri 2-arkitekturen i en separat,
avgränsad nästa etapp.

Villkoren är:

- detta är ett källkods-/releasebinärbevis, inte ett distributionsbevis;
- PyInstaller, RPM, AppImage, updater och multi-user-synk är uttryckligen inte
  verifierade eller implementerade;
- WebKitWebDriver kan inte injicera W3C `element/value` eller `element/click`
  i WRY, och KWin-sessionen kunde inte automatiseras med ett fysiskt
  tangentbord. Applikationens verkliga `keydown Enter`-väg är verifierad inne i
  WebKit, men en mänsklig tangentbordssmoke bör upprepas i nästa manuella
  releasecheck.

## Miljö

| Del | Verifierad version |
| --- | --- |
| OS | Fedora 44 (Forty Four), kernel `7.1.5-200.fc44.x86_64` |
| Session | `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE`, `wayland-0` |
| KDE | Plasma/KWin `6.7.3` |
| Rust | `rustc 1.97.1`, `cargo 1.97.1` |
| Tauri | `tauri = 2.11.5`, `tauri-build = 2.6.3`, exakt låsta |
| Appens webview | `webkit2gtk4.1 2.52.5`, GTK 3 `3.24.52` |
| WebDriver | `tauri-driver 2.0.6`, `/usr/bin/WebKitWebDriver` från `webkitgtk6.0 2.52.5` |

`webkitgtk6.0`, `javascriptcoregtk6.0` och `tauri-driver` installerades lokalt
för den externa WebDriver-acceptansen. Appen själv länkar mot
`webkit2gtk4.1 2.52.5`.

## Arkitektur som faktiskt kördes

1. Tauri startar
   `backend/.venv/bin/python -m app.desktop` som ett ägt barn i en egen
   processgrupp.
2. Python binder först en OS-vald port på exakt `127.0.0.1:0`.
3. FastAPI monterar det byggda kanoniska UI:t på `/brfv2` och behåller
   produkt-API:t under `/api` i samma app.
4. Uvicorn skriver ett JSON-kontrakt först efter lyckad startup:

   ```json
   {
     "schema": "brfv2-desktop-startup/v1",
     "status": "ready",
     "host": "127.0.0.1",
     "port": 33401,
     "origin": "http://127.0.0.1:33401"
   }
   ```

5. Rust validerar schema, status, host, port och origin innan webview-fönstret
   skapas.
6. Fönstret tillåter bara navigation till exakt den validerade origin och
   nekar nya fönster.
7. Normal exit skickar `SIGTERM` till hela backendgruppen och använder
   `SIGKILL` endast efter tre sekunders grace. Linux `PR_SET_PDEATHSIG`
   stänger även backenden om Tauri dödas abrupt.

Appdata ligger i Tauri-katalogen
`~/.local/share/se.brfdokumentai.desktop.spike/data`, som sätts till mode
`0700`. Spiken skriver inte i `backend/data`.

## Säkerhetsgräns och cookiehotmodell

### HTTP och CSP

Varje svar, inklusive fel, får följande policy:

```text
default-src 'none'; base-uri 'self'; connect-src 'self'; font-src 'self';
form-action 'self'; frame-ancestors 'none'; img-src 'self' data: blob:;
manifest-src 'self'; media-src 'self' blob:; object-src 'none';
script-src 'self'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:
```

Skript får alltså bara laddas från samma origin; `eval`, inline-skript, objekt,
frames och externa anslutningar är stängda. Inline-style behålls eftersom det
kanoniska React-UI:t använder inline-style. `Host` måste vara exakt den valda
IP/port-kombinationen och en skickad `Origin` måste vara exakt samma origin.
Tester nekar annan port, `localhost` i stället för `127.0.0.1` och frontendens
utvecklingsorigin.

### Tauri IPC och remote origin

Fönstret använder en extern HTTP-URL, men `capabilities` är tom,
`withGlobalTauri` är `false`, inga plugins är installerade och ingen
`remote.urls`-regel finns. `window.__TAURI_INTERNALS__` finns som en intern
transportdetalj i WRY, men det aktiva försöket
`plugin:window|set_title` nekades med:

```text
Command plugin:window|set_title not allowed by ACL
```

Detta är det direkta beviset för remote-origin-gränsen; frånvaro av
`window.__TAURI__` används inte ensam som säkerhetsbevis.

### Cookie

Desktopcookien är:

- `HttpOnly`;
- `SameSite=Lax`;
- begränsad till `Path=/api/`;
- namngiven `brf_desktop_<24 hex>` med ett stabilt, installationsspecifikt id;
- skild från webbutvecklingens ordinarie cookie.

`Secure` används inte eftersom spiken medvetet kör HTTP på en slumpmässig
loopback-port. Trafiken lämnar aldrig hosten, men detta är inte ett
transportskydd mot en redan privilegierad lokal angripare.

Viktig begränsning: cookies är host-, inte portscopade. `SameSite` isolerar
inte två portar på samma `127.0.0.1`. Det installationsspecifika namnet minskar
oavsiktliga kollisioner men är inte en hemlighet. Den egentliga kontrollen är
kombinationen av exakt Host/Origin, `connect-src 'self'`, exakt
webview-navigation och API-sökvägen. En annan lokal tjänst får därför inte
desktopcookien via appens normala navigation eller fetch.

OS-användaren är spikens lokala tillitsgräns. En process som redan kör som
samma Unix-användare kan läsa eller manipulera användarens appdata och ligger
utanför detta bevis. Multi-user-synk och en starkare lokal processisolering
tillhör inte XS-46.

## Claim matrix

| Claim | Kontroll | Evidens | Status |
| --- | --- | --- | --- |
| Tauri 2 kör på faktisk Fedora/KDE/Wayland | Native releasefönster + WebKitWebDriver | Miljön ovan; tre visuellt granskade screenshots | PASS |
| UI och API delar origin | Login och `/api/auth/me` från webview, readinessjämförelse | `http://127.0.0.1:33401` för båda | PASS |
| Slumpport och maskinläsbar readiness | Rust blockerar webview tills JSON validerats | Schema v1 och port `33401`; tidigare körningar använde andra portar | PASS |
| Login fungerar | UI-login med `max@demo.se`, därefter `/api/auth/me` | Autentiserad användare `max@demo.se` | PASS |
| BRF-byte fungerar och läcker inte state | Gjutformen → Sjöutsikten → Gjutformen | Selectvärde och laddad tenantstate kontrollerade | PASS |
| Underbyggt svar och citation | Fråga om styrelsens säte | Exakt svar och `Stadgar Brf Gjutformen 12.pdf s.1` | PASS |
| PDF och highlight fungerar | Citation öppnas i WebKit | `Sida 1 av 3`, synlig rect `101.14 × 13.73` | PASS |
| Säker vägran | Källfrämmande fråga om planetarium | Refusal-rubrik och noll citationer | PASS |
| Resize, scroll, scaling, zoom | Fönster `1000×700`, DPR och DOM-layout | Ingen horisontell overflow, DPR 1, PDF 100→110 % | PASS |
| Tangentbordsväg | `keydown Enter` i riktiga WebKit-vyn | Frågan submitteras och svaras | PASS |
| Fysisk tangentautomation | W3C, KWin virtual keyboard och tillfällig uinput provades | Nådde inte WebKit-automationstoplevel | BLOCKED |
| CSP och exakt HTTP-origin | Backendtester + live headers | Restriktiv CSP och 403 för fel host/origin | PASS |
| Remote Tauri IPC är stängt | Aktivt `set_title`-invoke från HTTP-sidan | `not allowed by ACL` | PASS |
| Cookiegräns | Backendtest + live `Set-Cookie` | HttpOnly, Lax, `/api/`, installationsnamn | PASS |
| Normal processstopp | Native KDE window-close och WebDriver DELETE session | Port stängd; ingen Tauri/Python kvar | PASS |
| Abrupt processstopp | Avbruten driver efter `PDEATHSIG`-fix | Ingen `app.desktop`, driver eller listener kvar | PASS |
| Befintlig backend är fortsatt grön | Full pytest | `544 passed, 3 skipped` | PASS |
| Kanoniskt UI är fortsatt grönt | oxlint, Vitest, Vite, Playwright | 0 lintfel, 14/14, build, 11/11 | PASS |
| Scope är avgränsat | Manifest- och källgranskning | Bundle av, inga paketerare/updater/synkmotorer | PASS |

## Visuell evidens

- [Native login i Tauri/WebKitGTK](xs46-tauri-login.png)
- [PDF sida 1 med exakt citation-highlight](xs46-tauri-answer-highlight.png)
- [Säkert avslag utan citationer](xs46-tauri-refusal.png)

## Reproducerbara kontroller

```bash
make desktop-build
make desktop-check
make desktop-acceptance

backend/.venv/bin/pytest -q backend/tests
cd brfv2-mockup
npm run lint
npm test
npm run build
npm run test:e2e
```

Senast verifierade resultat:

- Rust: 2/2 tester;
- desktopadapter: 5/5 tester;
- backend: 544 passed, 3 skipped;
- frontend: 14/14 komponenttester, lint utan fel, Vite releasebuild;
- webbe2e: 11/11;
- native Tauri/WebKitGTK-acceptans: PASS, port stängd efteråt;
- `git diff --check`: PASS.

Backendens enda varning är den redan befintliga Starlette-deprecationen om
`httpx`/`httpx2`. Vite varnar fortsatt för en JavaScript-chunk över 500 kB.
Ingendera introducerades av desktopspiken.

## Findings och unverified areas

1. Under felvägsprov upptäcktes att hård driverdöd kunde lämna FastAPI kvar.
   Det korrigerades med Linux `PR_SET_PDEATHSIG`; både normal och abrupt cleanup
   verifierades därefter.
2. WebKitWebDriver för WRY saknar element-click/value. Acceptansen använder
   WebKits DOM för text/klick och testar den riktiga Enter-handlern. Native
   scan-code-automation är fortfarande blockerad enligt matrisen.
3. WebKitGTK:s user agent innehåller kompatibilitetstoken `X11` även när den
   faktiska sessionen är Wayland; sessionstypen verifierades separat från
   operativsystemet.
4. Det kanoniska HTML-dokumentet refererar Google Fonts. CSP blockerar den
   externa stilen och UI:t använder lokal fallback-font. Ingen extern fontorigin
   öppnades för att få tystare konsollogg.
5. Detta bevis omfattar inte installation på en ren andra maskin, signering,
   paketformat, automatiska uppdateringar eller multi-user-synk.

## Required next action

Stäng XS-46 som ett lyckat arkitekturbevis och skapa separata, explicita issues
för paketering/installationsprov och eventuell produktionshärdning. Lägg inte
PyInstaller, RPM, AppImage, updater eller multi-user-synk i denna spike.
