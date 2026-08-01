import { forwardRef } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Animated from 'react-native-reanimated'

import type { Citation } from '../api/types'
import { color, font, radius, space } from '../theme/tokens'
import { CheckIcon } from './icons'

/**
 * One verified source. Never signalled by colour alone: a check glyph for a
 * verified citation, a dashed edge plus an explicit label when the
 * highlight is approximate (OCR word boxes on a scanned page). The first
 * citation renders "primary" (thumbnail, ORDAGRANT VERIFIERAT footer,
 * green rule) matching 3a's Svar screen; the rest render as plainer rows.
 *
 * Wrapped in Animated.View and forwardRef so the hero transition
 * (useHeroTransition) can measure this exact node before it flies to the
 * highlighted passage in Källa.
 */
export const CitationCard = forwardRef<View, { citation: Citation; primary: boolean; onOpen: () => void }>(
  ({ citation, primary, onOpen }, ref) => {
    if (!primary) {
      return (
        <Pressable
          onPress={onOpen}
          style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={`Källa: ${citation.document_name}, sida ${citation.page}. Öppna sidan med markerad passage.`}
        >
          <View style={styles.secondaryRule} />
          <View style={{ flex: 1 }}>
            <Text style={styles.secondaryDoc}>
              {citation.document_name} · sida {citation.page}
            </Text>
            <Text style={styles.quote} numberOfLines={3}>
              &ldquo;{citation.quote}&rdquo;
            </Text>
          </View>
        </Pressable>
      )
    }

    return (
      <Animated.View ref={ref} collapsable={false}>
        <Pressable
          onPress={onOpen}
          style={({ pressed }) => [styles.primary, pressed && styles.primaryPressed]}
          accessibilityRole="button"
          accessibilityLabel={`Källa: ${citation.document_name}, sida ${citation.page}. Öppna sidan med markerad passage.`}
        >
          <View style={styles.primaryRule} />
          <View style={styles.primaryRow}>
            <View style={styles.thumb}>
              <View style={styles.thumbLineTitle} />
              <View style={styles.thumbLine} />
              <View style={styles.thumbLine} />
              <View style={[styles.thumbLine, styles.thumbLineHl]} />
              <View style={styles.thumbLine} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.primaryDoc} numberOfLines={1}>
                {citation.document_name} · sida {citation.page}
              </Text>
              <Text style={styles.quote} numberOfLines={4}>
                &ldquo;{citation.quote}&rdquo;
              </Text>
            </View>
          </View>
          <View style={styles.primaryFooter}>
            {citation.approximate ? (
              <View style={styles.approxBadge}>
                <Text style={styles.approxLabel}>UNGEFÄRLIG MARKERING</Text>
              </View>
            ) : (
              <View style={styles.verifiedRow}>
                <CheckIcon size={11} strokeWidth={3.4} />
                <Text style={styles.verifiedLabel} numberOfLines={1}>
                  ORDAGRANT VERIFIERAT
                </Text>
              </View>
            )}
            <View style={{ flex: 1 }} />
            <Text style={styles.openLink}>Öppna sidan →</Text>
          </View>
        </Pressable>
      </Animated.View>
    )
  },
)
CitationCard.displayName = 'CitationCard'

const styles = StyleSheet.create({
  primary: {
    borderRadius: radius.lg,
    backgroundColor: 'rgba(255,255,255,0.045)',
    borderWidth: 1,
    borderColor: color.groundedBorder,
    padding: space.lg,
    overflow: 'hidden',
  },
  primaryPressed: { transform: [{ translateY: -1 }] },
  primaryRule: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, backgroundColor: color.grounded },
  primaryRow: { flexDirection: 'row', gap: space.md },
  thumb: {
    width: 48,
    height: 64,
    borderRadius: 2,
    backgroundColor: '#fff',
    padding: 5,
    gap: 4,
  },
  thumbLineTitle: { height: 2, width: '55%', backgroundColor: '#20242B', borderRadius: 1, marginBottom: 2 },
  thumbLine: { height: 2, backgroundColor: '#CBD0D7', borderRadius: 1 },
  thumbLineHl: { backgroundColor: color.hlEdge, height: 3 },
  primaryDoc: { fontFamily: font.sansSemibold, fontSize: 12.5, color: color.grounded },
  quote: { fontFamily: font.serifItalic, fontStyle: 'italic', fontSize: 14, lineHeight: 19, color: color.ink85, marginTop: space.xs },
  primaryFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: color.hairline,
  },
  /* The verification badge yields before the affordance does: at a large font
   * scale this row overflowed and clipped "Öppna sidan →" off the card. */
  verifiedRow: { flexShrink: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 6 },
  verifiedLabel: { flexShrink: 1, fontFamily: font.monoBold, fontSize: 9.5, letterSpacing: 1, color: 'rgba(79,199,156,0.85)' },
  approxBadge: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: color.hlEdge,
    paddingHorizontal: space.sm,
    paddingVertical: 3,
  },
  approxLabel: { fontFamily: font.monoBold, fontSize: 9, letterSpacing: 0.8, color: color.hlEdge },
  openLink: { flexShrink: 0, fontFamily: font.sansSemibold, fontSize: 12, color: color.action },
  secondary: {
    borderRadius: radius.lg,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: 'rgba(79,199,156,0.18)',
    padding: space.md,
    flexDirection: 'row',
    gap: space.md,
    overflow: 'hidden',
  },
  pressed: { backgroundColor: color.surfacePress },
  secondaryRule: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, backgroundColor: 'rgba(79,199,156,0.6)' },
  secondaryDoc: { fontFamily: font.sansSemibold, fontSize: 12.5, color: 'rgba(79,199,156,0.85)' },
})
