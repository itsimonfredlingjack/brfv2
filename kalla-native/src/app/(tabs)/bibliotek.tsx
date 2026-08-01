import { useRouter } from 'expo-router'
import { useEffect, useState } from 'react'
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { api } from '@/api/client'
import type { DocumentMeta } from '@/api/types'
import { formatDate } from '@/lib/format'
import { metaCache } from '@/state/journal'
import { useActiveBrf } from '@/state/session'
import { color, font, radius, space } from '@/theme/tokens'

export default function BibliotekScreen() {
  const router = useRouter()
  const brfId = useActiveBrf()
  const [documents, setDocuments] = useState<DocumentMeta[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    metaCache.documents.read(brfId).then((cached) => {
      if (cached && !cancelled) setDocuments(cached)
    })
    api
      .listDocuments(brfId)
      .then((fresh) => {
        if (cancelled) return
        setDocuments(fresh)
        void metaCache.documents.write(brfId, fresh).catch(() => {})
      })
      .catch(() => {
        if (!cancelled && documents === null) setError('Kunde inte hämta dokumentlistan.')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brfId])

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <Text style={styles.title}>Bibliotek</Text>

      {documents !== null && documents.length === 0 && (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Föreningen har inga dokument ännu.</Text>
        </View>
      )}

      {error && documents === null && (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>{error}</Text>
        </View>
      )}

      <FlatList
        data={documents ?? []}
        keyExtractor={(d) => d.id}
        contentContainerStyle={{ paddingHorizontal: space.xxl, paddingBottom: space.xxl, gap: space.sm }}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => router.push({ pathname: '/dokument/[id]', params: { id: item.id } })}
            style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
          >
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {item.name}
              </Text>
              <Text style={styles.rowMeta}>
                {item.pages} SIDOR · {item.source === 'scanned' ? 'SKANNAT' : 'DIGITALT'} · {formatDate(item.uploaded_at)}
              </Text>
            </View>
          </Pressable>
        )}
      />
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  title: { fontFamily: font.serif, fontSize: 28, color: color.ink, paddingHorizontal: space.xxl, paddingTop: space.md, marginBottom: space.lg },
  empty: { paddingHorizontal: space.xxl, paddingVertical: space.xl },
  emptyTitle: { fontFamily: font.sans, fontSize: 14, color: color.ink50 },
  row: { flexDirection: 'row', alignItems: 'center', padding: space.lg, borderRadius: radius.md, backgroundColor: color.surface, borderWidth: 1, borderColor: color.hairline },
  rowPressed: { backgroundColor: color.surfacePress },
  rowTitle: { fontFamily: font.sansMedium, fontSize: 14.5, color: color.ink },
  rowMeta: { fontFamily: font.mono, fontSize: 10, letterSpacing: 0.6, color: color.ink38, marginTop: 4 },
})
