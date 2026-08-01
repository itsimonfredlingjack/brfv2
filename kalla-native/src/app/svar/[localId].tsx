import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useRef, useState } from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Animated from 'react-native-reanimated'

import type { Citation } from '../../api/types'
import { AnswerCard } from '../../components/AnswerCard'
import { KallaSheet } from '../../components/KallaSheet'
import type { KallaTarget } from '../../components/KallaSheet'
import { ChevronLeft } from '../../components/icons'
import { LivingIndex } from '../../components/LivingIndex'
import { Notice } from '../../components/Notice'
import { RefusalScreen } from '../../components/RefusalScreen'
import type { SuspectedSource } from '../../components/RefusalScreen'
import { VisaOverlay } from '../../components/VisaOverlay'
import { getEntry } from '../../state/journal'
import type { JournalEntry } from '../../state/journal'
import { topHitsByDocument, useAsk } from '../../state/useAsk'
import { useHeroFlight } from '../../state/useHeroFlight'
import { useUiModeStack } from '../../state/uiMode'
import { useActiveBrf } from '../../state/session'
import { color, font, space } from '../../theme/tokens'

const REVEAL_STAGGER_MS = 240
const REVEAL_SETTLE_MS = 450

export default function SvarScreen() {
  const params = useLocalSearchParams<{ localId: string; q?: string }>()
  const router = useRouter()
  const brfId = useActiveBrf()
  const isFresh = typeof params.q === 'string' && params.q.length > 0

  return isFresh ? (
    <FreshAsk brfId={brfId} question={params.q!} onBack={() => router.back()} />
  ) : (
    <Historical brfId={brfId} localId={params.localId} onBack={() => router.back()} />
  )
}

function Historical({ brfId, localId, onBack }: { brfId: string; localId: string; onBack: () => void }) {
  const [entry, setEntry] = useState<JournalEntry | null | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    getEntry(brfId, localId)
      .then((found) => !cancelled && setEntry(found ?? null))
      .catch(() => !cancelled && setEntry(null))
    return () => {
      cancelled = true
    }
  }, [brfId, localId])

  if (entry === undefined) {
    return (
      <SafeAreaView style={styles.root}>
        <BackLink onPress={onBack} />
      </SafeAreaView>
    )
  }

  if (entry === null) {
    return (
      <SafeAreaView style={styles.root}>
        <BackLink onPress={onBack} />
        <View style={{ paddingHorizontal: space.xxl, marginTop: space.xl }}>
          <Notice tone="refusal" title="Svaret finns inte kvar">
            Svaret har tagits bort — antingen av retentionsgränsen på 30 dagar eller när svarshistoriken rensades.
          </Notice>
        </View>
      </SafeAreaView>
    )
  }

  return <ResultShell brfId={brfId} entry={entry} onBack={onBack} />
}

function FreshAsk({ brfId, question, onBack }: { brfId: string; question: string; onBack: () => void }) {
  const ask = useAsk(brfId, question)
  const [revealed, setRevealed] = useState<ReturnType<typeof topHitsByDocument>>([])
  const [settled, setSettled] = useState(false)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    if (ask.step !== 'done' || !ask.entry) return
    const targets = topHitsByDocument(ask.entry.retrieval)
    timers.current.forEach(clearTimeout)
    timers.current = []
    targets.forEach((_, i) => {
      timers.current.push(
        setTimeout(() => setRevealed((prev) => targets.slice(0, i + 1)), i * REVEAL_STAGGER_MS),
      )
    })
    timers.current.push(
      setTimeout(() => setSettled(true), targets.length * REVEAL_STAGGER_MS + REVEAL_SETTLE_MS),
    )
    return () => timers.current.forEach(clearTimeout)
  }, [ask.step, ask.entry])

  if (ask.step === 'failed') {
    return (
      <SafeAreaView style={styles.root}>
        <BackLink onPress={onBack} />
        <View style={{ paddingHorizontal: space.xxl, marginTop: space.xl, gap: space.lg }}>
          <Notice tone="error" title="Frågan gick inte att ställa">
            {ask.error ?? 'Okänt fel.'}
          </Notice>
          <Pressable onPress={ask.retry} style={styles.retryBtn}>
            <Text style={styles.retryLabel}>Försök igen</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  }

  if (ask.step === 'asking' || !settled) {
    return (
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        <LivingIndex
          question={question}
          stage={ask.stage}
          documentCount={ask.documentCount}
          revealed={revealed}
          canSkip={ask.step === 'done'}
          onSkip={() => setSettled(true)}
        />
      </SafeAreaView>
    )
  }

  return <ResultShell brfId={brfId} entry={ask.entry!} onBack={onBack} />
}

function BackLink({ onPress }: { onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={styles.backLink}>
      <ChevronLeft />
      <Text style={styles.backLabel}>Högen</Text>
    </Pressable>
  )
}

