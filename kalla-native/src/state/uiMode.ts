import { useCallback, useEffect, useState } from 'react'
import { BackHandler } from 'react-native'

export type UiMode = 'answer' | 'kalla' | 'visa'

/**
 * Svar → Källa → Visa is one local UI-mode stack, not three routes — a
 * router push per layer would fight the hero transition's shared
 * measurement and would give the OS back button the wrong granularity.
 * Android Back steps down one layer at a time (visa → kalla → answer)
 * instead of leaving the screen (brief §5 navigation rules; mission
 * core_flow: "Android Back should leave presentation mode before closing
 * the source").
 */
export function useUiModeStack() {
  const [mode, setMode] = useState<UiMode>('answer')

  const openKalla = useCallback(() => setMode('kalla'), [])
  const openVisa = useCallback(() => setMode('visa'), [])
  const closeVisa = useCallback(() => setMode('kalla'), [])
  const closeKalla = useCallback(() => setMode('answer'), [])

  useEffect(() => {
    if (mode === 'answer') return undefined
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      setMode((current) => {
        if (current === 'visa') return 'kalla'
        if (current === 'kalla') return 'answer'
        return current
      })
      return true
    })
    return () => sub.remove()
  }, [mode])

  return { mode, openKalla, openVisa, closeVisa, closeKalla }
}
