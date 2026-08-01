# Träff — native Android

The native Android implementation of Träff: question → living index →
grounded answer → exact source passage → **Visa för någon**, plus the
refusal path when the corpus can't answer. Built with Expo Router, React
Native, and Reanimated over the same proven backend contract as the
`xs_mobilapp` PWA — same auth model, same citation verification, same
rect→highlight transform, just a real native surface instead of a browser.

Direction: **3a** ("ett ljus, en hög, sex tillstånd") from the approved
design prototype — deep near-black chrome, cool white-blue search light,
electric-blue actions, green verified states, amber refusal states, white
document pages, yellow passage highlights. See `src/theme/tokens.ts` for the
full token set, transcribed from the prototype.

## Identity

The product was called Källa during the build; the shipped identity is
**Träff** ("Träff · visuell identitet v2", juli 2026), which is the governing
visual source of truth. It ratified the existing palette and type roles
unchanged, so the rename touched the name and the mark, not the meanings.

The mark is ◉, and it carries two meanings that must never blur:

- **Varumärket** (`BrandMark`, `Wordmark`) — always complete, always
  monochrome. Header, login, launcher icon. It says *who is speaking*, so it
  never wears a state colour, not even green.
- **Statusmärket** (`StatusMark`, `StatusChip`) — starts empty and only
  draws its core the instant a passage is verified verbatim. `vila` ·
  `soker` · `belagt` · `ejbelagt`; the middle stays empty in three of the
  four. "En fylld kärna utan citat är en lögn i formspråket."

Status is never carried by the mark alone: every state ships its mono label
(BELAGT, EJ BELAGT, SÖKER) and a spoken form for screen readers, so it
survives both colour blindness and TalkBack. A genuine failure — network,
session, model — is *not* `ejbelagt` and keeps the error treatment, because
it is not a statement about the corpus.

`src/theme/brand.ts` holds the four locked numbers (ring 8 % of the outer
diameter, core 46 % of the inner, 16 dp minimum, mark 52 % of the icon
field). `scripts/make-brand-icons.py` regenerates every launcher, adaptive,
splash and favicon asset from them.

Note that *källa*, *hög*, *belagt* and *sida* remain the app's ordinary
Swedish vocabulary — the identity's §09 explicitly endorses them against
anglicisms. Only the product **name** changed, so "2 KÄLLOR" and "Stäng
källa" are correct and stay.

## Run it

The backend must be running first (from the repo root):

```bash
cd backend && uv run uvicorn app.main:create_app --factory --port 8787
```

Then:

```bash
cd kalla-native
npm install
npx expo start --android   # or --ios / --web (see below)
```

The app has no "same origin" to inherit from a dev server the way the PWA
does — it needs the backend's address. Set it once on the login screen
("Serverinställning"), e.g. `http://<your-LAN-ip>:8787`; it's remembered
locally. Auth is the backend's existing httpOnly `brf_session` cookie —
native `fetch` on Android rides the platform's own persistent cookie jar, so
no bearer token is used or needed (the backend is cookie-only on the wire;
see `src/api/client.ts`).

### Web preview

`expo start --web` works for layout/motion iteration, but a browser enforces
CORS and the backend's `allow_origins` only lists the PWA's dev ports. Point
Metro at the backend instead of the browser doing it directly:

```bash
KALLA_DEV_BACKEND_URL=http://127.0.0.1:8787 npx expo start --web
```

This proxies `/api/*` through Metro's own dev server (`metro.config.js`),
so the web preview and the API share an origin — mirroring
`xs_mobilapp/vite.config.ts`. It's dev-only scaffolding; the shipped Android
app talks to the backend directly and isn't subject to CORS at all.

## Test

```bash
npm run typecheck
npm run lint
npm test
```

## Android build

```bash
npx expo prebuild --platform android   # generates ./android (gitignored)
cd android && ./gradlew assembleDebug
```

Requires JDK 17 and the Android SDK (`platform-36`, `build-tools;36.0.0`).

Three things about `prebuild` that are easy to lose an hour to:

- **It always clears `android/`**, with or without `--clean`. That deletes
  `local.properties`, so recreate it (`sdk.dir=/path/to/android-sdk`) or
  export `ANDROID_HOME` before building.
- **It resets `reactNativeArchitectures` to all four ABIs**, which triples
  the APK. Build the device slice explicitly:
  `./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a`.
- **The toolchain must be a JDK, not a JRE.** If the system Java is a JRE
  (or 25), Gradle picks it, finds no `JAVA_COMPILER`, and fails on the first
  native module. Point at the JDK 17 Gradle provisions for itself:
  `export JAVA_HOME=~/.gradle/jdks/eclipse_adoptium-17-amd64-linux.2`.

`assembleDebug` produces a Metro-backed shell — it embeds **no JS bundle**, so
it only runs with `npx expo start` reachable (`adb reverse tcp:8081 tcp:8081`).
For a self-contained artifact use `./gradlew assembleRelease`, which bundles
`assets/index.android.bundle`.

Accepted on hardware: a Samsung SM-F766B (Galaxy Z Flip7, Android 16 / SDK 36,
arm64-v8a, 1080×2520 @ 480 dpi, 120 Hz) running the **release** APK against
`backend/scripts/e2e_server.py` with `BRF_LLM=scripted`, reached over `adb
reverse tcp:8787 tcp:8787` — real auth, real retrieval, real citation
verification, real page rasterization, real highlight placement; only the
generated text is deterministic. Exercised on the device: both the grounded
and refusal routes, the citation→source transition, Visa mode, system Back at
every layer, sharing, haptics, offline, source-load failure, session expiry,
reduced motion, and a 1.3× font scale.

## Structure

```
src/
  api/          typed client + types mirroring the backend contract
  theme/        design tokens + font loading (direction 3a)
  lib/          rects (the highlight transform), refusals (copy), format
  state/        session, journal + page cache (local storage), the hero
                flight animation, the Svar→Källa→Visa UI-mode stack
  components/   CitationCard, LivingIndex, AnswerCard, KallaSheet,
                VisaOverlay, RefusalScreen, CorpusStack, icons
  app/          Expo Router screens (login, tabs, svar/[localId],
                dokument/[id], konto)
```

## Design decisions worth knowing about

- **No fabricated search progress.** The backend answers in one call — there
  is no real per-document search to stream. The living index shows generic
  pending skeletons during the actual wait and only reveals real document
  names/scores once the answer has actually returned, then stages that
  reveal for a beat before moving on. It never invents an interim hit.
- **Hero transition is native-measured, not ported DOM.** `useHeroFlight`
  measures the tapped citation card and the destination highlight with
  `measureInWindow` and drives one Reanimated timeline (transform + opacity
  only) — not a translation of the prototype's `getBoundingClientRect` code.
- **Källa/Visa are local UI state, not routes.** They're layered views inside
  the Svar screen (`state/uiMode.ts` + `BackHandler`) so the hero
  measurement stays in one native view tree, and Android Back steps down one
  layer at a time (Visa → Källa → Svar) instead of leaving the screen.
- **PIN/biometric lock is out of scope for this pass** (the PWA brief's
  local-lock feature) — the mission's enumerated states didn't call for it
  and it wasn't implemented here.
