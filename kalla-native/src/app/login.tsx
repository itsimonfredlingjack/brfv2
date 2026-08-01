import { useEffect, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { ApiError, OfflineError } from '@/api/client'
import { getApiBaseUrl, setApiBaseUrl } from '@/api/config'
import { Wordmark } from '@/components/BrandMark'
import { Notice } from '@/components/Notice'
import { useSession } from '@/state/session'
import { color, font, radius, space } from '@/theme/tokens'

export default function LoginScreen() {
  const { login, expired } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [server, setServer] = useState('')
  const [serverOpen, setServerOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // One-shot read of the persisted backend address; no render-time source.
  useEffect(() => {
    let alive = true
    getApiBaseUrl().then((url) => {
      if (alive) setServer(url)
    })
    return () => {
      alive = false
    }
  }, [])

  async function submit() {
    if (busy) return
    setError(null)
    setBusy(true)
    try {
      if (serverOpen && server.trim()) await setApiBaseUrl(server)
      await login(email.trim(), password)
    } catch (err) {
      if (err instanceof OfflineError) setError('Du är offline. Inloggning kräver uppkoppling.')
      else if (err instanceof ApiError && err.status === 401) setError('Fel e-post eller lösenord.')
      else if (err instanceof ApiError && err.status === 429) setError('För många försök. Vänta en stund.')
      else setError(err instanceof Error ? err.message : 'Inloggningen misslyckades.')
    } finally {
      setBusy(false)
    }
  }

  const canSubmit = email.trim().length > 0 && password.length > 0 && !busy

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      {/* `android:windowSoftInputMode=adjustResize` stops resizing the window
       * once the app is edge-to-edge (Android 15+), so the IME simply covers
       * the lower part of the screen. Pad explicitly for the keyboard and put
       * the form in a ScrollView so the focused field is scrolled into view —
       * the server field sits last and was otherwise unreachable. `flexGrow` +
       * `center` keeps the resting layout identical to a centred View. */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View>
          <Wordmark size={44} />
          {/* The brand statement, verbatim from the identity's own lockup
            * sheet. §07 sets a claim in serif, never in the interface sans. */}
          <View style={styles.tagline}>
            <Text style={styles.taglineStrong}>När svaret finns i dokumenten visar Träff exakt var.</Text>
            <Text style={styles.taglineSoft}>Finns det inte där säger Träff det.</Text>
          </View>

          {expired && (
            <View style={{ marginTop: space.xl }}>
              <Notice tone="refusal" title="Sessionen har gått ut">
                Logga in igen för att fortsätta.
              </Notice>
            </View>
          )}

          <View style={styles.form}>
            <View style={styles.field}>
              <Text style={styles.label}>E-post</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                placeholder="namn@forening.se"
                placeholderTextColor={color.ink25}
                editable={!busy}
              />
            </View>
            <View style={styles.field}>
              <Text style={styles.label}>Lösenord</Text>
              <TextInput
                style={styles.input}
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                autoComplete="password"
                placeholder="••••••••"
                placeholderTextColor={color.ink25}
                editable={!busy}
                onSubmitEditing={submit}
              />
            </View>

            {error && (
              <View style={{ marginTop: space.sm }}>
                <Notice tone="error" title="Det gick inte att logga in">
                  {error}
                </Notice>
              </View>
            )}

            <Pressable
              onPress={submit}
              disabled={!canSubmit}
              style={({ pressed }) => [
                styles.submit,
                (!canSubmit || pressed) && styles.submitPressed,
              ]}
            >
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitLabel}>Logga in</Text>}
            </Pressable>

            <Pressable onPress={() => setServerOpen((v) => !v)} style={styles.serverToggle}>
              <Text style={styles.serverToggleLabel}>
                {serverOpen ? 'Dölj serverinställning' : 'Serverinställning'}
              </Text>
            </Pressable>
            {serverOpen && (
              <View style={styles.field}>
                <Text style={styles.label}>Serveradress</Text>
                <TextInput
                  style={styles.input}
                  value={server}
                  onChangeText={setServer}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                  placeholder="http://192.168.1.10:8787"
                  placeholderTextColor={color.ink25}
                />
              </View>
            )}
          </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.bg,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: space.xxl,
    paddingVertical: space.xxl,
  },
  tagline: {
    marginTop: space.lg,
  },
  taglineStrong: {
    fontFamily: font.serif,
    fontSize: 21,
    lineHeight: 27,
    color: color.ink65,
    letterSpacing: -0.42,
  },
  taglineSoft: {
    fontFamily: font.serif,
    fontSize: 21,
    lineHeight: 27,
    color: color.ink38,
    letterSpacing: -0.42,
  },
  form: {
    marginTop: space.xxxl,
    gap: space.lg,
  },
  field: {
    gap: space.xs,
  },
  label: {
    fontFamily: font.mono,
    fontSize: 10,
    letterSpacing: 1.2,
    color: color.ink38,
    textTransform: 'uppercase',
  },
  input: {
    fontFamily: font.sans,
    fontSize: 16,
    color: color.ink,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  submit: {
    marginTop: space.sm,
    height: 50,
    borderRadius: radius.pill,
    backgroundColor: color.action,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitPressed: {
    opacity: 0.6,
  },
  submitLabel: {
    fontFamily: font.mono,
    fontSize: 12,
    letterSpacing: 1.4,
    color: '#fff',
  },
  serverToggle: {
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  serverToggleLabel: {
    fontFamily: font.mono,
    fontSize: 10.5,
    letterSpacing: 0.8,
    color: color.ink38,
  },
})
