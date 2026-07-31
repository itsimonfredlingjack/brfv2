import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { api } from '../api/client'
import type { Citation, Extraction } from '../api/types'
import { passageZoom, pickPageWidth, rectsToBoxes, rectsUnion } from '../lib/rects'
import { metaCache } from '../state/localStore'
import { usePageImage } from '../state/usePageImage'
import { CheckIcon, ChevronLeft, ChevronRight, CloseIcon } from './icons'

export interface KallaTarget {
  documentId: string
  documentName: string
  page: number
  /** Present when opened from a citation; absent when browsing a document. */
  citation: Citation | null
}

/** How the page is framed. `passage` zooms in so the cited line is actually
 * readable when the phone is held out to someone; `page` fits the whole
 * sheet of paper for orientation. */
type Framing = 'passage' | 'page'

/** Padding inside the scroll viewport, kept in sync with .sheet__scroll. */
const SCROLL_PADDING = 16

/**
 * The source sheet — the moment the product is selling: the answer stops
 * being a claim and becomes something you can hold out to another person.
 *
 * On open from a citation it must answer, without being asked:
 * which document, which page, where the passage is, whether the match is
 * exact, and how to get back.
 */
export function KallaSheet({
  brfId,
  target,
  onClose,
}: {
  brfId: string
  target: KallaTarget
  onClose: () => void
}) {
  const citation = target.citation

  const [page, setPage] = useState(target.page)
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [framing, setFraming] = useState<Framing>(citation ? 'passage' : 'page')
  const [available, setAvailable] = useState(0)

  const scrollRef = useRef<HTMLDivElement>(null)
  const pageRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusTo = useRef<Element | null>(null)
  const centeredFor = useRef<string>('')

  // Page geometry: cache-first, so a page seen before still measures offline.
  useEffect(() => {
    let cancelled = false

    async function load() {
      const cached = await metaCache.extraction.read(brfId, target.documentId).catch(() => undefined)
      if (cached && !cancelled) setExtraction(cached)
      try {
        const fresh = await api.getExtraction(brfId, target.documentId)
        if (cancelled) return
        setExtraction(fresh)
        await metaCache.extraction.write(brfId, target.documentId, fresh).catch(() => {})
      } catch {
        // Cached geometry is enough to place a highlight.
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [brfId, target.documentId])

  // Measure the scroll viewport — everything below is derived from it.
  useLayoutEffect(() => {
    const element = scrollRef.current
    if (!element) return undefined

    const measure = () => {
      const width = element.clientWidth - SCROLL_PADDING * 2
      if (width > 0) setAvailable(width)
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const pageCount = extraction?.document.pages ?? target.page
  const dims = extraction?.pages.find((p) => p.number === page) ?? null
  const onCitedPage = citation != null && citation.page === page

  /* Zoom so the cited line is legible rather than hairline-thin. An A4 page
   * squeezed into 320 css px renders 10pt body text at ~5px — technically
   * "shown", practically unreadable, which is exactly the moment this
   * product exists for. */
  const zoom = useMemo(() => {
    if (framing === 'page' || !onCitedPage || !dims || !available) return 1
    return passageZoom(citation.rects, dims, available)
  }, [framing, onCitedPage, citation, dims, available])

  const pageWidthPx = available ? Math.round(available * zoom) : 0
  const renderWidth = pickPageWidth(pageWidthPx || available || 360, window.devicePixelRatio)

  const image = usePageImage(brfId, target.documentId, page, renderWidth)
  const boxes = onCitedPage && dims ? rectsToBoxes(citation.rects, dims) : []

  // Bring the passage into view once the page is measured and painted.
  useEffect(() => {
    const scroll = scrollRef.current
    const pageElement = pageRef.current
    if (!scroll || !pageElement || !dims || !image.url) return

    const key = `${page}:${framing}:${pageWidthPx}`
    if (centeredFor.current === key) return

    const union = onCitedPage ? rectsUnion(citation.rects) : null

    // Not the cited page, or nothing to aim at: start at the top.
    //
    // Note this deliberately does NOT depend on zoom. A wide screen can leave
    // zoom at 1 because the text is already legible, while the page is still
    // far taller than the viewport — landscape phones especially. Framing
    // controls how big the page is, never whether the passage is on screen.
    if (!union) {
      scroll.scrollTo({ top: 0, left: 0 })
      centeredFor.current = key
      return
    }

    // Where the page sits inside the scroller's content box. Measured rather
    // than read off offsetTop/offsetLeft, which are relative to the nearest
    // POSITIONED ancestor — here the fixed sheet, so they silently include
    // the header and quote bar and push the passage off the top.
    const pageBox = pageElement.getBoundingClientRect()
    const scrollBox = scroll.getBoundingClientRect()
    const pageLeft = pageBox.left - scrollBox.left + scroll.scrollLeft
    const pageTop = pageBox.top - scrollBox.top + scroll.scrollTop

    const pageHeightPx = pageWidthPx * (dims.height / dims.width)
    const hlLeft = (union.x0 / dims.width) * pageWidthPx
    const hlWidth = ((union.x1 - union.x0) / dims.width) * pageWidthPx
    const hlTop = (union.y0 / dims.height) * pageHeightPx
    const hlHeight = ((union.y1 - union.y0) / dims.height) * pageHeightPx

    // A cited line usually spans most of the page width. Centring it then
    // cuts BOTH ends; landing on its start lets you simply read it.
    const readingMargin = 12
    const left =
      hlWidth >= scroll.clientWidth * 0.9
        ? pageLeft + hlLeft - readingMargin
        : pageLeft + hlLeft + hlWidth / 2 - scroll.clientWidth / 2

    scroll.scrollTo({
      left: Math.max(0, left),
      top: Math.max(0, pageTop + hlTop + hlHeight / 2 - scroll.clientHeight / 2),
      behavior: 'auto',
    })
    centeredFor.current = key
  }, [citation, dims, framing, image.url, onCitedPage, page, pageWidthPx, zoom])

  // Modal semantics: focus in on open, focus back on close, Escape closes.
  useEffect(() => {
    returnFocusTo.current = document.activeElement
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    // Lets the frame behind reflow into the remaining space on wide screens
    // instead of sitting hidden underneath the sheet.
    document.body.classList.add('kalla-open')

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      document.body.classList.remove('kalla-open')
      const element = returnFocusTo.current
      if (element instanceof HTMLElement) element.focus()
    }
  }, [onClose])

  const goTo = useCallback(
    (next: number) => {
      const clamped = Math.min(Math.max(1, next), pageCount)
      if (clamped !== page) setPage(clamped)
    },
    [page, pageCount],
  )

  const toggleFraming = () => setFraming((current) => (current === 'passage' ? 'page' : 'passage'))
  const canFocusPassage = citation != null && citation.rects.length > 0

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={`Källa: ${target.documentName}`}>
      <div className="sheet__header">
        <div className="sheet__title">
          <div className="sheet__doc">{target.documentName}</div>
          <div className="sheet__sub">
            Sida {page} av {pageCount}
            {image.fromCache && ' · nedladdad'}
          </div>
        </div>
        <button ref={closeRef} type="button" className="sheet__close" onClick={onClose} aria-label="Stäng källa">
          <CloseIcon />
        </button>
      </div>

      {/* What the passage says, in readable type — so the person you are
          showing it to knows what to look for before finding it on the page. */}
      {citation && (
        <div className={`quotebar${citation.approximate ? ' quotebar--approximate' : ''}`}>
          <div className="quotebar__status">
            {citation.approximate ? (
              <>
                <span aria-hidden="true">◌</span> Ungefärlig markering — skannat original
              </>
            ) : (
              <>
                <CheckIcon /> Verifierat ordagrant i dokumentet
              </>
            )}
          </div>
          <p className="quotebar__quote">”{citation.quote}”</p>
        </div>
      )}

      {citation && !onCitedPage && (
        <div className="sheet__offpage">
          <span>Markeringen finns på sida {citation.page}</span>
          <button type="button" className="btn btn--link" onClick={() => goTo(citation.page)}>
            Gå dit
          </button>
        </div>
      )}

      {/* Focusable because it genuinely scrolls in two dimensions once the
          passage is zoomed — without a tab stop a keyboard user can see the
          highlight but never pan the rest of the page. */}
      <div
        className="sheet__scroll"
        ref={scrollRef}
        tabIndex={0}
        role="group"
        aria-label={`Sida ${page} av ${target.documentName}. Panorera med piltangenterna.`}
      >
        <div
          className="page"
          ref={pageRef}
          style={{
            width: pageWidthPx ? `${pageWidthPx}px` : '100%',
            aspectRatio: dims ? `${dims.width} / ${dims.height}` : '1 / 1.414',
          }}
        >
          {image.url ? (
            <img
              className="page__img"
              src={image.url}
              /* The quote is what a screen-reader user needs here — "PDF-sida"
               * would describe the container and hide the content. */
              alt={
                onCitedPage && citation
                  ? `Sida ${page} med markerad passage: ”${citation.quote}”`
                  : `Sida ${page} av ${target.documentName}`
              }
              data-testid="page-image"
            />
          ) : (
            <div className="skeleton page__skeleton" aria-hidden="true" />
          )}

          {boxes.map((box, index) => (
            <div
              key={index}
              className={`page__hl${citation?.approximate ? ' page__hl--approximate' : ''}`}
              style={box}
              data-testid="citation-highlight"
              aria-hidden="true"
            />
          ))}
        </div>

        {image.error && (
          <p className="sheet__error" role="alert">
            {image.error}
          </p>
        )}
      </div>

      <div className="sheet__footer">
        <div className="pager">
          <button
            type="button"
            className="pager__btn"
            onClick={() => goTo(page - 1)}
            disabled={page <= 1}
            aria-label="Föregående sida"
          >
            <ChevronLeft />
          </button>
          <span className="pager__count" aria-live="polite">
            {page} / {pageCount}
          </span>
          <button
            type="button"
            className="pager__btn"
            onClick={() => goTo(page + 1)}
            disabled={page >= pageCount}
            aria-label="Nästa sida"
          >
            <ChevronRight />
          </button>
        </div>

        {/* Hidden rather than disabled when you have paged away: off the cited
            page you ARE looking at the whole page, so a greyed-out "Hela
            sidan" would describe the state you are already in. */}
        {canFocusPassage && onCitedPage && (
          <button
            type="button"
            className="btn btn--quiet sheet__framing"
            onClick={toggleFraming}
            aria-pressed={framing === 'passage'}
            data-testid="framing-toggle"
          >
            {framing === 'passage' ? 'Hela sidan' : 'Visa passagen'}
          </button>
        )}
      </div>
    </div>
  )
}
