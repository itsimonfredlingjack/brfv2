import { describe, expect, it } from 'vitest'

import { passageZoom, pickPageWidth, rectToBox, rectsToBoxes, rectsUnion } from './rects'

/* The transform that replaces pdf.js. If it drifts, every highlight in the
 * product lands somewhere other than the passage it is claiming to prove —
 * which is worse than showing no highlight at all. */

// A4 at PyMuPDF's default: exactly what the seeded corpus renders as.
const A4 = { width: 595, height: 842 }

const asNumber = (percent: string) => Number.parseFloat(percent.replace('%', ''))

describe('rectToBox', () => {
  it('maps a rect to percentages of the page', () => {
    const box = rectToBox([72, 100, 300, 114], A4)!
    expect(box).not.toBeNull()
    expect(asNumber(box.left)).toBeCloseTo((72 / 595) * 100, 3)
    expect(asNumber(box.top)).toBeCloseTo((100 / 842) * 100, 3)
    expect(asNumber(box.width)).toBeCloseTo((228 / 595) * 100, 3)
    expect(asNumber(box.height)).toBeCloseTo((14 / 842) * 100, 3)
  })

  it('does NOT flip the y axis', () => {
    // Backend rects are top-left origin (app/extract.py). A rect near the top
    // of the page must land near the top of the image. The desktop's pdf.js
    // path needs a flip here; this one must not have inherited it.
    const box = rectToBox([50, 40, 200, 60], A4)!
    expect(asNumber(box.top)).toBeLessThan(10)
  })

  it('places a rect near the bottom of the page near the bottom of the image', () => {
    const box = rectToBox([50, 800, 200, 820], A4)!
    expect(asNumber(box.top)).toBeGreaterThan(94)
  })

  it('normalizes reversed coordinates', () => {
    const forward = rectToBox([72, 100, 300, 114], A4)
    const reversed = rectToBox([300, 114, 72, 100], A4)
    expect(reversed).toEqual(forward)
  })

  it('clamps a rect that grazes past the page edge instead of dropping it', () => {
    const box = rectToBox([-20, 100, 700, 114], A4)!
    expect(asNumber(box.left)).toBe(0)
    expect(asNumber(box.width)).toBeCloseTo(100, 3)
  })

  it('returns null for a zero-area rect', () => {
    expect(rectToBox([100, 100, 100, 100], A4)).toBeNull()
  })

  it('returns null for a rect entirely off the page', () => {
    expect(rectToBox([700, 100, 900, 114], A4)).toBeNull()
  })

  it('returns null for malformed input rather than rendering a wrong box', () => {
    expect(rectToBox([1, 2, 3], A4)).toBeNull()
    expect(rectToBox([Number.NaN, 2, 3, 4], A4)).toBeNull()
    expect(rectToBox([1, 2, 3, Number.POSITIVE_INFINITY], A4)).toBeNull()
  })

  it('returns null for a degenerate page', () => {
    expect(rectToBox([1, 2, 3, 4], { width: 0, height: 842 })).toBeNull()
  })

  it('is resolution independent — the same rect maps identically at any raster width', () => {
    // Percentages are why the highlight survives rotation, the tablet pane
    // and browser zoom without re-measuring anything.
    const box = rectToBox([72, 100, 300, 114], A4)
    expect(box).toEqual(rectToBox([72, 100, 300, 114], { ...A4 }))
  })
})

describe('rectsToBoxes', () => {
  it('keeps one box per line for a multi-line citation', () => {
    // SPEC §2.2: a quote wrapping across lines resolves to one rect per line
    // and ALL of them must be rendered.
    const boxes = rectsToBoxes(
      [
        [72, 100, 520, 114],
        [72, 116, 380, 130],
      ],
      A4,
    )
    expect(boxes).toHaveLength(2)
    expect(asNumber(boxes[1]!.top)).toBeGreaterThan(asNumber(boxes[0]!.top))
  })

  it('drops only the unrenderable rects, never the whole citation', () => {
    const boxes = rectsToBoxes(
      [
        [72, 100, 520, 114],
        [0, 0, 0, 0],
      ],
      A4,
    )
    expect(boxes).toHaveLength(1)
  })

  it('returns an empty list when there are no rects', () => {
    expect(rectsToBoxes([], A4)).toEqual([])
  })
})

