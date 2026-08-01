/**
 * Träff — the brand geometry, transcribed from the identity document
 * ("Träff · visuell identitet v2", juli 2026, §02 Geometrin and §08 Ikon och
 * bruk). The identity is the highest visual source of truth, and these are
 * the numbers it locks: nothing about ◉ is free-hand.
 *
 * ◉ carries two different meanings and they must never blur together (§01):
 *
 *   A · VARUMÄRKET  — always complete, always monochrome. Header, launcher
 *     icon, print. Here ◉ is a *name*: it says who is speaking, not what is
 *     true, so it never wears a state colour — not even green.
 *   B · STATUSMÄRKET — starts empty. The core is drawn in the same instant a
 *     passage is verified verbatim, never a millisecond earlier. "En fylld
 *     kärna utan citat är en lögn i formspråket."
 *
 * `BrandMark` renders A. `StatusMark` renders B. They share this geometry
 * and nothing else.
 */

export const mark = {
  /** Ring weight as a fraction of the OUTER diameter. §02: "Vikten är 8 % av
   *  ytterdiametern och ändras aldrig." */
  ringWeight: 0.08,

  /** Core diameter as a fraction of the INNER dimension. §02: "Solid,
   *  koncentrisk, 46 % av innermåttet. Alltid centrerad: en träff sitter
   *  aldrig snett." */
  coreOfInner: 0.46,

  /** Below this the gap stops reading, so the ring is dropped and the mark
   *  becomes the solid dot alone (§02 "Minsta storlek": 16 px digitally). */
  minRingSize: 16,

  /** The solid dot that replaces the full mark under `minRingSize`, as a
   *  fraction of the nominal size — from the identity's own <16 sample. */
  dotOfOuter: 0.56,

  /** Mark diameter as a fraction of the visible icon field (§08). */
  iconField: 0.52,
} as const

/**
 * Core diameter as a fraction of the OUTER diameter — 0.46 × (1 − 2 × 0.08).
 * Also the lockup's mark-to-wordmark gap: §05 "Mellanrum = kärnans diameter."
 */
export const CORE_OF_OUTER = mark.coreOfInner * (1 - 2 * mark.ringWeight)

/**
 * Ring weight for a given outer diameter. §02: "Ringvikten skalas optiskt,
 * inte matematiskt. Den får aldrig se hårfin ut." A flat 8 % goes thin at
 * the bottom of the scale, so the floor below reproduces the identity's own
 * size samples exactly (64→5, 32→2.5, 16→1.4).
 */
export function ringWeightFor(size: number): number {
  return Math.max(1.4, size * mark.ringWeight)
}

/** Core diameter for a given outer diameter. */
export function coreSizeFor(size: number): number {
  return size * CORE_OF_OUTER
}

/**
 * The wordmark lockup (§05). The mark stands *before* the name at cap
 * height — "ett bekräftelsemärke framför ett påstående, inte en ikon bredvid
 * en etikett" — which the identity draws as a 50 px mark against 56 px of
 * Instrument Serif.
 */
export const lockup = {
  markToFontSize: 50 / 56,
  /** §05: Instrument Serif Regular, spärrning −3,5 %. */
  tracking: -0.035,
} as const

/**
 * Mark size for a lockup — never below the size at which the ring survives.
 *
 * The 0.893 ratio above comes from the identity's *large* primary lockup.
 * Applied naively to a small header it lands under 16 dp, `BrandMark`
 * correctly falls back to the solid dot, and the wordmark quietly loses its
 * ring. That is exactly what happened at 17 px in the Fråga header, caught
 * on device: ● Träff instead of ◉ Träff.
 *
 * The sub-16 fallback exists for a mark shrinking into a genuinely tiny
 * slot, not for the brand lockup — which the identity always draws complete
 * (§08 sets a 19 px ◉ beside 14 px of type in the product header,
 * proportionally *larger* than the primary lockup, for this very reason).
 * So the floor wins over the ratio: the mark grows to meet it rather than
 * degrading.
 */
export function lockupMarkSize(fontSize: number): number {
  return Math.max(mark.minRingSize, Math.round(fontSize * lockup.markToFontSize))
}