function ResultShell({ brfId, entry, onBack }: { brfId: string; entry: JournalEntry; onBack: () => void }) {
  const hero = useHeroFlight()
  const { mode, openKalla, openVisa, closeVisa, closeKalla } = useUiModeStack()
  const [target, setTarget] = useState<KallaTarget | null>(null)
  const primaryRef = useRef<View>(null)

  /* Clear the flight whenever the source layer is left, by any route. Doing
   * it only in KallaSheet's onClose missed system Back — which closes Källa
   * through the BackHandler in useUiModeStack — leaving a stale captured
   * source behind, so the next open skipped its flight and left the passage
   * hidden. */
  const heroReset = hero.reset
  useEffect(() => {
    if (mode === 'answer') heroReset()
  }, [mode, heroReset])

  const openCitation = (citation: Citation, index: number) => {
    if (index === 0) hero.captureSource(primaryRef.current)
    setTarget({ documentId: citation.document_id, documentName: citation.document_name, page: citation.page, citation })
    openKalla()
  }

  const suspected: SuspectedSource | null = (() => {
    if (!entry.refusal || entry.rejected.length === 0) return null
    const rejected = entry.rejected[0]!
    const hit = entry.retrieval.find((h) => h.chunk_id === rejected.chunk_id)
    if (!hit) return null
    return { documentName: hit.document_name, documentId: hit.document_id, page: hit.page }
  })()

  const openSuspected = () => {
    if (!suspected) return
    setTarget({ documentId: suspected.documentId, documentName: suspected.documentName, page: suspected.page, citation: null })
    openKalla()
  }

  return (
    <View style={{ flex: 1, backgroundColor: color.bg }}>
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        <BackLink onPress={onBack} />
        <ScrollView contentContainerStyle={{ paddingHorizontal: space.xxl, paddingBottom: space.xxxl }}>
          {entry.refusal ? (
            <RefusalScreen
              question={entry.question}
              reason={entry.refusalReason}
              retrieval={entry.retrieval}
              rejected={entry.rejected}
              suspected={suspected}
              onOpenSuspected={openSuspected}
            />
          ) : (
            <>
              <Text style={styles.question}>{entry.question}</Text>
              <AnswerCard
                answer={entry.answer}
                warning={entry.warning}
                citations={entry.citations}
                provider={entry.provider}
                model={entry.model}
                createdAt={entry.createdAt}
                primaryRef={primaryRef}
                onOpenCitation={openCitation}
                onOpenVisa={() => {
                  if (entry.citations[0]) {
                    setTarget({
                      documentId: entry.citations[0].document_id,
                      documentName: entry.citations[0].document_name,
                      page: entry.citations[0].page,
                      citation: entry.citations[0],
                    })
                    openVisa()
                  }
                }}
              />
            </>
          )}
        </ScrollView>
      </SafeAreaView>

      {(mode === 'kalla' || mode === 'visa') && target && (
        <View style={StyleSheet.absoluteFill}>
          <KallaSheet
            brfId={brfId}
            target={target}
            hero={hero}
            onClose={() => {
              hero.reset()
              closeKalla()
            }}
            onOpenVisa={openVisa}
          />
        </View>
      )}

      {mode === 'visa' && target?.citation && (
        <View style={StyleSheet.absoluteFill}>
          <VisaOverlay brfId={brfId} documentName={target.documentName} page={target.page} citation={target.citation} onExit={closeVisa} />
        </View>
      )}

      {(mode === 'kalla' || mode === 'visa') && (
        <Animated.View pointerEvents="none" style={hero.overlayStyle}>
          <Animated.View style={[StyleSheet.absoluteFill, styles.flightCard, hero.cardStyle]} />
          <Animated.View style={[StyleSheet.absoluteFill, styles.flightHighlight, hero.highlightStyle]} />
        </Animated.View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: space.lg, paddingTop: space.sm, paddingBottom: space.xs },
  backLabel: { fontFamily: font.sansMedium, fontSize: 13, color: color.ink50 },
  question: { fontFamily: font.sans, fontSize: 13, lineHeight: 18, color: color.ink50, marginTop: space.sm },
  retryBtn: { height: 46, borderRadius: 14, backgroundColor: color.surfaceStrong, alignItems: 'center', justifyContent: 'center' },
  retryLabel: { fontFamily: font.sansSemibold, fontSize: 13.5, color: color.ink },
  flightCard: {
    borderRadius: 15,
    backgroundColor: '#12161C',
    borderWidth: 1,
    borderColor: color.groundedBorder,
    shadowColor: '#000',
    shadowOpacity: 0.6,
    shadowRadius: 24,
  },
  flightHighlight: {
    borderRadius: 3,
    backgroundColor: color.hlFill,
    borderWidth: 1.5,
    borderColor: color.hlEdge,
  },
})
