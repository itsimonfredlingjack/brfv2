import { CORE_OF_OUTER, coreSizeFor, lockup, lockupMarkSize, mark, ringWeightFor } from './brand'

/**
 * The identity document calls the geometry "identitetens hårdaste regel".
 * These are not tests of our code so much as a lock on the four numbers the
 * mark is made of — if someone nudges one, the mark stops being the mark.
 */
describe('◉ geometry', () => {
  it('gives the ring 8 % of the outer diameter', () => {
    expect(ringWeightFor(100)).toBeCloseTo(8, 5)
    expect(ringWeightFor(230)).toBeCloseTo(18.4, 5)
  })

  it('gives the core 46 % of the inner dimension', () => {
    const size = 100
    const inner = size - 2 * ringWeightFor(size)
    expect(coreSizeFor(size)).toBeCloseTo(0.46 * inner, 5)
  })

  it('resolves the core to 38.64 % of the outer diameter', () => {
    expect(CORE_OF_OUTER).toBeCloseTo(0.3864, 6)
    expect(coreSizeFor(50)).toBeCloseTo(19.32, 5)
  })

  it('scales the ring optically at the bottom of the range', () => {
    // The identity's own size samples: 64→5, 32→2.5, 16→1.4. A flat 8 % goes
    // thin at 16 ("den får aldrig se hårfin ut"), so the floor takes over
    // there and only there.
    expect(ringWeightFor(64)).toBeCloseTo(5.12, 2)
    expect(ringWeightFor(32)).toBeCloseTo(2.56, 2)
    expect(ringWeightFor(16)).toBeCloseTo(1.4, 2)
    expect(ringWeightFor(16)).toBeGreaterThan(16 * mark.ringWeight)
  })

  it('never lets the ring go hairline', () => {
    for (const size of [8, 12, 16, 20, 32, 64, 128, 512]) {
      expect(ringWeightFor(size)).toBeGreaterThanOrEqual(1.4)
    }
  })

  it('sets the lockup gap to exactly the core diameter', () => {
    // §05: "Mellanrum = kärnans diameter." The identity draws a 50 px mark
    // against 56 px of Instrument Serif with a 20 px gap.
    const markSize = Math.round(56 * lockup.markToFontSize)
    expect(markSize).toBe(50)
    expect(coreSizeFor(markSize)).toBeCloseTo(19.32, 2)
  })

  it('keeps the primary lockup ratio wherever it clears the floor', () => {
    expect(lockupMarkSize(56)).toBe(50)
    expect(lockupMarkSize(44)).toBe(39)
    expect(lockupMarkSize(20)).toBe(18)
  })

  it('never lets the wordmark degrade to the ringless dot', () => {
    // Regression: the Fråga header sets 17 px, which the raw ratio rounds to
    // 15 dp — under the minimum, so the mark rendered as ● instead of ◉.
    // The brand lockup is always complete, so the floor wins.
    expect(Math.round(17 * lockup.markToFontSize)).toBeLessThan(mark.minRingSize)
    expect(lockupMarkSize(17)).toBe(mark.minRingSize)
    for (const fontSize of [8, 12, 14, 17, 20, 44, 72]) {
      expect(lockupMarkSize(fontSize)).toBeGreaterThanOrEqual(mark.minRingSize)
    }
  })
})

describe('◉ as an app icon', () => {
  it('fills 52 % of the visible field', () => {
    expect(mark.iconField).toBe(0.52)
    // Legacy square icon: the whole canvas is visible.
    expect(1024 * mark.iconField).toBeCloseTo(532.48, 2)
  })

  it('keeps the adaptive mark inside the 66 dp safe zone', () => {
    // 52 % is taken of the ~72 dp a launcher actually shows, not of the full
    // 108 dp canvas — which is what keeps it clear of every mask.
    const visible = 72
    const diameter = visible * mark.iconField
    expect(diameter).toBeCloseTo(37.44, 2)
    expect(diameter).toBeLessThan(66)
  })
})
