import { useState } from 'react'
import type { FormEvent } from 'react'

import { Notice } from '../components/Notice'
import { LockIcon } from '../components/icons'
import { verifyPin } from '../state/lock'

export function LockScreen({ onUnlock, onForgot }: { onUnlock: () => void; onForgot: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (await verifyPin(pin)) {
      onUnlock()
      return
    }
    setError(true)
    setPin('')
  }

  return (
    <div className="frame">
      <main className="frame__main">
        <div className="screen" style={{ justifyContent: 'center' }}>
          <div style={{ textAlign: 'center', color: 'var(--ink-2)' }}>
            <LockIcon size={32} />
          </div>
          <h1 className="screen__title" style={{ textAlign: 'center', marginTop: 'var(--s3)' }}>
            Lås upp Träff
          </h1>
          <p className="screen__lede" style={{ textAlign: 'center' }}>
            Ange din kod för att komma åt föreningens svar och dokument.
          </p>

          <form onSubmit={submit}>
            <label className="field">
              <span className="visually-hidden">Kod</span>
              <input
                className="field__input"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                pattern="[0-9]*"
                maxLength={8}
                autoFocus
                value={pin}
                onChange={(event) => {
                  setPin(event.target.value.replace(/\D/g, ''))
                  setError(false)
                }}
                style={{ textAlign: 'center', letterSpacing: '0.5em', fontSize: '1.25rem' }}
              />
            </label>

            {error && (
              <div style={{ marginTop: 'var(--s4)' }}>
                <Notice tone="error" title="Fel kod">
                  Koden stämmer inte.
                </Notice>
              </div>
            )}

            <div style={{ marginTop: 'var(--s5)' }}>
              <button type="submit" className="btn btn--primary" disabled={pin.length < 4}>
                Lås upp
              </button>
            </div>
          </form>

          <div style={{ marginTop: 'var(--s5)', textAlign: 'center' }}>
            <button type="button" className="btn btn--link" onClick={onForgot}>
              Glömt koden? Logga ut
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
