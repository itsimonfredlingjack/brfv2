import { Image } from 'expo-image'
import * as Haptics from 'expo-haptics'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native'
import Animated from 'react-native-reanimated'
import { SafeAreaView } from 'react-native-safe-area-context'

import { api } from '../api/client'
import type { Citation, Extraction, PageDims } from '../api/types'
import { passageZoom, pickPageWidth, rectsToBoxes, rectsUnion } from '../lib/rects'
import { metaCache } from '../state/journal'
import { getPage } from '../state/pageCache'
import type { useHeroFlight } from '../state/useHeroFlight'
import { color, font, radius, space } from '../theme/tokens'
import { CheckIcon, ChevronLeft, ChevronRight, CloseIcon, EyeIcon } from './icons'

export interface KallaTarget {
  documentId: string
  documentName: string
  page: number
  /** Present when opened from a citation; absent when browsing a document
   * from Bibliotek/Dokument with nothing specific to verify. */
  citation: Citation | null
}

type Framing = 'passage' | 'page'
const SCROLL_PADDING = 16

export function KallaSheet({
  brfId,
  target,
  hero,
  onClose,
  onOpenVisa,
}: {
  brfId: string
  target: KallaTarget
  hero: ReturnType<typeof useHeroFlight>
  onClose: () => void
  onOpenVisa: () => void
}) {
  const citation = target.citation
  const { width: windowWidth } = useWindowDimensions()

  const [page, setPage] = useState(target.page)
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [framing, setFraming] = useState<Framing>(citation ? 'passage' : 'page')
  const [available, setAvailable] = useState(windowWidth - SCROLL_PADDING * 2)
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [imageFromCache, setImageFromCache] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)
  /** The rasterized page is decoded and painted — not merely fetched. The
   * hero flight waits on this; see the flight effect below. */
  const [imageLoaded, setImageLoaded] = useState(false)

  const scrollRef = useRef<ScrollView>(null)
  const highlightRef = useRef<View>(null)
  const flownRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    metaCache.extraction
      .read(brfId, target.documentId)
      .then((cached) => cached && !cancelled && setExtraction(cached))
      .catch(() => {})
    api
      .getExtraction(brfId, target.documentId)
      .then((fresh) => {
        if (cancelled) return
        setExtraction(fresh)
        void metaCache.extraction.write(brfId, target.documentId, fresh).catch(() => {})
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [brfId, target.documentId])

  const pageCount = extraction?.document.pages ?? target.page
  const dims: PageDims | null = extraction?.pages.find((p) => p.number === page) ?? null
  const onCitedPage = citation != null && citation.page === page

  const zoom = useMemo(() => {
    if (framing === 'page' || !onCitedPage || !dims || !available) return 1
    return passageZoom(citation!.rects, dims, available)
  }, [framing, onCitedPage, citation, dims, available])

  const pageWidthPx = available ? Math.round(available * zoom) : 0
  const pageHeightPx = dims ? Math.round(pageWidthPx * (dims.height / dims.width)) : 0
  const renderWidth = pickPageWidth(pageWidthPx || available || 360, 2)

  useEffect(() => {
    let cancelled = false
    // Reset to loading for the NEW page/width before fetching it below —
    // the documented exception, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setImageUri(null)
    setImageError(null)
    setImageLoaded(false)
    async function load() {
      try {
        const url = await api.pageImageUrl(brfId, target.documentId, page, renderWidth)
        const result = await getPage(brfId, target.documentId, page, renderWidth, url)
        if (cancelled) return
        setImageUri(result.uri)
        setImageFromCache(result.fromCache)
      } catch {
        if (!cancelled) setImageError('Sidan kunde inte hämtas.')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [brfId, target.documentId, page, renderWidth])

  /* Gated on the page having painted: a highlight floating over the loading
   * placeholder marks nothing, and it would show the destination before the
   * card has flown to it. Mounting them with the image also means the primary
   * box's ref is attached by the time the flight effect below measures it. */
  const boxes = onCitedPage && dims && imageLoaded ? rectsToBoxes(citation!.rects, dims) : []

  // Bring the passage into view. Runs on geometry alone (from /extraction),
  // so the page is already scrolled to the passage by the time it paints.
  useEffect(() => {
    if (!dims || !pageWidthPx || !pageHeightPx) return
    const union = onCitedPage && citation ? rectsUnion(citation.rects) : null

    if (!union) {
      scrollRef.current?.scrollTo({ x: 0, y: 0, animated: false })
    } else {
      const hlLeft = (union.x0 / dims.width) * pageWidthPx
      const hlWidth = ((union.x1 - union.x0) / dims.width) * pageWidthPx
      const hlTop = (union.y0 / dims.height) * pageHeightPx
      const hlHeight = ((union.y1 - union.y0) / dims.height) * pageHeightPx

      const viewportW = available
      const readingMargin = 12
      const left =
        hlWidth >= viewportW * 0.9 ? hlLeft - readingMargin : hlLeft + hlWidth / 2 - viewportW / 2
      scrollRef.current?.scrollTo({
        x: Math.max(0, left),
        y: Math.max(0, hlTop + hlHeight / 2 - 220),
        animated: false,
      })
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dims, pageWidthPx, pageHeightPx])

  // Hand the real highlight's screen position to the hero flight — but only
  // once the rasterized page has actually painted. The destination geometry
  // is known as soon as /extraction lands, and flying then sent the card to a
  // highlight hovering over a blank placeholder: the passage the card is
  // supposed to visibly *become* had not been drawn yet, and the page popped
  // in underneath mid-flight. If the page never loads the flight is simply
  // skipped and the real highlight stays visible — never a landing on nothing.
  useEffect(() => {
    if (!imageLoaded || !dims || !pageWidthPx || !pageHeightPx) return
    if (flownRef.current || page !== target.page || !onCitedPage) return
    flownRef.current = true
    const frame = requestAnimationFrame(() => {
      void hero.registerDestination(highlightRef.current)
    })
    return () => cancelAnimationFrame(frame)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageLoaded, dims, pageWidthPx, pageHeightPx])

  const goTo = useCallback(
    (next: number) => {
      const clamped = Math.min(Math.max(1, next), pageCount)
      if (clamped !== page) {
        Haptics.selectionAsync().catch(() => {})
        setPage(clamped)
      }
    },
    [page, pageCount],
  )

  const canFocusPassage = citation != null && citation.rects.length > 0
  const toggleFraming = () => setFraming((f) => (f === 'passage' ? 'page' : 'passage'))

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.docName} numberOfLines={1}>
            {target.documentName}
          </Text>
          <Text style={styles.docSub}>
            Sida {page} av {pageCount}
            {imageFromCache ? ' · nedladdad' : ''}
          </Text>
        </View>
        <Pressable onPress={onClose} style={styles.closeBtn} accessibilityLabel="Stäng källa">
          <CloseIcon />
        </Pressable>
      </View>

      {citation && (
        <View style={[styles.quoteBar, citation.approximate && styles.quoteBarApprox]}>
          <View style={styles.quoteStatus}>
            {citation.approximate ? (
              <Text style={styles.quoteStatusApproxText}>◌ Ungefärlig markering — skannat original</Text>
            ) : (
              <>
                <CheckIcon size={13} />
                <Text style={styles.quoteStatusText}>Verifierat ordagrant i dokumentet</Text>
              </>
            )}
          </View>
          <Text style={styles.quote}>&ldquo;{citation.quote}&rdquo;</Text>
        </View>
      )}

      {citation && !onCitedPage && (
        <View style={styles.offpage}>
          <Text style={styles.offpageText}>Markeringen finns på sida {citation.page}</Text>
          <Pressable onPress={() => goTo(citation.page)}>
            <Text style={styles.offpageLink}>Gå dit</Text>
          </Pressable>
        </View>
      )}

      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: SCROLL_PADDING }}
        onLayout={(e) => setAvailable(e.nativeEvent.layout.width - SCROLL_PADDING * 2)}
        minimumZoomScale={1}
        maximumZoomScale={4}
        pinchGestureEnabled
        bouncesZoom
      >
        <View style={{ width: pageWidthPx || available, aspectRatio: dims ? dims.width / dims.height : 1 / 1.414 }}>
          {imageUri ? (
            <Image
              source={{ uri: imageUri }}
              style={StyleSheet.absoluteFill}
              contentFit="fill"
              onLoad={() => setImageLoaded(true)}
            />
          ) : (
            <View style={[StyleSheet.absoluteFill, styles.skeleton]} />
          )}

          {boxes.map((box, index) => {
            const isPrimary = index === 0
            const boxStyle = {
              position: 'absolute' as const,
              left: box.left * pageWidthPx,
              top: box.top * pageHeightPx,
              width: box.width * pageWidthPx,
              height: box.height * pageHeightPx,
            }
            if (isPrimary) {
              return (
                <Animated.View
                  key={index}
                  ref={highlightRef}
                  collapsable={false}
                  style={[boxStyle, styles.highlight, citation?.approximate && styles.highlightApprox, hero.realHighlightStyle]}
                />
              )
            }
            return (
              <Animated.View
                key={index}
                style={[boxStyle, styles.highlight, citation?.approximate && styles.highlightApprox, hero.realHighlightStyle]}
              />
            )
          })}
        </View>

        {imageError && <Text style={styles.error}>{imageError}</Text>}
      </ScrollView>

      <View style={styles.footer}>
        <View style={styles.pager}>
          <Pressable onPress={() => goTo(page - 1)} disabled={page <= 1} style={[styles.pagerBtn, page <= 1 && styles.pagerBtnDisabled]}>
            <ChevronLeft />
          </Pressable>
          <Text style={styles.pagerCount}>
            {page} / {pageCount}
          </Text>
          <Pressable onPress={() => goTo(page + 1)} disabled={page >= pageCount} style={[styles.pagerBtn, page >= pageCount && styles.pagerBtnDisabled]}>
            <ChevronRight />
          </Pressable>
        </View>

        {canFocusPassage && onCitedPage && (
          <Pressable onPress={toggleFraming} style={styles.framingBtn}>
            <Text style={styles.framingLabel} numberOfLines={1}>
              {framing === 'passage' ? 'Hela sidan' : 'Visa passagen'}
            </Text>
          </Pressable>
        )}

        <Pressable onPress={onOpenVisa} style={styles.visaBtn}>
          <EyeIcon size={16} />
          <Text style={styles.visaLabel} numberOfLines={1}>
            Visa för någon
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bgKalla },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: color.hairline,
  },
  docName: { fontFamily: font.sansSemibold, fontSize: 15, color: color.ink },
  docSub: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.7, color: color.ink38, marginTop: 4 },
  closeBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: color.surfaceStrong },
  quoteBar: {
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    backgroundColor: color.groundedTint,
    borderBottomWidth: 1,
    borderBottomColor: color.groundedBorder,
  },
  quoteBarApprox: { backgroundColor: color.refusalTint, borderBottomColor: color.refusalBorder },
  quoteStatus: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  quoteStatusText: { fontFamily: font.monoBold, fontSize: 9.5, letterSpacing: 1, color: color.grounded },
  quoteStatusApproxText: { fontFamily: font.monoBold, fontSize: 9.5, letterSpacing: 1, color: color.refusal },
  quote: { fontFamily: font.serifItalic, fontStyle: 'italic', fontSize: 14, lineHeight: 19, color: color.ink85, marginTop: 6 },
  offpage: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    paddingVertical: space.sm,
    backgroundColor: color.surface,
  },
  offpageText: { fontFamily: font.sans, fontSize: 12.5, color: color.ink50 },
  offpageLink: { fontFamily: font.sansSemibold, fontSize: 12.5, color: color.action },
  skeleton: { backgroundColor: '#E5E4E1' },
  highlight: {
    backgroundColor: color.hlFill,
    borderWidth: 1.5,
    borderColor: color.hlEdge,
    borderRadius: 2,
  },
  highlightApprox: { borderStyle: 'dashed' },
  error: { fontFamily: font.sans, fontSize: 13, color: color.error, textAlign: 'center', marginTop: space.lg },
  /* Sized to fit a 360dp phone: pager + toggle + action at full width came to
   * ~406dp, which used to push "Visa för någon" off the right edge entirely.
   * Spacing is tightened here and the secondary toggle is the only label
   * allowed to give way — the primary action keeps its words. */
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderTopWidth: 1,
    borderTopColor: color.hairline,
  },
  pager: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  pagerBtn: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: color.surfaceStrong, alignItems: 'center', justifyContent: 'center' },
  pagerBtnDisabled: { opacity: 0.4 },
  pagerCount: { fontFamily: font.mono, fontSize: 12, color: color.ink65, minWidth: 40, textAlign: 'center' },
  framingBtn: { flexShrink: 1, minWidth: 0, paddingHorizontal: space.sm, paddingVertical: space.sm },
  framingLabel: { fontFamily: font.sansMedium, fontSize: 12.5, color: color.ink65 },
  visaBtn: {
    marginLeft: 'auto',
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    height: 40,
    paddingHorizontal: space.md,
    borderRadius: radius.md,
    backgroundColor: color.action,
  },
  visaLabel: { flexShrink: 0, fontFamily: font.sansSemibold, fontSize: 12.5, color: '#fff' },
})
