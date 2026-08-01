import { Tabs } from 'expo-router'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import * as Haptics from 'expo-haptics'

import { color, font, space } from '@/theme/tokens'

/* Two destinations, not three, and not a hamburger — matching the 3a
 * prototype's bottom bar exactly: centered mono text labels, no icons, the
 * asking composer lives above this on Fråga rather than inside the bar. */
function TabBar({ state, descriptors, navigation }: Parameters<NonNullable<React.ComponentProps<typeof Tabs>['tabBar']>>[0]) {
  const insets = useSafeAreaInsets()

  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, space.md) }]}>
      {state.routes.map((route, index) => {
        const { options } = descriptors[route.key]
        const label = (options.title ?? route.name).toUpperCase()
        const focused = state.index === index

        return (
          <Pressable
            key={route.key}
            onPress={() => {
              if (!focused) {
                Haptics.selectionAsync().catch(() => {})
                navigation.navigate(route.name)
              }
            }}
            style={styles.item}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
          >
            <Text style={[styles.label, focused ? styles.labelActive : styles.labelInactive]}>{label}</Text>
          </Pressable>
        )
      })}
    </View>
  )
}

export default function TabsLayout() {
  return (
    <Tabs
      tabBar={(props) => <TabBar {...props} />}
      screenOptions={{ headerShown: false }}
    >
      <Tabs.Screen name="index" options={{ title: 'Fråga' }} />
      <Tabs.Screen name="bibliotek" options={{ title: 'Bibliotek' }} />
    </Tabs>
  )
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 26,
    paddingTop: space.md,
    backgroundColor: color.bg,
    borderTopWidth: 1,
    borderTopColor: color.hairline,
  },
  item: {
    paddingVertical: 6,
    paddingHorizontal: space.sm,
  },
  label: {
    fontFamily: font.monoBold,
    fontSize: 11,
    letterSpacing: 1.4,
  },
  labelActive: {
    color: color.ink,
  },
  labelInactive: {
    color: color.ink38,
  },
})
