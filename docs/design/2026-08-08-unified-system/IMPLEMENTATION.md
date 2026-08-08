# Implementationsplan — varaktig enhetlighet på kodnivå

Underlag för att föra mockup-systemet (`src/system.css` i denna mapp) in i
`brfv2-mockup`. Uppmätt mot koden 2026-08-08, inte gissat.

## Nuläge (fakta)

| System | Kanoniskt | Legacy | Användning |
| --- | --- | --- | --- |
| Knappar | `.ui-btn*` i `theme.css` (25 regler) | `.primary-action-btn` / `.secondary-action-btn` i `App.css` (16 regler) | Legacy: **6 JSX-platser, alla i `App.jsx`**. Kanoniskt: 3 platser i `IntakeQueue.jsx` |
| Breakpoints | — | 18 `@media` i 11 filer med **elva olika värden**: 390, 560, 640, 720, 768, 860, 900, 1024, 1100, 1180, 1200 | App.css 1200/1024/768/390; domän: 1180, 1100×2, 900×2, 860, 720×5, 640, 560×2 |
| Fokusring | `:focus-visible` globalt + `.ui-btn`/`.ui-input`/`.ui-tabs` i `theme.css` — redan 2px `var(--ring)` | Saknas på listrader | — |
| Typsnitt | `--font-sans` / `--font-serif` / `--font-mono` i `theme.css` | — | Serif = display idag |

## Beslut 1 — Ett knappsystem: `.ui-btn`

**Beslut:** `.ui-btn` i `theme.css` är den enda knapprimitiven. Legacy-klasserna
dör; de depreceras inte och lämnas inte kvar "för säkerhets skull".

Konsoliderad spec (matchar mockupen):

| Egenskap | Värde |
| --- | --- |
| Höjd | 36px (default), 30px (`--sm`) |
| Radie | 10px (`--r-control`) — inte 18px-kapsel |
| Ikon | 15px Lucide, stroke 2, gap 8px |
| Varianter | `--primary` (ink), `--outline`, `--ghost`, `--destructive`, `--warning` |
| Fokus | 2px `var(--ring)`, offset 2px — identisk för alla varianter |

**Migration (en atomär commit):**

1. Komplettera `.ui-btn` i `theme.css` med saknade varianter och 36px-höjd.
2. Ersätt de 6 användningarna i `App.jsx` (sänd-knapp, chat/docs-åtgärder).
3. Radera `.primary-action-btn`/`.secondary-action-btn`-blocken i `App.css`
   i samma commit — aldrig ett mellanläge där båda lever.
4. Test: inga testfiler refererar legacy-klasserna (verifierat via sökning).

**Varaktig garanti:** rules-lock-test som feilar på strängarna
`primary-action-btn` / `secondary-action-btn` under `src/` — samma mönster
som repots befintliga vocabulary/rules-locks (`Makefile`).

## Beslut 2 — Fyra breakpoints, låsta

**Beslut:** elva värden → fyra tokens. Inga nya byggberoenden: literaler med
låstest i stället för PostCSS-plugin (passar repots lock-kultur, noll risk
för byggkedjan).

| Token | Värde | Tar över från | Användning |
| --- | --- | --- | --- |
| `--bp-wide` | 1200px | 1200, 1180, 1100×2 | split-pane → kolumn, sidospår staplas |
| `--bp-mid` | 1024px | 1024, 900×2, 860 | sidomeny fälls, grid 4→2 kolumner |
| `--bp-narrow` | 768px | 768, 720×5, 640 | enkolumnslistor, verktygsrader bryts |
| `--bp-compact` | 560px | 560×2, 390 | minsta skal: kortrutnät 1 kolumn |

**Migration:** värde för värde, fil för fil; varje byte visuellt verifierat
vid båda sidor av tröskeln (t.ex. 1180→1200 kontrolleras vid 1190 och 1210).
`@media (min-width: 900px)` i IntakeQueue.css blir `min-width: 1024px` —
enda min-width-fallet, granskas separat.

**Varaktig garanti:** lock-test som skannar `src/**/*.css` och feilar på
`@media`-bredder utanför {1200, 1024, 768, 560}. Nya undantag kräver
medveten ändring av testet — det är priset för att lägga till ett breakpoint.

*(Alternativ om teamet föredrar deklarativ syntax: `postcss-custom-media`
och `@media (--bp-mid)`. Mer läsbart, men ett nytt dev-beroende — rekommenderas
först om lock-testet visar sig för skört.)*

## Beslut 3 — Typografi och kontrollmått i `theme.css`

1. Vendor:a Poppins 500/600 + Inter 400/500/600 till `src/assets/fonts/`
   (OFL, `font-src 'self'` oförändrad; licensnot finns i denna mapps `fonts/`).
2. `--font-display: 'Poppins'` (ny), `--font-sans: 'Inter'` (ompekad).
   `--font-serif` pekas om till sans — Instrument Serif-filerna tas bort när
   ingen selektor längre refererar dem (lock-test på `'Instrument`).
3. Kontrollmått: `--h-control: 36px`, radier 10/14px, 4px-spacing-skala
   `--s1…--s14` — alla domän-CSS slutar hårdkoda.
4. Kontrastregel i kommentar vid färgtokens: text <12px = `--ink-muted`
   eller mörkare (uppmätt: 6.2:1 på papper; `--ink-subtle` 4.9:1 räcker inte
   för tunn 10.5px mono).

## Beslut 4 — Tangentbordsflöde

- `/` fokuserar sidans filter; fältet bär en `kbd`-chip i vila.
- Register får *roving tabindex*: en rad i tab-ordningen, `↑`/`↓` flyttar
  markering, `Enter` öppnar, `Esc` återgår. Fokusrad = inset 2px handling-ring
  + `--handling-soft`-toning (inset för att kortets `overflow` inte klipper).
- Ringen är överallt 2px `var(--ring)` / offset 2px — inputs inkluderade
  (mockupens 3px-glow avskedad; `theme.css` har redan rätt mönster).

## Sekvens — atomära commits, varje med visuell evidens

1. `feat(ui): land sans-first typography + control metrics in theme.css`
2. `refactor(ui): consolidate shell buttons on .ui-btn, delete legacy`
3. `test(ui): lock button classes and breakpoint values`
4. `feat(ui): sidebar groups` (AppNavigation.jsx — liten, isolerad)
5. `feat(ui): register component + Fakturor/Bevakningar/Granskning`
6. `feat(ui): unified empty states` (en per sektion, samma mönster)
7. `feat(ui): keyboard flow (roving tabindex, /, Enter, Esc)`
8. Uppdatera `DESIGN.md` — serif-eran dokumenteras som ersatt beslut.

## Risker och gränser

- **Rör inte** `backend/app`, `backend/pyproject.toml` eller andra ytor på
  desktop-leveransens hash-sökvägar — denna plan är uteslutande `brfv2-mockup/src`.
- `xs_mobilapp` och `kalla-native` har egna tokens och påverkas inte;
  sans-first-paritet dit är ett eget beslut.
- Hemsidans publicerade sajt (`site.css`) är ett separat system by design —
  dess breakpoints (860/560) ingår i mappningen men visuell granskning sker
  mot publicerad sajt, inte produktkrom.
