import { useEffect } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated'

import type { RefusalReason, RejectedCitation, RetrievalHit } from '../api/types'
import { GROUNDING_PROMISE, refusalCopy, rejectCopy } from '../lib/refusals'
import { color, font, radius, space } from '../theme/tokens'
import { EyeIcon } from './icons'
import { StatusChip, StatusMark } from './StatusMark'

export interface SuspectedSource {
  documentName: string
  documentId: string
  page: number
}

/**
 * Vägran — a full screen, not an inline card: the design's 3a·6 state.
 * Amber, never red — refusing correctly is the product working. Every
 * number here (document names, relevance bars, the escape-hatch page) comes
 * from the real `retrieval`/`rejected_citations` the backend returned;
 * nothing is invented to make the "corpus searched anyway" panel feel more
 * complete than the evidence actually is.
 */
export function RefusalScreen({
  question,
  reason,
  retrieval,
  rejected,
  suspected,
  onOpenSuspected,
}: {
  question: string
  reason: RefusalReason | null
  retrieval: RetrievalHit[]
  rejected: RejectedCitation[]
  suspected: SuspectedSource | null
  onOpenSuspected: () => void
}) {
  const copy = refusalCopy(reason)
  const isError = copy.tone === 'error'
  const tint = isError ? color.error : color.refusal

  const breathe = useSharedValue(0)
  useEffect(() => {
    breathe.value = withRepeat(withTiming(1, { duration: 1800, easing: Easing.inOut(Easing.ease) }), -1, true)
  }, [breathe])
  const ringStyle = useAnimatedStyle(() => ({ opacity: 0.15 + breathe.value * 0.25 }))

  const topByDoc = new Map<string, RetrievalHit>()
  for (const hit of retrieval) {
    const current = topByDoc.get(hit.document_name)
    if (!current || hit.confidence > current.confidence) topByDoc.set(hit.document_name, hit)
  }
  const bars = Array.from(topByDoc.values())
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 4)
  const maxConfidence = Math.max(0.01, ...bars.map((b) => b.confidence))
  const flaggedNames = new Set(rejected.map((r) => r.quote.slice(0, 24)))

  return (
    <View style={styles.root}>
      <Text style={styles.question}>{question}</Text>

      {/* ◉ EJ BELAGT — the ring holds and the middle stays completely empty:
        * the material exists, the hit does not, and "Träff hittar aldrig på
        * en kärna" (identity §03).
        *
        * Only for an actual refusal. An `error` tone is something genuinely
        * broken — network, session, model — not a statement about the corpus,
        * so it keeps the warning treatment rather than borrowing a status the
        * product has not earned the right to report. */}
      <View style={styles.iconWrap}>
        {isError ? (
          <>
            <Animated.View style={[styles.ring, styles.ringOuter, { borderColor: tint }, ringStyle]} />
            <View style={[styles.ring, styles.ringInner, { borderColor: tint }]} />
            <View style={[styles.iconCore, { backgroundColor: `${tint}1F`, borderColor: `${tint}6B` }]}>
              <WarningGlyph color={tint} />
            </View>
          </>
        ) : (
          <StatusMark state="ejbelagt" size={96} />
        )}
      </View>

      {!isError && (
        <View style={styles.statusRow}>
          <StatusChip state="ejbelagt" />
        </View>
      )}

      <Text style={[styles.title, { color: tint }]}>{copy.title}</Text>
      <Text style={styles.body}>{copy.body}</Text>
      {copy.next && <Text style={styles.next}>{copy.next}</Text>}

      {bars.length > 0 && (
        <View style={styles.panel}>
          <Text style={styles.panelLabel}>HÖGEN GENOMSÖKTES ÄNDÅ</Text>
          <View style={{ gap: space.sm, marginTop: space.md }}>
            {bars.map((hit) => {
              const flagged = flaggedNames.has(hit.text.slice(0, 24))
              return (
                <View key={hit.chunk_id} style={styles.barRow}>
                  <View style={styles.barTrack}>
                    <View
                      style={[
                        styles.barFill,
                        {
                          width: `${Math.max(6, (hit.confidence / maxConfidence) * 100)}%`,
                          backgroundColor: flagged ? 'rgba(229,180,92,0.55)' : 'rgba(255,255,255,0.14)',
                        },
                      ]}
                    />
                  </View>
                  <Text
                    style={[styles.barLabel, flagged && { color: 'rgba(229,180,92,0.85)' }]}
                    numberOfLines={1}
                  >
                    {hit.document_name}
                  </Text>
                </View>
              )
            })}
          </View>
          {rejected.length > 0 && (
            <Text style={styles.panelNote}>{rejectCopy(rejected[0]!.reason)}</Text>
          )}
        </View>
      )}

      {suspected && (
        <Pressable
          onPress={onOpenSuspected}
          style={({ pressed }) => [styles.escapeHatch, pressed && { opacity: 0.75 }]}
        >
          <EyeIcon size={15} color={color.refusal} strokeWidth={1.8} />
          <Text style={styles.escapeHatchLabel}>Öppna sidan {suspected.page} ändå</Text>
        </Pressable>
      )}

      <Text style={styles.promise}>{GROUNDING_PROMISE.toUpperCase()}</Text>
    </View>
  )
}

