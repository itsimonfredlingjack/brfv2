import Constants from 'expo-constants'
import { useRouter } from 'expo-router'
import { useState } from 'react'
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import type { Health } from '@/api/types'
import { Wordmark } from '@/components/BrandMark'
import { ChevronLeft } from '@/components/icons'
import { clearJournal } from '@/state/journal'
import { useActiveBrf, useSession } from '@/state/session'
import { color, font, radius, space } from '@/theme/tokens'

/* `runtime_label` is an optional deployment env var and the model name is
 * empty for providers that have no model identity, so composing these
 * unconditionally rendered a bare "()". Same fallbacks the PWA's Konto uses. */
function modelLabel(llm: Health['llm'] | undefined): string {
  if (!llm) return '—'
  const name = llm.display_name || llm.model || (llm.ready ? 'Konfigurerad' : 'Ingen modell konfigurerad')
  return llm.runtime_label ? `${name} (${llm.runtime_label})` : name
}

export default function KontoScreen() {
  const router = useRouter()
  const { user, active, memberships, health, logout } = useSession()
  const brfId = useActiveBrf()
  const [busy, setBusy] = useState(false)

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <Pressable onPress={() => router.back()} style={styles.backLink}>
        <ChevronLeft />
        <Text style={styles.backLabel}>Tillbaka</Text>
      </Pressable>

      <View style={styles.content}>
        <Text style={styles.title}>Konto</Text>

        <Row label="ANVÄNDARE" value={user?.name || user?.email || '—'} />
        <Row label="FÖRENING" value={active?.name ?? '—'} />
        <Row label="ROLL" value={active?.role === 'admin' ? 'Administratör' : 'Styrelseledamot'} />
        <Row label="MODELL" value={modelLabel(health?.llm)} />

        {memberships.length > 1 && (
          <Pressable onPress={() => router.push('/valj')} style={styles.action}>
            <Text style={styles.actionLabel}>Byt förening</Text>
          </Pressable>
        )}

        <Pressable
          onPress={() =>
            Alert.alert('Rensa svarshistorik', 'Alla sparade svar för den här föreningen tas bort från enheten.', [
              { text: 'Avbryt', style: 'cancel' },
              { text: 'Rensa', style: 'destructive', onPress: () => void clearJournal(brfId) },
            ])
          }
          style={styles.action}
        >
          <Text style={styles.actionLabel}>Rensa svarshistorik</Text>
        </Pressable>

        <Pressable
          disabled={busy}
          onPress={() => {
            setBusy(true)
            void logout()
          }}
          style={[styles.action, styles.logout]}
        >
          <Text style={styles.logoutLabel}>Logga ut</Text>
        </Pressable>

        {/* The lockup at rest, monochrome and dimmed — a signature, not a
          * status. §01: the brand mark never wears a state colour. */}
        <View style={styles.identity}>
          <Wordmark size={20} tint={color.ink38} role="none" />
          <Text style={styles.identityMeta}>VERSION {Constants.expoConfig?.version ?? '—'}</Text>
        </View>
      </View>
    </SafeAreaView>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: space.lg, paddingTop: space.sm },
  backLabel: { fontFamily: font.sansMedium, fontSize: 13, color: color.ink50 },
  content: { paddingHorizontal: space.xxl, paddingTop: space.xl },
  title: { fontFamily: font.serif, fontSize: 28, color: color.ink, marginBottom: space.xl },
  row: { paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: color.hairline },
  rowLabel: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 1.2, color: color.ink38 },
  rowValue: { fontFamily: font.sansMedium, fontSize: 15, color: color.ink, marginTop: 4 },
  action: {
    marginTop: space.lg,
    height: 48,
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionLabel: { fontFamily: font.sansMedium, fontSize: 14, color: color.ink },
  logout: { backgroundColor: color.errorTint, borderColor: color.errorBorder },
  logoutLabel: { fontFamily: font.sansSemibold, fontSize: 14, color: color.error },
  identity: { marginTop: space.xxxl, alignItems: 'center', gap: space.sm },
  identityMeta: { fontFamily: font.mono, fontSize: 9.5, letterSpacing: 1.2, color: color.ink25 },
})
