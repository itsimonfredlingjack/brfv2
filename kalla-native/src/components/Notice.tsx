import { StyleSheet, Text, View } from 'react-native'

import { color, font, radius, space } from '../theme/tokens'
import { AlertIcon, WarningIcon } from './icons'

export type NoticeTone = 'refusal' | 'error' | 'info'

const TONE = {
  refusal: { bg: color.refusalTint, border: color.refusalBorder, ink: color.refusal },
  error: { bg: color.errorTint, border: color.errorBorder, ink: color.error },
  info: { bg: color.surface, border: color.hairline, ink: color.ink65 },
} as const

/** A compact inline banner — offline strip, ask errors, small warnings.
 * Distinct from the full-screen Vägran state: this is for chrome-level
 * notices, not the product's considered refusal of a question. */
export function Notice({
  tone,
  title,
  children,
}: {
  tone: NoticeTone
  title: string
  children?: string
}) {
  const t = TONE[tone]
  return (
    <View style={[styles.root, { backgroundColor: t.bg, borderColor: t.border }]}>
      {tone !== 'info' && (
        <View style={styles.icon}>
          {tone === 'error' ? <AlertIcon color={t.ink} /> : <WarningIcon size={16} color={t.ink} strokeWidth={2} />}
        </View>
      )}
      <View style={styles.body}>
        <Text style={[styles.title, { color: t.ink }]}>{title}</Text>
        {children ? <Text style={styles.text}>{children}</Text> : null}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  root: {
    flexDirection: 'row',
    gap: space.md,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.lg,
    alignItems: 'flex-start',
  },
  icon: {
    paddingTop: 2,
  },
  body: {
    flex: 1,
    gap: 4,
  },
  title: {
    fontFamily: font.sansSemibold,
    fontSize: 13.5,
  },
  text: {
    fontFamily: font.sans,
    fontSize: 13,
    lineHeight: 18,
    color: color.ink65,
  },
})