function WarningGlyph({ color: c }: { color: string }) {
  return <Text style={{ color: c, fontFamily: font.serif, fontSize: 26, lineHeight: 26 }}>!</Text>
}

const styles = StyleSheet.create({
  root: { paddingHorizontal: space.xxl, paddingTop: space.md, paddingBottom: space.xxxl },
  question: { fontFamily: font.sans, fontSize: 13, lineHeight: 18, color: color.ink50 },
  iconWrap: { alignSelf: 'center', width: 118, height: 118, alignItems: 'center', justifyContent: 'center', marginTop: space.xl },
  ring: { position: 'absolute', borderRadius: 999, borderWidth: 1 },
  ringOuter: { width: 118, height: 118 },
  ringInner: { width: 86, height: 86, opacity: 0.4 },
  iconCore: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  statusRow: { alignItems: 'center', marginTop: space.lg },
  title: {
    fontFamily: font.serif,
    fontSize: 25,
    textAlign: 'center',
    marginTop: space.xl,
    letterSpacing: -0.2,
  },
  body: {
    fontFamily: font.sans,
    fontSize: 15,
    lineHeight: 22,
    color: color.ink65,
    textAlign: 'center',
    marginTop: space.md,
  },
  next: {
    fontFamily: font.sans,
    fontSize: 13.5,
    lineHeight: 19,
    color: color.ink38,
    textAlign: 'center',
    marginTop: space.sm,
  },
  panel: {
    marginTop: space.xxl,
    borderRadius: radius.lg,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    padding: space.lg,
  },
  panelLabel: { fontFamily: font.monoBold, fontSize: 9.5, letterSpacing: 1, color: color.ink38 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  barTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.07)', overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 3 },
  barLabel: { fontFamily: font.mono, fontSize: 10, color: color.ink38, width: 96, textAlign: 'right' },
  panelNote: { fontFamily: font.sans, fontSize: 13, lineHeight: 18, color: color.ink50, marginTop: space.md },
  escapeHatch: {
    marginTop: space.lg,
    height: 46,
    borderRadius: radius.md,
    backgroundColor: color.refusalTint,
    borderWidth: 1,
    borderColor: color.refusalBorder,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  escapeHatchLabel: { fontFamily: font.sansSemibold, fontSize: 12.5, color: color.refusal },
  promise: {
    fontFamily: font.monoBold,
    fontSize: 10,
    letterSpacing: 1.2,
    color: color.ink25,
    textAlign: 'center',
    marginTop: space.xl,
  },
})
