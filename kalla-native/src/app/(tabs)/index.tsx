import { useFocusEffect, useRouter } from 'expo-router'
import { useCallback, useRef, useState } from 'react'
import {
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { Wordmark } from '@/components/BrandMark'
import { CorpusStack } from '@/components/CorpusStack'
import { SendIcon } from '@/components/icons'
import { StatusMark } from '@/components/StatusMark'
import { formatMoment } from '@/lib/format'
import { refusalCopy } from '@/lib/refusals'
import { newEntryId, listEntries } from '@/state/journal'
import type { JournalEntry } from '@/state/journal'
import { takePendingQuestion } from '@/state/pending'
import { useActiveBrf, useSession } from '@/state/session'
import { useOnline } from '@/state/useOnline'
import { color, font, radius, space, touchTarget } from '@/theme/tokens'

export default function FragaScreen() {
  const router = useRouter()
  const { user, active } = useSession()
  const brfId = useActiveBrf()
  const online = useOnline()

  const [question, setQuestion] = useState(() => takePendingQuestion(user?.id ?? ''))
  const [entries, setEntries] = useState<JournalEntry[] | null>(null)
  const inputRef = useRef<TextInput>(null)

  // On focus, not on mount: this tab stays mounted while Svar is pushed over
  // it, so a mount-only read left a just-answered question missing from
  // SENAST until the app was restarted.
  useFocusEffect(
    useCallback(() => {
      let cancelled = false
      listEntries(brfId)
        .then((list) => !cancelled && setEntries(list))
        .catch(() => !cancelled && setEntries([]))
      return () => {
        cancelled = true
      }
    }, [brfId]),
  )

  const canSend = question.trim().length > 0 && online

  function ask() {
    const text = question.trim()
    if (!text || !canSend) return
    setQuestion('')
    inputRef.current?.blur()
    router.push({ pathname: '/svar/[localId]', params: { localId: newEntryId(), q: text } })
  }

  const initials = (active?.name ?? user?.name ?? user?.email ?? '?').slice(0, 2).toUpperCase()

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      {/* `behavior="padding"` on Android too: once the app is edge-to-edge
       * (Android 15+) `adjustResize` no longer shrinks the window, so without
       * this the composer — the app's primary control — sits under the IME.
       * KeyboardAvoidingView pads only by the measured overlap, so the tab bar
       * below this screen is already accounted for. */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        {/* ◉ Träff as the brand mark: complete, monochrome, saying who is
          * speaking rather than what is true (identity §01 A). */}
        <View style={styles.brandRow}>
          <Wordmark size={17} />
        </View>

        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.tenantName} numberOfLines={1}>
              {active?.name ?? '—'}
            </Text>
            <Text style={styles.tenantRole}>{active?.role === 'admin' ? 'ADMINISTRATÖR' : 'STYRELSELEDAMOT'}</Text>
          </View>
          <Pressable onPress={() => router.push('/konto')} style={styles.avatar}>
            <Text style={styles.avatarText}>{initials}</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={{ paddingBottom: space.xl }} keyboardShouldPersistTaps="handled">
          <CorpusStack />

          <View style={styles.hero}>
            {/* ◉ VILA — the resting status mark: a quiet empty ring, nothing
              * asked so nothing to report. Identity §03: "Ingen fråga ställd,
              * alltså ingen träff att visa. 30 % opacitet, ingen rörelse." */}
            <View style={styles.restRow}>
              <StatusMark state="vila" size={16} />
              <Text style={styles.restLabel}>INGEN FRÅGA STÄLLD</Text>
            </View>
            <Text style={styles.headline}>Allt föreningen{'\n'}har skrivit ner.</Text>
            <Text style={styles.sub}>Fråga rakt in i högen. Svaret öppnas på den sida det kom från.</Text>
          </View>

          {!online && (
            <View style={styles.offlineStrip}>
              <Text style={styles.offlineText}>Du är offline. Frågor kräver uppkoppling.</Text>
            </View>
          )}

          {entries && entries.length > 0 && (
            <View style={styles.recent}>
              <Text style={styles.recentLabel}>SENAST</Text>
              <View style={{ gap: space.sm, marginTop: space.sm }}>
                {entries.slice(0, 6).map((entry) => (
                  <Pressable
                    key={entry.id}
                    onPress={() => router.push({ pathname: '/svar/[localId]', params: { localId: entry.id } })}
                    style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
                  >
                    <View style={[styles.rowBar, { backgroundColor: entry.refusal ? color.refusal : color.grounded }]} />
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text numberOfLines={1} style={styles.rowTitle}>
                        {entry.question}
                      </Text>
                      <Text style={styles.rowMeta}>
                        {entry.refusal
                          ? refusalCopy(entry.refusalReason).title.toUpperCase()
                          : `${entry.citations.length} ${entry.citations.length === 1 ? 'KÄLLA' : 'KÄLLOR'}`}
                        {' · '}
                        {formatMoment(entry.createdAt)}
                      </Text>
                    </View>
                  </Pressable>
                ))}
              </View>
            </View>
          )}

          {entries && entries.length === 0 && (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>Inga frågor ännu</Text>
              <Text style={styles.emptyBody}>
                Fråga om stadgar, protokoll, avtal eller årsredovisning — svaret kommer med källa.
              </Text>
            </View>
          )}
        </ScrollView>

        <View style={styles.composerWrap}>
          <View style={styles.composerShell}>
            <TextInput
              ref={inputRef}
              style={styles.composerInput}
              placeholder="Fråga om föreningens dokument…"
              placeholderTextColor={color.ink38}
              value={question}
              onChangeText={setQuestion}
              multiline
              editable={online}
              onSubmitEditing={ask}
            />
            <Pressable
              onPress={ask}
              disabled={!canSend}
              style={[styles.sendBtn, !canSend && styles.sendBtnDisabled]}
              accessibilityLabel="Skicka frågan"
            >
              <SendIcon />
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  brandRow: { paddingHorizontal: space.xxl, paddingTop: space.md },
  header: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.xxl, paddingTop: space.sm, paddingBottom: space.sm },
  tenantName: { fontFamily: font.sansSemibold, fontSize: 15.5, color: color.ink, letterSpacing: -0.2 },
  tenantRole: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1, color: color.ink38, marginTop: 4 },
  avatar: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: touchTarget / 2,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.lightGlow,
    borderWidth: 1,
    borderColor: 'rgba(207,224,255,0.24)',
  },
  avatarText: { fontFamily: font.sansSemibold, fontSize: 12, color: color.light },
  hero: { paddingHorizontal: space.xxl, marginTop: space.lg },
  restRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.md },
  restLabel: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1.4, color: color.ink38 },
  headline: { fontFamily: font.serif, fontSize: 30, lineHeight: 34, color: color.ink, letterSpacing: -0.3 },
  sub: { fontFamily: font.sans, fontSize: 13.5, lineHeight: 19, color: color.ink50, marginTop: space.sm, maxWidth: 320 },
  offlineStrip: { marginHorizontal: space.xxl, marginTop: space.lg, padding: space.md, borderRadius: radius.md, backgroundColor: color.errorTint },
  offlineText: { fontFamily: font.sansMedium, fontSize: 12.5, color: color.error },
  recent: { paddingHorizontal: space.xxl, marginTop: space.xxl },
  recentLabel: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1.4, color: color.ink38 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md, borderRadius: radius.md, backgroundColor: color.surface, borderWidth: 1, borderColor: color.hairline },
  rowPressed: { backgroundColor: color.surfacePress },
  rowBar: { width: 5, height: 26, borderRadius: 3 },
  rowTitle: { fontFamily: font.sansMedium, fontSize: 13.5, color: color.ink },
  rowMeta: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.6, color: color.ink38, marginTop: 4 },
  empty: { paddingHorizontal: space.xxl, marginTop: space.xxl },
  emptyTitle: { fontFamily: font.sansSemibold, fontSize: 14, color: color.ink },
  emptyBody: { fontFamily: font.sans, fontSize: 13, lineHeight: 18, color: color.ink38, marginTop: 4 },
  composerWrap: { paddingHorizontal: space.lg, paddingBottom: space.md },
  composerShell: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.sm,
    padding: space.xs,
    paddingLeft: space.lg,
    borderRadius: 27,
    backgroundColor: color.surfaceStrong,
    borderWidth: 1,
    borderColor: color.hairlineStrong,
  },
  composerInput: {
    flex: 1,
    fontFamily: font.sans,
    fontSize: 15,
    color: color.ink,
    maxHeight: 120,
    paddingVertical: space.sm,
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.action,
  },
  sendBtnDisabled: { opacity: 0.35 },
})
