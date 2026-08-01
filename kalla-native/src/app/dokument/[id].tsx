import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { api } from '@/api/client'
import type { Extraction } from '@/api/types'
import { KallaSheet } from '@/components/KallaSheet'
import type { KallaTarget } from '@/components/KallaSheet'
import { ChevronLeft } from '@/components/icons'
import { formatDate } from '@/lib/format'
import { metaCache } from '@/state/journal'
import { useActiveBrf } from '@/state/session'
import { useHeroFlight } from '@/state/useHeroFlight'
import { color, font, radius, space } from '@/theme/tokens'

export default function DokumentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const router = useRouter()
  const brfId = useActiveBrf()
  const hero = useHeroFlight()
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [pageInput, setPageInput] = useState('1')
  const [target, setTarget] = useState<KallaTarget | null>(null)

  useEffect(() => {
    let cancelled = false
    metaCache.extraction.read(brfId, id).then((cached) => cached && !cancelled && setExtraction(cached))
    api
      .getExtraction(brfId, id)
      .then((fresh) => {
        if (cancelled) return
        setExtraction(fresh)
        void metaCache.extraction.write(brfId, id, fresh).catch(() => {})
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [brfId, id])

  const doc = extraction?.document

  function openPage() {
    const page = Math.max(1, Math.min(Number.parseInt(pageInput, 10) || 1, doc?.pages ?? 1))
    setTarget({ documentId: id, documentName: doc?.name ?? '', page, citation: null })
  }

  return (
    <View style={{ flex: 1, backgroundColor: color.bg }}>
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        <Pressable onPress={() => router.back()} style={styles.backLink}>
          <ChevronLeft />
          <Text style={styles.backLabel}>Bibliotek</Text>
        </Pressable>

        {doc && (
          <View style={styles.content}>
            <Text style={styles.title}>{doc.name}</Text>
            <Text style={styles.meta}>
              {doc.pages} SIDOR · {doc.source === 'scanned' ? 'SKANNAT' : 'DIGITALT'} · UPPLADDAT {formatDate(doc.uploaded_at)}
            </Text>

            <View style={styles.jump}>
              <Text style={styles.jumpLabel}>Gå till sida</Text>
              <View style={styles.jumpRow}>
                <TextInput
                  style={styles.jumpInput}
                  value={pageInput}
                  onChangeText={setPageInput}
                  keyboardType="number-pad"
                  maxLength={4}
                />
                <Text style={styles.jumpOf}>av {doc.pages}</Text>
                <Pressable onPress={openPage} style={styles.jumpBtn}>
                  <Text style={styles.jumpBtnLabel}>Öppna</Text>
                </Pressable>
              </View>
            </View>
          </View>
        )}
      </SafeAreaView>

      {target && (
        <View style={StyleSheet.absoluteFill}>
          <KallaSheet brfId={brfId} target={target} hero={hero} onClose={() => setTarget(null)} onOpenVisa={() => {}} />
        </View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: space.lg, paddingTop: space.sm },
  backLabel: { fontFamily: font.sansMedium, fontSize: 13, color: color.ink50 },
  content: { paddingHorizontal: space.xxl, paddingTop: space.xl },
  title: { fontFamily: font.serif, fontSize: 26, color: color.ink, letterSpacing: -0.2 },
  meta: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.8, color: color.ink38, marginTop: space.sm },
  jump: { marginTop: space.xxl },
  jumpLabel: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1.2, color: color.ink38, marginBottom: space.sm },
  jumpRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  jumpInput: {
    width: 64,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    color: color.ink,
    fontFamily: font.mono,
    fontSize: 15,
    textAlign: 'center',
  },
  jumpOf: { fontFamily: font.sans, fontSize: 13, color: color.ink38 },
  jumpBtn: { marginLeft: 'auto', height: 44, paddingHorizontal: space.lg, borderRadius: radius.md, backgroundColor: color.action, alignItems: 'center', justifyContent: 'center' },
  jumpBtnLabel: { fontFamily: font.sansSemibold, fontSize: 13, color: '#fff' },
})