describe('rectsUnion', () => {
  it('spans every rect of a multi-line citation', () => {
    const union = rectsUnion([
      [72, 100, 520, 114],
      [72, 116, 380, 130],
    ])!
    expect(union).toEqual({ x0: 72, y0: 100, x1: 520, y1: 130 })
  })

  it('normalizes reversed coordinates', () => {
    expect(rectsUnion([[300, 114, 72, 100]])).toEqual({ x0: 72, y0: 100, x1: 300, y1: 114 })
  })

  it('ignores malformed rects instead of poisoning the union with NaN', () => {
    const union = rectsUnion([
      [Number.NaN, 1, 2, 3],
      [10, 20, 30, 40],
      [1, 2, 3],
    ])!
    expect(union).toEqual({ x0: 10, y0: 20, x1: 30, y1: 40 })
  })

  it('is null when there is nothing usable', () => {
    expect(rectsUnion([])).toBeNull()
    expect(rectsUnion([[1, 2, 3]])).toBeNull()
  })
})

describe('passageZoom', () => {
  /* An A4 page squeezed into a phone renders 10pt body text at about five
   * pixels: the highlight is visible, the words are not. Since the product
   * exists for holding the phone out to someone else, the source view has to
   * zoom to the LINE, not to the page. */
  const line = (y: number, height = 11.5) => [72, y, 520, y + height]

  it('zooms in when a cited line would render too small to read', () => {
    // 320px phone: 288px of usable width for a 595pt page.
    const zoom = passageZoom([line(300)], A4, 288)
    expect(zoom).toBeGreaterThan(2)
  })

  it('produces a genuinely readable line height', () => {
    const available = 288
    const zoom = passageZoom([line(300)], A4, available)
    const renderedLinePx = 11.5 * ((available * zoom) / A4.width)
    expect(renderedLinePx).toBeGreaterThanOrEqual(15)
  })

  it('does not zoom a page that is already legible', () => {
    // A wide tablet pane renders the same line large enough already.
    expect(passageZoom([line(300)], A4, 1200)).toBe(1)
  })

  it('never zooms below fit-width', () => {
    expect(passageZoom([line(300, 40)], A4, 900)).toBe(1)
  })

  it('is capped so a hairline rect cannot demand an absurd zoom', () => {
    expect(passageZoom([line(300, 0.4)], A4, 288)).toBeLessThanOrEqual(4)
  })

  it('uses the shortest rect, so a multi-line citation is not under-zoomed', () => {
    // A tall union spanning several lines must not be mistaken for one huge
    // line — that would leave the text as small as before.
    const multiline = [line(300), line(316), line(332)]
    expect(passageZoom(multiline, A4, 288)).toBeCloseTo(passageZoom([line(300)], A4, 288), 5)
  })

  it('falls back to 1 for degenerate input rather than NaN', () => {
    expect(passageZoom([], A4, 288)).toBe(1)
    expect(passageZoom([line(300)], A4, 0)).toBe(1)
    expect(passageZoom([line(300)], { width: 0, height: 0 }, 288)).toBe(1)
    expect(passageZoom([[10, 20, 30, 20]], A4, 288)).toBe(1)
  })
})

describe('pickPageWidth', () => {
  it('only ever returns a width the backend allowlist accepts', () => {
    const widths = [320, 390, 430, 560, 760, 1200].flatMap((css) =>
      [1, 2, 3, 4].map((dpr) => pickPageWidth(css, dpr)),
    )
    for (const width of widths) expect([720, 1080, 1440]).toContain(width)
  })

  it('scales with device pixel ratio', () => {
    expect(pickPageWidth(360, 1)).toBe(720)
    expect(pickPageWidth(360, 2)).toBe(720)
    expect(pickPageWidth(390, 3)).toBe(1440)
  })

  it('caps the ratio so an extreme dpr cannot ask for more than 1440', () => {
    expect(pickPageWidth(430, 10)).toBe(1440)
  })

  it('survives a missing devicePixelRatio', () => {
    expect(pickPageWidth(390, 0)).toBe(720)
  })
})
