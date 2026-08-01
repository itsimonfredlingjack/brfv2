import { Image } from 'expo-image'
import { useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { api } from '../api/client'
import type { Citation, PageDims } from '../api/types'
import { pickPageWidth, rectsToBoxes } from '../lib/rects'
import { metaCache } from '../state/journal'
import { getPage } from '../state/pageCache'
import { color, font, space } from '../theme/tokens'
import { CheckIcon } from './icons'

/**
 * "Visa för någon" — the moment the product is built for: hand the phone
 * to the person you're talking to. Pure black, minimal chrome, tap or
 * Android Back exits to Källa (not out of the source entirely — the
 * back-stack lives in state/uiMode.ts).
 */
export function VisaOverlay({
  brfId,
  documentName,
  page,
  citation,
  onExit,
}: {
  brfId: string
  documentName: string
  page: number
  citation: Citation
  onExit: () => void
}) {
  const [dims, setDims] = useState<PageDims | null>(null)
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [pageBoxWidth, setPageBoxWidth] = useState(0)

  useEffect(() => {
    let cancelled = false
    metaCache.extraction.read(brfId, citation.document_id).then((extraction) => {
      if (cancelled || !extraction) return
      const found = extraction.pages.find((p) => p.number === page)
      if (found) setDims(found)
    })
    return () => {
      cancelled = true
    }
  }, [brfId, citation.document_id, page])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const width = pickPageWidth(414, 2)
      const url = await api.pageImageUrl(brfId, citation.document_id, page, width)
      try {
        const result = await getPage(brfId, citation.document_id, page, width, url)
        if (!cancelled) setImageUri(result.uri)
      } catch {
        // Presentation mode fails silently to the quote alone — the person
        // being shown the answer still sees the verified text.
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [brfId, citation.document_id, page])

  const boxes = dims ? rectsToBoxes(citation.rects, dims) : []

  return (
    <Pressable style={StyleSheet.absoluteFill} onPress={onExit} accessibilityRole="button" accessibilityLabel="Avsluta visa-läge">
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        <View style={styles.topRow}>
          <View style={styles.badge}>
            <View style={styles.badgeDot} />
            <Text style={styles.badgeText}>VISA-LÄGE</Text>
          </View>
          <Text style={styles.hint}>TRYCK FÖR ATT AVSLUTA</Text>
        </View>

        <View style={styles.head}>
          <Text style={styles.docLabel}>
            {documentName.toUpperCase()} · SIDA {page}
          </Text>
          <Text style={styles.bigQuote}>&ldquo;{citation.quote}&rdquo;</Text>
          {!citation.approximate && (
            <View style={styles.verifiedRow}>
              <CheckIcon size={14} />
              <Text style={styles.verifiedText}>Ordagrant verifierat mot originalet</Text>
            </View>
          )}
        </View>

        <View style={styles.divider}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerLabel}>ORIGINALET</Text>
          <View style={styles.dividerLine} />
        </View>

        <View style={styles.pageWrap}>
          <View
            style={[styles.page, { aspectRatio: dims ? dims.width / dims.height : 1 / 1.414 }]}
            onLayout={(e) => setPageBoxWidth(e.nativeEvent.layout.width)}
          >
            {imageUri && <Image source={{ uri: imageUri }} style={StyleSheet.absoluteFill} contentFit="cover" />}
            {boxes.map((box, i) => {
              const w = pageBoxWidth
              const h = dims ? w * (dims.height / dims.width) : 0
              return (
                <View
                  key={i}
                  style={[
                    styles.highlight,
                    {
                      left: box.left * w,
                      top: box.top * h,
                      width: box.width * w,
                      height: box.height * h,
                    },
                  ]}
                />
              )
            })}
          </View>
        </View>
      </SafeAreaView>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bgVisa },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xxl,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: space.md,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.09)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
  },
  badgeDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: color.grounded },
  badgeText: { fontFamily: font.monoBold, fontSize: 9.5, letterSpacing: 1.1, color: 'rgba(255,255,255,0.78)' },
  hint: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 1.1, color: 'rgba(255,255,255,0.35)' },
  head: { paddingHorizontal: space.xxl, marginTop: space.xxl },
  docLabel: { fontFamily: font.monoBold, fontSize: 10, letterSpacing: 1.2, color: color.grounded },
  bigQuote: {
    fontFamily: font.serifItalic,
    fontStyle: 'italic',
    fontSize: 26,
    lineHeight: 33,
    color: '#fff',
    marginTop: space.md,
    letterSpacing: -0.2,
  },
  verifiedRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: space.lg },
  verifiedText: { fontFamily: font.sansMedium, fontSize: 12.5, color: 'rgba(255,255,255,0.55)' },
  divider: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.xxl, marginTop: space.xl },
  dividerLine: { flex: 1, height: 1, backgroundColor: 'rgba(255,255,255,0.14)' },
  dividerLabel: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 1.1, color: 'rgba(255,255,255,0.35)' },
  pageWrap: { flex: 1, marginTop: space.lg, paddingHorizontal: space.md, alignItems: 'center' },
  page: { width: '92%', maxWidth: 420, backgroundColor: '#fff', overflow: 'hidden', borderRadius: 3 },
  highlight: {
    position: 'absolute',
    backgroundColor: color.hlFill,
    borderWidth: 1.5,
    borderColor: color.hlEdge,
    borderRadius: 2,
  },
})
