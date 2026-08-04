import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, OfflineError } from '../api/client'
import { Notice } from '../components/Notice'
import { TraffMark } from '../components/TraffMark'
import { useSession } from '../state/session'

/* Seeded demo logins, for the dev-mode convenience list only.
 *
 * Guarded by import.meta.env.DEV so the constant folds to an empty array at
 * build time and these strings never reach a production bundle. They are only
 * ever valid against `scripts/seed.py`'s synthetic föreningar, but a release
 * artifact that ships login credentials is the kind of thing nobody wants to
 * explain later. */
const DEMO_ACCOUNTS = import.meta.env.DEV
  ? [
      { email: 'anna@gjutformen12.se', password: 'gjutformen-demo-2026', label: 'Anna — administratör' },
      { email: 'bo@gjutformen12.se', password: 'gjutformen-medlem-2026', label: 'Bo — styrelseledamot' },
      { email: 'max@demo.se', password: 'max-demo-2026', label: 'Max — två föreningar' },
    ]
  : []

function messageFor(error: unknown): string {
  if (error instanceof OfflineError) return 'Du är offline. Inloggning kräver uppkoppling.'
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Fel e-post eller lösenord.'
    if (error.status === 429) return error.message
    if (error.status === 0) return 'Servern går inte att nå just nu.'
    return error.message
  }
  return 'Inloggningen misslyckades.'
}

export function Login() {
  const { login, health, expired } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const showDemoAccounts = health?.mode === 'dev' && DEMO_ACCOUNTS.length > 0

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (err) {
      setError(messageFor(err))
      setBusy(false)
    }
  }

  return (
    <div className="frame">
      <main className="frame__main">
        <div className="screen">
          {/* §05 Lockup: the mark stands before the name at cap height. It
              says who is speaking before it asks for anything. */}
          <span className="lockup">
            <TraffMark size={28} decorative />
            <h1 className="screen__title lockup__name">Träff</h1>
          </span>
          <p className="screen__lede">
            Ställ en fråga om föreningens dokument. Svaret visar var det står.
            Står det ingenstans säger Träff det.
          </p>

          {expired && !error && (
            <div style={{ marginTop: 'var(--s5)' }}>
              <Notice tone="refusal" title="Din session har gått ut">
                Logga in igen för att fortsätta. Din fråga finns kvar.
              </Notice>
            </div>
          )}

          <form onSubmit={onSubmit} style={{ marginTop: 'var(--s6)' }}>
            <label className="field">
              <span className="field__label">E-post</span>
              <input
                className="field__input"
                type="email"
                name="email"
                autoComplete="username"
                inputMode="email"
                autoCapitalize="none"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Lösenord</span>
              <input
                className="field__input"
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            {error && (
              <div style={{ marginTop: 'var(--s4)' }}>
                <Notice tone="error" title="Kunde inte logga in">
                  {error}
                </Notice>
              </div>
            )}

            <div style={{ marginTop: 'var(--s5)' }}>
              <button type="submit" className="btn btn--primary" disabled={busy}>
                {busy ? 'Loggar in…' : 'Logga in'}
              </button>
            </div>
          </form>

          {showDemoAccounts && (
            <div style={{ marginTop: 'var(--s8)' }}>
              <div className="label">Demokonton (utvecklingsläge)</div>
              <div className="list">
                {DEMO_ACCOUNTS.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    className="row"
                    onClick={() => {
                      setEmail(account.email)
                      setPassword(account.password)
                    }}
                  >
                    <span className="row__body">
                      <span className="row__title">{account.label}</span>
                      <span className="row__meta">{account.email}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
