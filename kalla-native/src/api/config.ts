import AsyncStorage from '@react-native-async-storage/async-storage'

/**
 * Where the backend lives. A native app has no "same origin" to inherit the
 * way the PWA does (APP-BUILD-BRIEF §7) — it must be told a host. Defaults
 * to the env var baked at build time; overridable at runtime from the login
 * screen for LAN/SSH-forward deployments (brief §13: public hosting is an
 * explicit open decision, not assumed here).
 */
const STORAGE_KEY = 'kalla.apiBaseUrl'
const BUILD_DEFAULT = process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') || ''

let cached: string | null = null

export async function getApiBaseUrl(): Promise<string> {
  if (cached !== null) return cached
  let resolved = BUILD_DEFAULT
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY)
    if (stored && stored.trim()) resolved = stored.trim().replace(/\/+$/, '')
  } catch {
    // fall back to BUILD_DEFAULT
  }
  cached = resolved
  return resolved
}

export function getApiBaseUrlSync(): string {
  return cached ?? BUILD_DEFAULT
}

export async function setApiBaseUrl(url: string): Promise<void> {
  const clean = url.trim().replace(/\/+$/, '')
  cached = clean
  await AsyncStorage.setItem(STORAGE_KEY, clean)
}
