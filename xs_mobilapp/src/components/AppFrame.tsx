import type { ReactNode } from 'react'

import { Link, useRouter } from '../app/router'
import { useSession } from '../state/session'
import { useOnline } from '../state/useOnline'
import { AskIcon, LibraryIcon, ReviewIcon, TaskIcon, WatchIcon } from './icons'

function initials(name: string | undefined, email: string): string {
  const source = (name ?? '').trim() || email
  const parts = source.split(/[\s@.]+/).filter(Boolean)
  const first = parts[0]?.[0] ?? '?'
  const second = parts.length > 1 ? parts[1]?.[0] ?? '' : ''
  return (first + second).toUpperCase()
}

export function AppFrame({ children }: { children: ReactNode }) {
  const { active, user } = useSession()
  const { path } = useRouter()
  const online = useOnline()

  const onAsk = path === '/' || path.startsWith('/svar')
  const onLibrary = path.startsWith('/bibliotek') || path.startsWith('/dokument')
  const onReview = path.startsWith('/granskning')
  const onWatches = path.startsWith('/bevakningar')
  const onTasks = path.startsWith('/uppgifter')

  return (
    <div className="frame">
      <header className="frame__header">
        <div className="frame__tenant">
          <div className="frame__tenant-name">{active?.name ?? 'Källa'}</div>
          <div className="frame__tenant-sub">
            {active ? (active.role === 'admin' ? 'Administratör' : 'Styrelseledamot') : 'Ingen förening vald'}
          </div>
        </div>
        <Link to="/konto" className="avatar" aria-label="Konto och inställningar">
          {user ? initials(user.name, user.email) : '–'}
        </Link>
      </header>

      {!online && (
        <div className="offline-strip" role="status">
          Du är offline. Sparade svar och nedladdade sidor går att läsa.
        </div>
      )}

      <main className="frame__main" id="innehall">
        {children}
      </main>

      <nav className="tabbar" aria-label="Huvudnavigering">
        <Link to="/" className="tabbar__item" aria-current={onAsk ? 'page' : undefined}>
          <AskIcon className="tabbar__icon" />
          Fråga
        </Link>
        <Link to="/bibliotek" className="tabbar__item" aria-current={onLibrary ? 'page' : undefined}>
          <LibraryIcon className="tabbar__icon" />
          Bibliotek
        </Link>
        <Link to="/granskning" className="tabbar__item" aria-current={onReview ? 'page' : undefined}>
          <ReviewIcon className="tabbar__icon" />
          Granskning
        </Link>
        <Link to="/bevakningar" className="tabbar__item" aria-current={onWatches ? 'page' : undefined}>
          <WatchIcon className="tabbar__icon" />
          Bevakningar
        </Link>
        <Link to="/uppgifter" className="tabbar__item" aria-current={onTasks ? 'page' : undefined}>
          <TaskIcon className="tabbar__icon" />
          Uppgifter
        </Link>
      </nav>
    </div>
  )
}
