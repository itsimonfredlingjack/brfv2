import NetInfo from '@react-native-community/netinfo'
import { useEffect, useState } from 'react'

/** True until proven otherwise — matches the PWA's `navigator.onLine`
 * default and avoids a false "offline" flash before the first NetInfo
 * event arrives. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(true)

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setOnline(state.isConnected !== false && state.isInternetReachable !== false)
    })
    return unsubscribe
  }, [])

  return online
}
