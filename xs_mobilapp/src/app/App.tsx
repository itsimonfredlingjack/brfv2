import { useEffect, useState } from 'react'

import { AppFrame } from '../components/AppFrame'
import { Bibliotek } from '../screens/Bibliotek'
import { Dokument } from '../screens/Dokument'
import { Fraga } from '../screens/Fraga'
import { Granskning } from '../screens/Granskning'
import { Konto } from '../screens/Konto'
import { LockScreen } from '../screens/LockScreen'
import { Login } from '../screens/Login'
import { Svar } from '../screens/Svar'
import { ValjForening } from '../screens/ValjForening'
import { hasPin, shouldLock } from '../state/lock'
import { useSession } from '../state/session'
import { matchRoute, navigate, useRouter } from './router'

function Splash() {
  return (
    <div className="frame">
      <main className="frame__main">
        <div className="screen" style={{ justifyContent: 'center', alignItems: 'center' }}>
          <span className="visually-hidden">Startar Källa…</span>
          <span className="thinking__dot" aria-hidden="true" />
        </div>
      </main>
    </div>
  )
}

/** Which screen a path resolves to, once there is a session and a förening. */
function Routes({ brfId }: { brfId: string }) {
  const { path } = useRouter()

  if (path === '/') return <Fraga brfId={brfId} />
  if (path === '/bibliotek') return <Bibliotek brfId={brfId} />
  if (path === '/granskning') return <Granskning brfId={brfId} />
  if (path === '/konto') return <Konto brfId={brfId} />
  if (path === '/valj') return <ValjForening />

  const svar = matchRoute('/svar/:id', path)
  if (svar) return <Svar brfId={brfId} entryId={svar.id!} />

  const dokument = matchRoute('/dokument/:id', path)
  if (dokument) return <Dokument brfId={brfId} documentId={dokument.id!} />

  return <NotFound />
}

function NotFound() {
  return (
    <div className="screen">
      <div className="empty">
        <div className="empty__title">Sidan finns inte</div>
        <p className="empty__body">Länken leder ingenstans i appen.</p>
        <button type="button" className="btn btn--link" onClick={() => navigate('/', { replace: true })}>
          Till Fråga
        </button>
      </div>
    </div>
  )
}

export function App() {
  const { status, activeBrfId, logout } = useSession()
  const [locked, setLocked] = useState(() => hasPin())

  // Re-lock after a spell in the background. Tracks when the app was hidden
  // rather than running a timer, so a backgrounded tab that the OS froze is
  // still handled correctly on return.
  useEffect(() => {
    let hiddenSince: number | null = null

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenSince = Date.now()
        return
      }
      if (shouldLock(hiddenSince)) setLocked(true)
      hiddenSince = null
    }

    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  if (status === 'loading') return <Splash />
  if (status === 'anonymous') return <Login />

  if (locked && hasPin()) {
    return (
      <LockScreen
        onUnlock={() => setLocked(false)}
        onForgot={() => {
          setLocked(false)
          void logout()
        }}
      />
    )
  }

  // Authenticated but no förening resolved — the user belongs to several and
  // has not picked one yet.
  if (!activeBrfId) return <ValjForening standalone />

  return (
    <AppFrame>
      {/* Keyed by förening so switching tenants REMOUNTS every screen rather
          than re-rendering it with a new prop. Without this, a request that
          was already in flight for the previous förening would resolve into
          a live component holding the old id — and write that tenant's data
          back onto a device that had just wiped it. */}
      <Routes key={activeBrfId} brfId={activeBrfId} />
    </AppFrame>
  )
}
