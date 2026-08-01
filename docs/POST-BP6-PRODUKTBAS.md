# Post-BP6-produktbas — en linje, två bevarade kontrakt

Det här dokumentet svarar på tre frågor som annars bara finns i git-historiken:
vilken commit fortsatt produktutveckling utgår från, varför desktop- och
mobilspåret inte slogs ihop med en merge, och exakt vad som fördes fram
respektive lämnades kvar.

## Repositorytopologi

| Linje | Ref | Roll |
| -- | -- | -- |
| Fedora-pilotens frysta släpplinje | `bp6/fedora-pilot-closeout`, taggen `v0.2.0-fedora-pilot` | Avslutad, kallgranskad pilot. Historisk evidens. Ingen fortsatt utveckling. |
| Publicerad produktbas | `feat/kalla-mobile-pwa` = `3bc78bdaaf8c252864ea31684272e10b5eb27693`, taggen `traff-mobile-rc1` | Cookie-only-auth, page-image-route, `/m`-servering, Träff Mobile RC1. |
| Fortsatt desktopprodukt | `feat/desktop-styrelsearbetsyta` | Den här grenen. Produktbasen + desktopens produktförmågor. |
| `main` | `acd39de0ce7e46e94786ba3aafa33fb22ee20ad7` | Orörd av desktoparbetet. |

Pilotgrenen och produktbasen delar bascommit `1cd65cae755b72f753b1d36ab4a1d5314fe2ea79`
men divergerar därifrån. De slås aldrig ihop: BP6 är ett dokument-only avslut på
sin egen linje, och den här grenen tar över produktansvaret.

## Varför inte en merge

Sex filer överlappar mellan linjerna, och tre av dem är centrala:
`backend/app/auth.py`, `backend/app/main.py` och `backend/tests/test_api.py`.
En merge hade producerat ett resultat där båda sidors *text* överlever men
ingen har prövat om båda sidors *garantier* fortfarande gäller. Två av dem är
direkt motstridiga i intention:

* pilotlinjen läser sessionen från `Authorization: Bearer` **eller** cookie, och
  `/api/desktop/setup` returnerade sessionstoken i JSON-svaret;
* produktbasen har tagit bort båda medvetet — login delar inte ut någon token,
  och ingen header accepteras.

En textuell merge behåller den svagare varianten utan att någonstans säga att
den gör det. Porteringen gjordes därför fil för fil, med varje överlapp
handavgjord.

## Vad som fördes fram från desktoplinjen

Produktförmågor, inte pilotens historiska evidens.

**Tauri-skalet och körmiljön**
`src-tauri/` (skal, ikoner, `Cargo.lock`, `tauri.conf.json`), som äger fönstret
och sidecarens livscykel men ingen produktlogik.

**Desktopadaptern** `backend/app/desktop.py`
Slumpad loopback-port, exakt Host/Origin-kontroll, säkerhetsheaders,
installationsspecifik `/api/`-scopad sessionscookie, first-run-provisionering,
modellruntimekonfiguration, backup/restore/restart, readiness-kontrakt.

**Modellgränsen** `backend/app/model_endpoint.py`
Default-deny-policy för vilka adresser modelltjänsten får peka på (loopback,
eller privat nät över https), maskinläsbar och delad mellan runtime, UI och
tester.

**Leverantörsgränsen** `backend/app/llm.py` + `backend/app/llm_hosted.py`
Tredjepartsleverantörer flyttade till en valfri plug-in-modul. Paketeringen
utelämnar modulen, så uteslutningen är strukturell och inte en flagga.

**Installationsadministratör** `backend/app/auth.py`
Tabellen `installation_admins`, `grant/revoke/is/list` och
`backfill_installation_admin()` — auktoritet över installationen, skild från
adminrollen inne i en förening.

**Bäddad embedder** `backend/app/embeddings.py`
`BRF_MODEL2VEC_PATH` och `configured_provider_name()`, så vikterna laddas ur
bundlen och tillståndsrutten inte behöver konstruera embeddern.

**Paketering** `ops/build-runtime.sh`, `ops/package-desktop.sh`, `ops/pins.json`,
`ops/fetch_pinned.py`, `ops/prune_payload.py`, `ops/inspect_payload.py`,
`ops/forbidden_providers.json`, `ops/verify-reproducible.sh`, `ops/lib/repro.sh`,
`ops/brf-dokument-ai.spec`.

**Desktop-UI** `brfv2-mockup/src/components/Setup.jsx`,
`brfv2-mockup/src/components/DesktopSettings.jsx` med CSS, samt `App.jsx`,
`api.js`, `index.html` och `modelDisplay.js`.

**Tester** `test_desktop.py`, `test_model_endpoint.py`, `test_desktop_artifact.py`,
`test_desktop_acceptance_evidence.py`, utökad `test_llm.py`.

**Dokumentation** `docs/DESKTOP-FEDORA.md` och `docs/adr/0001–0003`.

## Vad som medvetet inte fördes fram

* `docs/pilot/**` och `docs/evidence/pilot/**`, `docs/evidence/xs4*`, `xs5*` —
  pilotens historiska evidens hör till den frysta linjen. Att kopiera den hit
  hade gjort evidens om en annan artefakt till evidens om den här grenen.
* `backend/tests/test_desktop_acceptance_evidence.py` fördes fram, men de två
  fall som pekade på `docs/evidence/xs49-*` är omankrade till en fil som den här
  grenen faktiskt spårar. Regeln som testas — ett mål git redan bär stoppar
  körningen — är oförändrad.

## Vad som bevarades från produktbasen

Ingenting i porteringen försvagar dessa:

* **Cookie-only-session.** `_token_from()` läser bara cookien. Desktopadapterns
  egen `current_user()` gjorde det inte — den hade kvar en Bearer-gren från när
  login delade ut token. Den är borttagen.
* **Inget sessionstoken i JSON.** `/api/auth/login` returnerar `{user, memberships}`.
  `/api/desktop/setup` gjorde det inte — den returnerade `token`. Det fältet är
  borttaget. Provisioneringen är den enda plats i produkten som loggar in ett
  konto utan lösenordsprompt, alltså exakt det svar som inte får bära en
  långlivad credential.
* **Ingen Authorization/Bearer-väg**, varken på produktrutterna eller på
  desktoprutterna.
* **`/api/brf/{brf_id}/documents/{doc_id}/page/{page}`** med sluten breddallowlist
  och `Cache-Control: private, no-store`.
* **`/m` och mobilens same-origin-policy** med CSP-headers.
* **Tenantisolering** och samtliga dokument- och citatkontrakt.

Den installationsspecifika cookieidentiteten löstes utan att återinföra något
av det: `create_app()` tar `session_cookie_name` och `session_cookie_path` som
parametrar, och desktopadaptern skickar in sitt eget namn (`brf_desktop_<24 hex>`,
persistent i datakatalogen) och `/api/`. Namnet är inte en hemlighet och
transporten är oförändrad.

## Regressionsgrind

Fyra tester i `backend/tests/test_desktop.py` låser den reconciliation som
gjordes här, så att den inte kan tas tillbaka av misstag:

* `test_setup_does_not_echo_the_session_token`
* `test_a_real_session_token_is_refused_as_a_bearer_header` — samma giltiga token
  accepteras i cookien och avvisas som header, vilket är skillnaden mellan
  "Bearer accepteras inte" och "den token var ändå ogiltig"
* `test_login_through_the_desktop_boundary_is_cookie_only`
* `test_the_installation_cookie_name_is_per_install_and_stable`
