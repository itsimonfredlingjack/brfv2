import { useFonts } from 'expo-font'
import { Stack } from 'expo-router'
import * as SplashScreen from 'expo-splash-screen'
import { useEffect } from 'react'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { SafeAreaProvider } from 'react-native-safe-area-context'

import { AuthGate } from '@/state/AuthGate'
import { SessionProvider } from '@/state/session'
import { color } from '@/theme/tokens'
import { fontAssets } from '@/theme/fonts'
import { StatusBar } from 'expo-status-bar'

SplashScreen.preventAutoHideAsync().catch(() => {})

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fontAssets)

  useEffect(() => {
    if (fontsLoaded || fontError) SplashScreen.hideAsync().catch(() => {})
  }, [fontsLoaded, fontError])

  if (!fontsLoaded && !fontError) return null

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: color.bg }}>
      <SafeAreaProvider>
        <SessionProvider>
          <StatusBar style="light" />
          <AuthGate>
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: color.bg },
                animation: 'slide_from_right',
                animationDuration: 180,
              }}
            >
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="login" options={{ animation: 'fade' }} />
              <Stack.Screen name="valj" options={{ animation: 'fade' }} />
              <Stack.Screen name="svar/[localId]" />
              <Stack.Screen name="dokument/[id]" />
              <Stack.Screen name="konto" options={{ animation: 'slide_from_bottom' }} />
            </Stack>
          </AuthGate>
        </SessionProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
