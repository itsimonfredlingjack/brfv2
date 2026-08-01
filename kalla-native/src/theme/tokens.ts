/**
 * Design tokens for direction 3a ("ett ljus, en hög, sex tillstånd"),
 * transcribed from the approved clickable prototype
 * (claude.ai/design/p/a2d950e6-ff9f-48e7-9993-ae2b584b6570, §3a).
 *
 * Governing idea: one physical light lives over the document corpus. At
 * rest it lies still; asking sets it sweeping; a grounded answer leaves it
 * resting on the page that carried the proof. Colour carries meaning, never
 * decoration — cool white-blue is the search light, green is belagt
 * (grounded), amber is vägran (refusal, and refusal is CORRECT behavior),
 * and the one saturated accent (electric blue) is reserved for actions:
 * skicka and öppna källa. Never for state.
 *
 * The product is now called **Träff**, and the visual identity
 * ("Träff · visuell identitet v2", §06 Färg som betydelse) is the governing
 * source of truth above this file. It ratifies exactly these values and
 * exactly these meanings — skal #07080B, sökljus #CFE0FF, belagt #4FC79C,
 * vägran #E5B45C, handling #2E6BFF, överstrykning #FFD600 — so nothing in
 * the palette moved when the name did. See `brand.ts` for the mark itself.
 */

export const color = {
  // Chrome — near-black, not pure black, so depth reads under the glow.
  bg: '#07080B',
  bgKalla: '#050609',
  bgVisa: '#000000',

  surface: 'rgba(255,255,255,0.04)',
  surfaceStrong: 'rgba(255,255,255,0.07)',
  surfacePress: 'rgba(255,255,255,0.09)',
  hairline: 'rgba(255,255,255,0.08)',
  hairlineStrong: 'rgba(255,255,255,0.14)',

  // Ink, on dark chrome.
  ink: '#ECEDEF',
  ink85: 'rgba(236,237,239,0.85)',
  ink65: 'rgba(236,237,239,0.65)',
  ink50: 'rgba(236,237,239,0.5)',
  ink38: 'rgba(236,237,239,0.38)',
  ink25: 'rgba(236,237,239,0.25)',

  // The search light — cool white-blue, used only for the searching state.
  light: '#CFE0FF',
  lightDim: 'rgba(207,224,255,0.28)',
  lightGlow: 'rgba(207,224,255,0.1)',

  // The one electric accent. Actions only — skicka, öppna källa. Never a
  // state colour, so it never competes with grounded/refusal meaning.
  action: '#2E6BFF',
  actionPress: '#1F4FD8',
  actionTint: 'rgba(46,107,255,0.12)',
  actionTintBorder: 'rgba(46,107,255,0.34)',

  // Belagt — a citation verified verbatim against the source.
  grounded: '#4FC79C',
  groundedTint: 'rgba(79,199,156,0.12)',
  groundedBorder: 'rgba(79,199,156,0.32)',
  groundedGlow: 'rgba(79,199,156,0.3)',

  // Vägran — amber, never red. The product refusing is correct behavior.
  refusal: '#E5B45C',
  refusalTint: 'rgba(229,180,92,0.12)',
  refusalBorder: 'rgba(229,180,92,0.34)',

  // Actual failures — network, session, model. Reserved for what is
  // genuinely broken, never for a refusal.
  error: '#E5484D',
  errorTint: 'rgba(229,72,77,0.14)',
  errorBorder: 'rgba(229,72,77,0.36)',

  // The highlighter. Identical across every screen the passage appears on
  // (Svar preview, Källa, Visa) so the eye recognises it as the same mark.
  hlFill: 'rgba(255,214,0,0.42)',
  hlEdge: '#C9A227',

  // The document itself. Never inverted, never recoloured — it is the
  // evidence, not chrome.
  paper: '#FFFFFF',
  paperInk: '#14161A',
  paperMuted: '#8A8F97',
  paperRule: '#D8DADE',
} as const

export const font = {
  sans: 'InstrumentSans_400Regular',
  sansMedium: 'InstrumentSans_500Medium',
  sansSemibold: 'InstrumentSans_600SemiBold',
  sansBold: 'InstrumentSans_700Bold',
  serif: 'InstrumentSerif_400Regular',
  serifItalic: 'InstrumentSerif_400Regular_Italic',
  mono: 'JetBrainsMono_500Medium',
  monoBold: 'JetBrainsMono_700Bold',
} as const

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const

export const radius = {
  sm: 10,
  md: 13,
  lg: 15,
  xl: 20,
  pill: 999,
  // Paper has corners. The page image is the one surface that never rounds.
  page: 0,
} as const

/**
 * Motion, transcribed from the prototype's own timing. The hero flight
 * (citation → highlighted passage) is the single most important animation
 * in the product — everything else is secondary to reading correctly.
 */
export const motion = {
  push: 180,
  sheet: 240,
  heroFlight: 460,
  heroCardFade: 190,
  heroHighlightFade: 240,
  heroHighlightDelay: 170,
  highlightPaintDelay: 120,
  chipLift: 320,
  easing: [0.2, 0, 0, 1] as [number, number, number, number],
} as const

export const touchTarget = 44
