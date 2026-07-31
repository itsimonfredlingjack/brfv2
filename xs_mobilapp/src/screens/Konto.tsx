import { useEffect, useState } from 'react'

import { back, navigate } from '../app/router'
import { Notice } from '../components/Notice'
import { ChevronLeft, ChevronRight } from '../components/icons'
import { RETENTION_DAYS, clearJournal, listEntries } from '../state/localStore'
import { LOCK_AFTER_MINUTES, clearPin, hasPin, lockAvailable, setPin } from '../state/lock'
import { useSession } from '../state/session'

export function Konto({ brfId }: { brfId: string }) {
  const { user, memberships, active, health, logout } = useSession()
  const [entryCount, setEntryCount] = useState<number | null>(null)
  const [pinOn, setPinOn] = useState(hasPin())
  const [pinDraft, setPinDraft] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)

  useEffect(() => {
    listEntries(brfId)
      .then((list) => setEntryCount(list.length))
      .catch(() => setEntryCount(null))
  }, [brfId])

  async function clearHistory() {
    await clearJournal(brfId)
    setEntryCount(0)
  }

  async function enablePin() {
    if (pinDraft.length < 4) {
      setPinError('Koden måste vara minst fyra siffror.')
      return
    }
    await setPin(pinDraft)
    setPinDraft('')
    setPinError(null)
    setPinOn(true)
  }

  const llm = health?.llm

  return (
    <div className="screen">
      <button
        type="button"
        className="backlink"
        onClick={back}
      >
        <ChevronLeft size={16} />
        Tillbaka
      </button>

      <h1 className="screen__title" style={{ marginTop: 'var(--s4)' }}>
        Konto
      </h1>

      <div className="card" style={{ marginTop: 'var(--s5)' }}>
        <div className="row__title">{user?.name || user?.email}</div>
        <div className="row__meta">{user?.email}</div>
        <div className="row__meta" style={{ marginTop: 'var(--s2)' }}>
          {active?.name} · {active?.role === 'admin' ? 'Administratör' : 'Styrelseledamot'}
        </div>
      </div>

      {memberships.length > 1 && (
        <section style={{ marginTop: 'var(--s6)' }}>
          <div className="label">Förening</div>
          <div className="list">
            <button type="button" className="row" onClick={() => navigate('/valj')}>
              <span className="row__body">
                <span className="row__title">Byt förening</span>
                <span className="row__meta">
                  Data för {active?.name} tas bort från telefonen vid byte
                </span>
              </span>
              <ChevronRight className="row__chevron" />
            </button>
          </div>
        </section>
      )}

      <section style={{ marginTop: 'var(--s6)' }}>
        <div className="label">Svarstjänst</div>
        <div className="card" style={{ marginTop: 'var(--s3)' }}>
          {llm ? (
            <>
              <div className="row__title">
                {llm.ready ? llm.display_name || llm.model || 'Konfigurerad' : 'Ingen modell konfigurerad'}
              </div>
              <div className="row__meta">
                {llm.ready
                  ? `Leverantör: ${llm.provider}${llm.runtime_label ? ` · ${llm.runtime_label}` : ''}`
                  : 'Frågor kan inte besvaras förrän en modell är konfigurerad.'}
              </div>
              <div className="row__meta" style={{ marginTop: 'var(--s2)' }}>
                {/* Deliberately not overstated: /api/health reports
                    configuration, not live reachability (XS-37). */}
                Visar konfigurerat läge, inte att tjänsten svarar just nu.
              </div>
            </>
          ) : (
            <div className="row__meta">Statusen kunde inte hämtas.</div>
          )}
        </div>
      </section>

      <section style={{ marginTop: 'var(--s6)' }}>
        <div className="label">Sparat på telefonen</div>
        <div className="card" style={{ marginTop: 'var(--s3)' }}>
          <div className="row__meta">
            {entryCount === null
              ? 'Svarshistorik'
              : `${entryCount} ${entryCount === 1 ? 'sparat svar' : 'sparade svar'}`}{' '}
            för {active?.name}. Svar innehåller text ur föreningens dokument och raderas
            automatiskt efter {RETENTION_DAYS} dagar — och alltid vid utloggning.
          </div>
          <div style={{ marginTop: 'var(--s4)' }}>
            <button type="button" className="btn btn--quiet btn--danger" onClick={() => void clearHistory()}>
              Rensa svarshistorik
            </button>
          </div>
        </div>
      </section>

      <section style={{ marginTop: 'var(--s6)' }}>
        <div className="label">Kodlås</div>
        <div className="card" style={{ marginTop: 'var(--s3)' }}>
          {!lockAvailable() ? (
            <div className="row__meta">
              Kodlås kräver en säker anslutning (https eller localhost) och är inte tillgängligt
              här.
            </div>
          ) : pinOn ? (
            <>
              <div className="row__meta">
                Appen låses efter {LOCK_AFTER_MINUTES} minuter i bakgrunden. Kodlåset skyddar
                innehållet på telefonen — det är inte en ny inloggning mot servern.
              </div>
              <div style={{ marginTop: 'var(--s4)' }}>
                <button
                  type="button"
                  className="btn btn--quiet"
                  onClick={() => {
                    clearPin()
                    setPinOn(false)
                  }}
                >
                  Stäng av kodlås
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="row__meta">
                Kräv en kod när appen har legat i bakgrunden i {LOCK_AFTER_MINUTES} minuter.
              </div>
              <label className="field">
                <span className="field__label">Ny kod (minst 4 siffror)</span>
                <input
                  className="field__input"
                  type="password"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={8}
                  value={pinDraft}
                  onChange={(event) => {
                    setPinDraft(event.target.value.replace(/\D/g, ''))
                    setPinError(null)
                  }}
                />
              </label>
              {pinError && (
                <div style={{ marginTop: 'var(--s3)' }}>
                  <Notice tone="error" title="Koden sparades inte">
                    {pinError}
                  </Notice>
                </div>
              )}
              <div style={{ marginTop: 'var(--s4)' }}>
                <button type="button" className="btn btn--quiet" onClick={() => void enablePin()}>
                  Aktivera kodlås
                </button>
              </div>
            </>
          )}
        </div>
      </section>

      <div style={{ marginTop: 'var(--s8)' }}>
        <button type="button" className="btn btn--quiet btn--danger" onClick={() => void logout()}>
          Logga ut
        </button>
        <p className="row__meta" style={{ marginTop: 'var(--s3)', textAlign: 'center' }}>
          Utloggning raderar alla sparade svar och nedladdade sidor från telefonen.
        </p>
      </div>
    </div>
  )
}
