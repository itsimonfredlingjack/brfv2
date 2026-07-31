import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, api } from '../api/client'
import type { Health, Membership, User } from '../api/types'
import { wipeEverything, wipeTenant } from './localStore'
import { clearPin } from './lock'
import { clearPendingQuestion } from './pending'

const ACTIVE_BRF_KEY = 'kalla.activeBrf'

type Status = 'loading' | 'anonymous' | 'authenticated'

interface SessionValue {
  status: Status
  user: User | null
  memberships: Membership[]
  activeBrfId: string | null
  active: Membership | null
  health: Health | null
  /** True when a live session was rejected mid-use, so the login screen can
   * explain why the user is suddenly looking at it. */
  expired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  switchTenant: (brfId: string) => Promise<void>
  refresh: () => Promise<void>
  /** Report a 401 from any request; drops to the login screen with a reason. */
  reportUnauthorized: () => void
}

const SessionContext = createContext<SessionValue | null>(null)

function readStoredBrf(): string | null {
  try {
    return localStorage.getItem(ACTIVE_BRF_KEY)
  } catch {
    return null
  }
}

function storeBrf(brfId: string | null) {
  try {
    if (brfId) localStorage.setItem(ACTIVE_BRF_KEY, brfId)
    else localStorage.removeItem(ACTIVE_BRF_KEY)
  } catch {
    // private mode / storage disabled — the session still works, it just
    // forgets which förening was active between launches.
  }
}

/** Keep the remembered tenant only if it is still a real membership. */
function resolveActive(memberships: Membership[], preferred: string | null): string | null {
  if (preferred && memberships.some((m) => m.brf_id === preferred)) return preferred
  if (memberships.length === 1) return memberships[0]!.brf_id
  return null
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [memberships, setMemberships] = useState<Membership[]>([])
  const [activeBrfId, setActiveBrfId] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [expired, setExpired] = useState(false)

  const applyIdentity = useCallback((nextUser: User, nextMemberships: Membership[]) => {
    setUser(nextUser)
    setMemberships(nextMemberships)
    const active = resolveActive(nextMemberships, readStoredBrf())
    setActiveBrfId(active)
    storeBrf(active)
    setExpired(false)
    setStatus('authenticated')
  }, [])

  /** A request came back 401 while the app believed it was signed in. Drop to
   * the login screen, but say why — being silently returned to a login form
   * mid-conversation reads as the app breaking, not as a session ending.
   *
   * The device is wiped here for the same reason it is on logout: the session
   * is over, and whoever signs in next must not inherit the previous one's
   * answers or pages. A 401 only arrives over a live connection, so nothing
   * that was readable offline is lost silently. */
  const reportUnauthorized = useCallback(() => {
    void wipeEverything().catch(() => {})
    setExpired(true)
    setUser(null)
    setMemberships([])
    setActiveBrfId(null)
    setStatus('anonymous')
  }, [])

  const refresh = useCallback(async () => {
    try {
      const me = await api.me()
      applyIdentity(me.user, me.memberships)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setStatus('anonymous')
        setUser(null)
        setMemberships([])
        setActiveBrfId(null)
        return
      }
      // Offline with a cookie we cannot validate: stay anonymous rather than
      // pretending to be logged in. Asking needs the network anyway, and a
      // fake-authenticated shell would be a worse lie than a login screen.
      setStatus('anonymous')
    }
  }, [applyIdentity])

  useEffect(() => {
    void refresh()
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [refresh])

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await api.login(email, password)
      applyIdentity(result.user, result.memberships)
    },
    [applyIdentity],
  )

  const logout = useCallback(async () => {
    // Wipe FIRST. A failed logout request must not be able to leave document
    // text on the device.
    await wipeEverything()
    clearPendingQuestion()
    // The code lock belongs to the session that set it. Leaving it behind
    // would lock the NEXT person out of their own account with a code only
    // the previous user knows.
    clearPin()
    storeBrf(null)
    setExpired(false)
    try {
      await api.logout()
    } catch {
      // The local session is gone either way.
    }
    setUser(null)
    setMemberships([])
    setActiveBrfId(null)
    setStatus('anonymous')
  }, [])

  const switchTenant = useCallback(
    async (brfId: string) => {
      // Leave nothing behind for the förening being left: its answers and
      // page images are wiped before the new one renders.
      if (activeBrfId && activeBrfId !== brfId) await wipeTenant(activeBrfId)
      setActiveBrfId(brfId)
      storeBrf(brfId)
    },
    [activeBrfId],
  )

  const value = useMemo<SessionValue>(
    () => ({
      status,
      user,
      memberships,
      activeBrfId,
      active: memberships.find((m) => m.brf_id === activeBrfId) ?? null,
      health,
      expired,
      login,
      logout,
      switchTenant,
      refresh,
      reportUnauthorized,
    }),
    [
      status,
      user,
      memberships,
      activeBrfId,
      health,
      expired,
      login,
      logout,
      switchTenant,
      refresh,
      reportUnauthorized,
    ],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession utanför SessionProvider')
  return value
}

/** The active tenant id, for screens that only render when one exists. */
export function useActiveBrf(): string {
  const { activeBrfId } = useSession()
  if (!activeBrfId) throw new Error('Ingen aktiv förening')
  return activeBrfId
}
