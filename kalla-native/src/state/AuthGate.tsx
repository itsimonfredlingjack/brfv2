import { Redirect, useSegments } from 'expo-router'
import type { ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'

import { color } from '../theme/tokens'
import { useSession } from './session'

/**
 * Redirects between login, tenant-select and the app shell based on session
 * state. Mirrors xs_mobilapp's router.tsx guard, adapted to Expo Router's
 * segment-based navigation instead of a hash router.
 *
 * Uses `<Redirect>` (render-phase) rather than `router.replace()` inside a
 * `useEffect`: the imperative version still mounts `children` — and
 * therefore the matched tab screen underneath it, e.g. Fråga calling
 * `useActiveBrf()` — for one render before the effect can redirect away,
 * which throws. Returning `<Redirect>` in place of `children` means the
 * unauthenticated screen never mounts at all.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status, memberships, activeBrfId } = useSession()
  const segments = useSegments()
  const top = segments[0] as string | undefined

  if (status === 'loading') {
    return (
      <View style={{ flex: 1, backgroundColor: color.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={color.light} />
      </View>
    )
  }

  if (status === 'anonymous') {
    if (top !== 'login') return <Redirect href="/login" />
    return <>{children}</>
  }

  if (!activeBrfId && memberships.length > 1) {
    if (top !== 'valj') return <Redirect href="/valj" />
    return <>{children}</>
  }

  if (top === 'login' || top === 'valj') return <Redirect href="/" />
  return <>{children}</>
}
