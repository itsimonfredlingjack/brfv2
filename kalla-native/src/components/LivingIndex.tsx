import { useEffect } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Animated, {
  Easing,
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'

import type { RetrievalHit } from '../api/types'
import type { AskStage } from '../state/useAsk'
import { color, font, radius, space } from '../theme/tokens'
import { StatusMark } from './StatusMark'

const ROWS = 4

/**
 * "Levande index" — the searching state. Reveals document names, locations
 * and relevance progressively (3a §3a: "reveal document names, locations
 * and relevance progressively rather than showing permanent labels").
 *
 * Honesty constraint: the backend answers in one synchronous call, so there
 * is no real per-document search progress to stream. This never fabricates
 * interim hits — while `revealed` is empty every row is a generic pending
 * skeleton; once the real answer has returned, `revealed` fills with actual
 * retrieval hits and each row morphs in with a staggered lift, so the
 * *feeling* of discovery is genuine even though the reveal itself happens
 * after the fact, not during it.
 */
export function LivingIndex({
  question,
  stage,
  documentCount,
  revealed,
  canSkip,
  onSkip,
}: {
  question: string
  stage: AskStage
  documentCount: number | null
  revealed: RetrievalHit[]
  canSkip: boolean
  onSkip: () => void
}) {
  const sweep = useSharedValue(0)

  useEffect(() => {
    sweep.value = withRepeat(withTiming(1, { duration: 2600, easing: Easing.inOut(Easing.ease) }), -1, false)
  }, [sweep])

  const sweepStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: -260 + sweep.value * 520 }],
    opacity: revealed.length > 0 ? 0 : 0.5,
  }))

  const foundLabel =
    revealed.length === 0 ? 'SÖKER…' : `${revealed.length} ${revealed.length === 1 ? 'PASSAGE FUNNEN' : 'PASSAGER FUNNA'}`

  return (
    <Pressable style={styles.root} onPress={canSkip ? onSkip : undefined} disabled={!canSkip}>
      <View style={styles.head}>
        {/* ◉ SÖKER — broken ring, diffuse glow, and deliberately no core:
          * the middle stays empty all the way up to the evidence (identity
          * §03). The mono word rides alongside it so the state never depends
          * on colour or motion alone. */}
        <View style={styles.pulseRow}>
          <StatusMark state="soker" size={16} />
          <Text style={styles.pulseLabel}>
            SÖKER · LÄSER {documentCount ?? '…'} {documentCount === 1 ? 'DOKUMENT' : 'DOKUMENT'}
          </Text>
        </View>
        <Text style={styles.question}>{question}</Text>
      </View>

      <View style={styles.list}>
        {Array.from({ length: ROWS }).map((_, i) => {
          const hit = revealed[i]
          if (hit) return <HitRow key={hit.chunk_id} hit={hit} rank={i} />
          return <PendingRow key={`pending-${i}`} queued={i > revealed.length} />
        })}
        <Animated.View style={[styles.sweepBeam, sweepStyle]} pointerEvents="none" />
      </View>

      <View style={styles.footer}>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${Math.min(100, 15 + revealed.length * 22)}%` }]} />
        </View>
        <View style={styles.footerRow}>
          <Text style={styles.footerMeta}>{foundLabel}</Text>
          <Text style={styles.footerMeta}>{stage === 'retrieving' ? 'SÖKER' : 'FORMULERAR'}</Text>
        </View>
        <Text style={styles.footerCopy}>
          {stage === 'retrieving' ? `Söker i ${documentCount ?? 'föreningens'} dokument…` : 'Formulerar svar ur de funna passagerna. Inget utan belägg kommer med.'}
        </Text>
      </View>
    </Pressable>
  )
}

function HitRow({ hit, rank }: { hit: RetrievalHit; rank: number }) {
  const glow = rank === 0
  return (
    <Animated.View
      entering={FadeInDown.duration(320).easing(Easing.bezier(0.2, 0, 0, 1))}
      style={[styles.row, glow ? styles.rowGlow : styles.rowDim]}
    >
      <View style={[styles.rowIcon, glow ? styles.rowIconGlow : styles.rowIconDim]} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {hit.document_name}
        </Text>
        <Text style={styles.rowLoc}>SIDA {hit.page}</Text>
      </View>
      <Text style={[styles.rowScore, glow && { color: color.grounded }]}>{hit.confidence.toFixed(2)}</Text>
    </Animated.View>
  )
}

function PendingRow({ queued }: { queued: boolean }) {
  return (
    <View style={[styles.row, styles.rowPending, queued && { opacity: 0.5 }]}>
      <View style={styles.rowIconPending} />
      <View style={{ flex: 1, gap: 8 }}>
        <View style={styles.skeletonBar} />
        {queued && <Text style={styles.rowQueued}>I KÖ</Text>}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  head: { paddingHorizontal: space.xxl, paddingTop: space.xxl },
  pulseRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  pulseLabel: { fontFamily: font.monoBold, fontSize: 10, letterSpacing: 1.6, color: color.light },
  question: {
    fontFamily: font.serif,
    fontSize: 24,
    lineHeight: 30,
    color: color.ink,
    marginTop: space.md,
    letterSpacing: -0.2,
  },
  list: { flex: 1, marginTop: space.xl, paddingHorizontal: space.xxl, gap: space.md, overflow: 'hidden' },
  sweepBeam: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 120,
    backgroundColor: color.lightGlow,
  },
  row: {
    height: 58,
    borderRadius: radius.sm,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.md,
  },
  rowGlow: {
    backgroundColor: color.groundedTint,
    borderColor: color.groundedBorder,
  },
  rowDim: {
    backgroundColor: 'rgba(79,199,156,0.06)',
    borderColor: 'rgba(79,199,156,0.2)',
  },
  rowPending: {
    backgroundColor: color.surface,
    borderColor: color.hairline,
  },
  rowIcon: { width: 15, height: 15, borderRadius: 8 },
  rowIconGlow: { backgroundColor: color.grounded },
  rowIconDim: { backgroundColor: 'rgba(79,199,156,0.5)' },
  rowIconPending: { width: 15, height: 15, borderRadius: 8, borderWidth: 1.6, borderColor: color.ink25 },
  rowTitle: { fontFamily: font.sansSemibold, fontSize: 14, color: color.ink },
  rowLoc: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.8, color: 'rgba(79,199,156,0.75)', marginTop: 4 },
  rowScore: { fontFamily: font.monoBold, fontSize: 14, color: color.ink38 },
  rowQueued: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 1, color: color.ink25 },
  skeletonBar: { height: 8, width: '55%', borderRadius: 2, backgroundColor: color.surfaceStrong },
  footer: { paddingHorizontal: space.xxl, paddingBottom: space.xxl },
  progressTrack: { height: 2, borderRadius: 1, backgroundColor: color.hairline, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: color.light },
  footerRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: space.md },
  footerMeta: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.8, color: color.ink38 },
  footerCopy: {
    fontFamily: font.sans,
    fontSize: 13,
    lineHeight: 18,
    color: color.ink38,
    textAlign: 'center',
    marginTop: space.lg,
  },
})
