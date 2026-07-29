import { useEffect, useRef, useState } from 'react'

import { ApiError, OfflineError, api } from '../api/client'
import { navigate } from '../app/router'
import { Notice } from '../components/Notice'
import { SendIcon } from '../components/icons'
import { formatMoment } from '../lib/format'
import { refusalCopy } from '../lib/refusals'
import { metaCache, newEntryId, saveEntry } from '../state/localStore'
import type { JournalEntry } from '../state/localStore'
import { listEntries } from '../state/localStore'
import { rememberPendingQuestion, takePendingQuestion } from '../state/pending'
import { useSession } from '../state/session'
import { useOnline } from '../state/useOnline'

type AskStage = 'idle' | 'retrieving' | 'generating'

/** How long the "Söker i N dokument…" stage is shown before the copy moves
 * on to generation. Retrieval really is the fast part; this is an honest
 * description of what is happening, not a fake progress bar. */
const RETRIEVAL_COPY_MS = 1400

export function Fraga({ brfId }: { brfId: string }) {
  const { reportUnauthorized, user } = useSession()
  const online = useOnline()
  const userId = user?.id ?? ''

  // Restores a question that a session expiry interrupted — only for the
  // person who typed it.
  const [question, setQuestion] = useState(() => takePendingQuestion(userId))
  const [stage, setStage] = useState<AskStage>('idle')
  const [error, setError] = useState<string | null>(null)
  const [entries, setEntries] = useState<JournalEntry[] | null>(null)
  const [documentCount, setDocumentCount] = useState<number | null>(null)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const aliveRef = useRef(true)

  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    listEntries(brfId)
      .then((list) => !cancelled && setEntries(list))
      .catch(() => !cancelled && setEntries([]))
    return () => {
      cancelled = true
    }
  }, [brfId])

  // Document count, cache-first — it is what makes the wait state concrete
  // ("Söker i 5 dokument…") and it warms Bibliotek at the same time.
  useEffect(() => {
    let cancelled = false

    async function load() {
      const cached = await metaCache.documents.read(brfId).catch(() => undefined)
      if (cached && !cancelled) setDocumentCount(cached.length)
      try {
        const fresh = await api.listDocuments(brfId)
        if (cancelled) return
        setDocumentCount(fresh.length)
        await metaCache.documents.write(brfId, fresh).catch(() => {})
      } catch {
        // Cached count, or none — neither blocks asking.
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [brfId])

  function grow(element: HTMLTextAreaElement) {
    element.style.height = 'auto'
    element.style.height = `${element.scrollHeight}px`
  }

  async function ask() {
    const text = question.trim()
    if (!text || stage !== 'idle') return

    setError(null)
    setStage('retrieving')
    const toGenerating = setTimeout(() => setStage('generating'), RETRIEVAL_COPY_MS)

    try {
      const response = await api.ask(brfId, text)
      // Belt and braces alongside the remount key in App.tsx: an answer that
      // lands after this screen is gone belongs to a förening the device may
      // have just wiped, and must not be written back.
      if (!aliveRef.current) return
      const entry: JournalEntry = {
        id: newEntryId(),
        brfId,
        question: text,
        createdAt: Date.now(),
        answer: response.answer,
        refusal: response.refusal,
        refusalReason: response.refusal_reason,
        warning: response.warning,
        citations: response.citations,
        rejected: response.rejected_citations,
        provider: response.provider,
        model: response.model,
      }
      await saveEntry(entry)
      setQuestion('')
      if (inputRef.current) inputRef.current.style.height = 'auto'
      navigate(`/svar/${entry.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Keep the question. The user is standing in front of someone; making
        // them retype it is where the tool stops feeling dependable.
        rememberPendingQuestion(userId, text)
        reportUnauthorized()
        return
      }
      if (err instanceof OfflineError) setError('Du är offline. Frågor kräver uppkoppling.')
      else if (err instanceof ApiError && err.status === 0) setError('Servern gick inte att nå.')
      else setError(err instanceof Error ? err.message : 'Frågan kunde inte skickas.')
    } finally {
      clearTimeout(toGenerating)
      setStage('idle')
    }
  }

  const busy = stage !== 'idle'
  const canSend = question.trim().length > 0 && online && !busy

  return (
    <>
      <div className="screen screen--flush">
        <h1 className="screen__title">Fråga</h1>
        <p className="screen__lede">
          Svaren bygger bara på föreningens egna dokument, och varje påstående går att öppna på
          rätt sida.
        </p>

        {busy && (
          <div className="card" style={{ marginTop: 'var(--s5)' }}>
            <div className="thinking" aria-live="polite">
              <span className="thinking__dot" />
              {stage === 'retrieving'
                ? /* "dokument" is invariant in the Swedish plural — no ternary needed. */
                  `Söker i ${documentCount ?? 'föreningens'} dokument…`
                : 'Formulerar svar…'}
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 'var(--s5)' }}>
            <Notice tone="error" title="Frågan gick inte att ställa">
              {error}
            </Notice>
          </div>
        )}

        {entries !== null && entries.length > 0 && (
          <section style={{ marginTop: 'var(--s6)' }}>
            <div className="label">Tidigare svar</div>
            <div className="list">
              {entries.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  className="row"
                  onClick={() => navigate(`/svar/${entry.id}`)}
                >
                  <span className="row__body">
                    <span className="row__title">{entry.question}</span>
                    <span className="row__meta">
                      {entry.refusal
                        ? refusalCopy(entry.refusalReason).title
                        : `${entry.citations.length} ${entry.citations.length === 1 ? 'källa' : 'källor'}`}
                      {' · '}
                      {formatMoment(entry.createdAt)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {entries !== null && entries.length === 0 && !busy && (
          <div className="empty">
            <div className="empty__title">Inga frågor ännu</div>
            <p className="empty__body">
              {documentCount === 0
                ? 'Föreningen har inga dokument uppladdade ännu.'
                : 'Fråga om stadgar, protokoll, avtal eller årsredovisning — svaret kommer med källa.'}
            </p>
          </div>
        )}
      </div>

      <div className="composer">
        <div className="composer__shell">
          <label htmlFor="fraga" className="visually-hidden">
            Din fråga om föreningens dokument
          </label>
          <textarea
            id="fraga"
            ref={inputRef}
            className="composer__input"
            rows={1}
            placeholder="Fråga om föreningens dokument…"
            value={question}
            disabled={busy}
            onChange={(event) => {
              setQuestion(event.target.value)
              grow(event.target)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault()
                void ask()
              }
            }}
          />
          <button
            type="button"
            className="composer__send"
            onClick={() => void ask()}
            disabled={!canSend}
            aria-label="Skicka frågan"
          >
            <SendIcon />
          </button>
        </div>
        {!online && <p className="composer__hint">Du är offline. Frågor kräver uppkoppling.</p>}
      </div>
    </>
  )
}
