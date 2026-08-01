import * as Haptics from 'expo-haptics'
import { Pressable, Share, StyleSheet, Text, View } from 'react-native'

import type { Citation } from '../api/types'
import { formatMoment, formatProvenance } from '../lib/format'
import { color, font, space } from '../theme/tokens'
import { CitationCard } from './CitationCard'
import { ShareIcon } from './icons'
import { Notice } from './Notice'
import { StatusChip } from './StatusMark'

export function AnswerCard({
  answer,
  warning,
  citations,
  provider,
  model,
  createdAt,
  primaryRef,
  onOpenCitation,
  onOpenVisa,
}: {
  answer: string
  warning: string | null
  citations: Citation[]
  provider: string
  model: string
  createdAt: number
  primaryRef: React.Ref<View>
  onOpenCitation: (citation: Citation, index: number) => void
  onOpenVisa: () => void
}) {
  const primary = citations[0]

  return (
    <View>
      {/* ◉ BELAGT — the one state that draws a core, and it may draw it here
        * because this card only renders behind a verbatim-verified citation.
        * Identity §01: "En fylld kärna utan citat är en lögn i formspråket." */}
      <View style={styles.badgeRow}>
        <StatusChip state="belagt" />
        <View style={styles.badgeRule} />
      </View>

      <Text style={styles.answer}>{answer}</Text>

      {warning && (
        <View style={{ marginTop: space.lg }}>
          <Notice tone="refusal" title="Osäkert underlag">
            {warning}
          </Notice>
        </View>
      )}

      {citations.length > 0 && (
        <>
          <View style={styles.labelRow}>
            <Text style={styles.label}>HÄMTAT UR HÖGEN</Text>
            <View style={styles.labelRule} />
          </View>
          <View style={{ gap: space.sm }}>
            {citations.map((citation, index) => (
              <CitationCard
                key={`${citation.chunk_id}-${index}`}
                ref={index === 0 ? primaryRef : undefined}
                citation={citation}
                primary={index === 0}
                onOpen={() => onOpenCitation(citation, index)}
              />
            ))}
          </View>
        </>
      )}

      <Text style={styles.meta}>
        {[formatProvenance(provider, model), formatMoment(createdAt)].filter(Boolean).join(' · ').toUpperCase()}
      </Text>

      {primary && (
        <View style={styles.actions}>
          <Pressable
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {})
              onOpenVisa()
            }}
            style={({ pressed }) => [styles.visaBtn, pressed && { backgroundColor: '#fff' }]}
          >
            <Text style={styles.visaLabel}>VISA FÖR NÅGON</Text>
          </Pressable>
          <Pressable
            onPress={() => {
              void Share.share({ message: `${answer}\n\n— ${primary.document_name}, sida ${primary.page}: "${primary.quote}"` })
            }}
            style={styles.shareBtn}
            accessibilityLabel="Dela svaret"
          >
            <ShareIcon />
          </Pressable>
        </View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  badgeRule: { flex: 1, height: 1, backgroundColor: color.groundedBorder },
  answer: {
    fontFamily: font.serif,
    fontSize: 22,
    lineHeight: 32,
    color: color.ink,
    marginTop: space.lg,
    letterSpacing: -0.1,
  },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginTop: space.xxl, marginBottom: space.md },
  label: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1.4, color: color.ink38 },
  labelRule: { flex: 1, height: 1, backgroundColor: color.hairline },
  meta: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 0.9, color: color.ink38, marginTop: space.xl },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.xl },
  visaBtn: {
    flex: 1,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#F4F5F7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  visaLabel: { fontFamily: font.monoBold, fontSize: 12, letterSpacing: 1.2, color: '#0B0D10' },
  shareBtn: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: color.surfaceStrong,
    borderWidth: 1,
    borderColor: color.hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
})
