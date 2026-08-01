import { Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { useSession } from '@/state/session'
import { color, font, radius, space } from '@/theme/tokens'

export default function ValjForeningScreen() {
  const { memberships, switchTenant } = useSession()

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.content}>
        <Text style={styles.title}>Välj förening</Text>
        <Text style={styles.lede}>Du är medlem i flera föreningar.</Text>

        <View style={styles.list}>
          {memberships.map((m) => (
            <Pressable
              key={m.brf_id}
              onPress={() => void switchTenant(m.brf_id)}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
            >
              <Text style={styles.rowTitle}>{m.name}</Text>
              <Text style={styles.rowMeta}>{m.role === 'admin' ? 'ADMINISTRATÖR' : 'STYRELSELEDAMOT'}</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  content: { flex: 1, paddingHorizontal: space.xxl, paddingTop: space.xxxl },
  title: { fontFamily: font.serif, fontSize: 30, color: color.ink },
  lede: { fontFamily: font.sans, fontSize: 14, color: color.ink50, marginTop: space.xs },
  list: { marginTop: space.xxl, gap: space.sm },
  row: {
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    padding: space.lg,
  },
  rowPressed: { backgroundColor: color.surfacePress },
  rowTitle: { fontFamily: font.sansMedium, fontSize: 15.5, color: color.ink },
  rowMeta: { fontFamily: font.mono, fontSize: 10, letterSpacing: 1, color: color.ink38, marginTop: 4 },
})
