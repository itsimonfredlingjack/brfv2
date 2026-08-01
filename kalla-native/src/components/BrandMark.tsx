import { StyleSheet, Text, View } from 'react-native'

import { CORE_OF_OUTER, coreSizeFor, lockup, lockupMarkSize, mark, ringWeightFor } from '../theme/brand'
import { color, font } from '../theme/tokens'

/**
 * ◉ · A · VARUMÄRKET — the brand mark (identity §01, §02).
 *
 * Always complete (ring *and* core) and always monochrome. This is the mark
 * as a name, so it never takes a state colour: the identity calls a green
 * logotype outside the product "ett löfte utan belägg" (§10 Missbruk).
 * Anything that reports a *result* is `StatusMark`, not this.
 *
 * Under 16 dp the gap stops reading, so the identity drops the ring and uses
 * the solid dot alone rather than letting the ring go hairline (§02).
 */
export function BrandMark({
  size = 18,
  tint = color.ink,
}: {
  size?: number
  tint?: string
}) {
  if (size < mark.minRingSize) {
    const dot = size * mark.dotOfOuter
    return (
      <View
        style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}
        importantForAccessibility="no-hide-descendants"
      >
        <View style={{ width: dot, height: dot, borderRadius: dot / 2, backgroundColor: tint }} />
      </View>
    )
  }

  const weight = ringWeightFor(size)
  const core = coreSizeFor(size)

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: weight,
        borderColor: tint,
        alignItems: 'center',
        justifyContent: 'center',
      }}
      importantForAccessibility="no-hide-descendants"
    >
      <View style={{ width: core, height: core, borderRadius: core / 2, backgroundColor: tint }} />
    </View>
  )
}

/**
 * The lockup (identity §05): ◉ before the name, set in Instrument Serif
 * Regular at −3,5 % tracking, with the gap equal to the core's diameter.
 *
 * The Ä is not decoration — §05 "Diakriten Ä": the name is Swedish and the
 * dots belong to it. They are never stripped, never replaced with "ae", and
 * never clipped by a tight line height, so this sets `lineHeight` generously
 * above the cap height rather than letting the platform default crop them.
 */
export function Wordmark({
  size = 20,
  tint = color.ink,
  role = 'header',
}: {
  size?: number
  tint?: string
  role?: 'header' | 'none'
}) {
  const markSize = lockupMarkSize(size)

  return (
    <View
      style={styles.lockup}
      accessible
      accessibilityRole={role === 'header' ? 'header' : undefined}
      accessibilityLabel="Träff"
    >
      <BrandMark size={markSize} tint={tint} />
      <View style={{ width: coreSizeFor(markSize) }} />
      <Text
        style={{
          fontFamily: font.serif,
          fontSize: size,
          lineHeight: size * 1.28,
          letterSpacing: size * lockup.tracking,
          color: tint,
        }}
      >
        Träff
      </Text>
    </View>
  )
}

/**
 * The stacked lockup for narrow columns (§05 "STAPLAD · TRÅNGT FORMAT").
 */
export function WordmarkStacked({ size = 40, tint = color.ink }: { size?: number; tint?: string }) {
  const markSize = lockupMarkSize(size)

  return (
    <View accessible accessibilityRole="header" accessibilityLabel="Träff">
      <BrandMark size={markSize} tint={tint} />
      <Text
        style={{
          fontFamily: font.serif,
          fontSize: size,
          lineHeight: size * 1.28,
          letterSpacing: size * lockup.tracking,
          color: tint,
          marginTop: markSize * CORE_OF_OUTER,
        }}
      >
        Träff
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  lockup: { flexDirection: 'row', alignItems: 'center' },
})
