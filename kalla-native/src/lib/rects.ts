/* Citation rect → normalized box.
 *
 * This is the whole reason the app can skip a PDF-rendering engine. The
 * backend rasterizes a page at a known pixel width; the citation rects are
 * ALREADY top-left-origin PDF points in that same coordinate space
 * (backend/app/extract.py reads `page.rect` + `get_text("words")`, and
 * `get_pixmap` renders the same view, rotation included). So one uniform
 * scale is the entire transform:
 *
 *   scale = renderedWidthPx / pageWidthPt
 *
 * No y-flip, no viewport matrix, no rotation handling.
 *
 * Expressed as fractions (0..1) rather than pixels so the highlight stays
 * glued to the passage while the image reflows (rotation, tablet pane, pinch
 * zoom) without re-measuring anything — React Native applies these as
 * percentage-equivalent absolute layout using the page's own onLayout size.
 */

export interface HighlightBox {
  /** Fractions of the rendered page element, 0..1. */
  left: number
  top: number
  width: number
  height: number
}

export interface PageSize {
  /** Page width in PDF points, from /extraction (or X-Page-Width-Pt). */
  width: number
  /** Page height in PDF points. */
  height: number
}

/**
 * Convert one `[x0, y0, x1, y1]` rect in top-left-origin PDF points into a
 * fractional box. Returns null for a rect that is malformed or entirely
 * outside the page — the backend already rejects out-of-bounds rects (SPEC
 * §2.7), so this is defense in depth, and a bad rect must render as
 * *nothing* rather than as a box in the wrong place.
 */
export function rectToBox(rect: number[], page: PageSize): HighlightBox | null {
  if (rect.length < 4) return null
  const [x0, y0, x1, y1] = rect as [number, number, number, number]
  if (![x0, y0, x1, y1].every(Number.isFinite)) return null
  if (page.width <= 0 || page.height <= 0) return null

  const left = Math.min(x0, x1)
  const right = Math.max(x0, x1)
  const top = Math.min(y0, y1)
  const bottom = Math.max(y0, y1)

  // Clamp to the page rather than dropping: a rect grazing the margin is a
  // real citation whose box should stop at the edge.
  const cl = Math.max(0, Math.min(left, page.width))
  const cr = Math.max(0, Math.min(right, page.width))
  const ct = Math.max(0, Math.min(top, page.height))
  const cb = Math.max(0, Math.min(bottom, page.height))

  if (cr - cl <= 0 || cb - ct <= 0) return null

  return {
    left: cl / page.width,
    top: ct / page.height,
    width: (cr - cl) / page.width,
    height: (cb - ct) / page.height,
  }
}

/** Every renderable box for a citation's rects, in order. */
export function rectsToBoxes(rects: number[][], page: PageSize): HighlightBox[] {
  return rects.map((r) => rectToBox(r, page)).filter((b): b is HighlightBox => b !== null)
}

/**
 * Pick the rasterization width to request for a given layout width. The
 * backend allowlist is closed (720 / 1080 / 1440), so this picks the
 * smallest width that still covers the device's physical pixels — asking
 * for 1440 on a small phone wastes bandwidth the user is paying for.
 */
export function pickPageWidth(cssWidth: number, devicePixelRatio: number): 720 | 1080 | 1440 {
  const needed = cssWidth * Math.min(devicePixelRatio || 1, 3)
  if (needed <= 720) return 720
  if (needed <= 1080) return 1080
  return 1440
}

export interface RectUnion {
  x0: number
  y0: number
  x1: number
  y1: number
}

/** The bounding box of every rect in a citation, in PDF points. */
export function rectsUnion(rects: number[][]): RectUnion | null {
  let union: RectUnion | null = null

  for (const rect of rects) {
    if (rect.length < 4) continue
    const [a, b, c, d] = rect as [number, number, number, number]
    if (![a, b, c, d].every(Number.isFinite)) continue

    const x0 = Math.min(a, c)
    const x1 = Math.max(a, c)
    const y0 = Math.min(b, d)
    const y1 = Math.max(b, d)

    union = union
      ? {
          x0: Math.min(union.x0, x0),
          y0: Math.min(union.y0, y0),
          x1: Math.max(union.x1, x1),
          y1: Math.max(union.y1, y1),
        }
      : { x0, y0, x1, y1 }
  }

  return union
}

/** Line height in CSS px at which Swedish body text is comfortably readable
 * at arm's length — the distance at which someone else is looking at it. */
const READABLE_LINE_PX = 17
const MAX_ZOOM = 4

/**
 * How far to zoom so the cited passage is actually readable.
 *
 * Fitting an A4 page into a phone's width renders 10pt body text at about
 * five pixels. The highlight is visible; the words are not. Since the whole
 * point is holding the phone out to another person, the source view zooms
 * to the *line*, not to the page.
 *
 * Driven by the citation's own rect height — the true rendered line height —
 * so it adapts to large-print documents and dense annual reports alike.
 * Returns 1 (fit width) when the page is already legible.
 */
export function passageZoom(rects: number[][], page: PageSize, availableWidth: number): number {
  const union = rectsUnion(rects)
  if (!union || page.width <= 0 || availableWidth <= 0) return 1

  // Median-ish line height: use the shortest rect, since a multi-line
  // citation's tallest rect can span more than one line.
  const heights = rects
    .filter((r) => r.length >= 4 && r.every(Number.isFinite))
    .map((r) => Math.abs((r[3] as number) - (r[1] as number)))
    .filter((h) => h > 0)
  const lineHeightPt = heights.length ? Math.min(...heights) : union.y1 - union.y0
  if (lineHeightPt <= 0) return 1

  const pxPerPt = availableWidth / page.width
  const renderedLinePx = lineHeightPt * pxPerPt
  if (renderedLinePx <= 0) return 1

  const zoom = READABLE_LINE_PX / renderedLinePx
  if (!Number.isFinite(zoom)) return 1
  return Math.min(Math.max(zoom, 1), MAX_ZOOM)
}
