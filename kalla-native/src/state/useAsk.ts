import { useEffect, useRef, useState } from 'react'

import { ApiError, OfflineError, api } from '../api/client'
import type { AskResponse, RetrievalHit } from '../api/types'
import { metaCache, newEntryId, saveEntry } from './journal'
import type { JournalEntry } from './journal'
import { rememberPendingQuestion } from './pending'
import { useSession } from './session'

export type AskStage = 'retrieving' | 'generating'

/** How long the "Söker i N dokument…" stage is shown before the copy moves
 * on to generation. Retrieval really is the fast part; this is an honest
 * description of what is happening, not a fake progress bar — the same
 * number the PWA proved (xs_mobilapp/src/screens/Fraga.tsx). */
const RETRIEVAL_COPY_MS = 1400

export interface AskFlowState {
  step: 'asking' | 'done' | 'failed'
  stage: AskStage
  documentCount: number | null
  entry: JournalEntry | null
  error: string | null
}

/** Best-scoring retrieval hit per document, ranked — the "corpus genuinely
 * searched" evidence shown by the living index and, on a refusal, by
 * "Högen genomsöktes ändå". Always real data, never fabricated mid-search:
 * the backend answers in one call, so there is nothing to stream. */
export function topHitsByDocument(retrieval: RetrievalHit[], limit = 4): RetrievalHit[] {
  const best = new Map<string, RetrievalHit>()
  for (const hit of retrieval) {
    const current = best.get(hit.document_id)
    if (!current || hit.confidence > current.confidence) best.set(hit.document_id, hit)
  }
  return Array.from(best.values())
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, limit)
}

/**
 * Runs one question end to end: honest two-stage wait copy while the real
 * `POST /ask` is in flight, then a journal write, then the caller renders
 * the grounded/refusal outcome. Session expiry preserves the question so
 * retyping in front of another person is never required (xs_mobilapp
 * lib/pending.ts precedent).
 */
export function useAsk(brfId: string, question: string) {
  const { reportUnauthorized, user } = useSession()
  const [state, setState] = useState<AskFlowState>({
    step: 'asking',
    stage: 'retrieving',
    documentCount: null,
    entry: null,
    error: null,
  })
  const aliveRef = useRef(true)
  const attemptRef = useRef(0)
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    metaCache.documents
      .read(brfId)
      .then((cached) => {
        if (!cancelled && cached) setState((s) => ({ ...s, documentCount: cached.length }))
      })
      .catch(() => {})
    api
      .listDocuments(brfId)
      .then((fresh) => {
        if (cancelled) return
        setState((s) => ({ ...s, documentCount: fresh.length }))
        void metaCache.documents.write(brfId, fresh).catch(() => {})
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [brfId])

  useEffect(() => {
    const attempt = ++attemptRef.current
    // Resetting to the loading state for a NEW async operation keyed by
    // `question` — the documented exception to "don't setState in an
    // effect" (an effect synchronizing with an external system, here the
    // network request started right below).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((s) => ({ ...s, step: 'asking', stage: 'retrieving', entry: null, error: null }))
    const toGenerating = setTimeout(() => {
      if (attemptRef.current === attempt) setState((s) => ({ ...s, stage: 'generating' }))
    }, RETRIEVAL_COPY_MS)

    async function run() {
      try {
        const response: AskResponse = await api.ask(brfId, question)
        if (!aliveRef.current || attemptRef.current !== attempt) return
        const entry: JournalEntry = {
          id: newEntryId(),
          brfId,
          question,
          createdAt: Date.now(),
          answer: response.answer,
          refusal: response.refusal,
          refusalReason: response.refusal_reason,
          warning: response.warning,
          citations: response.citations,
          rejected: response.rejected_citations,
          retrieval: response.retrieval,
          provider: response.provider,
          model: response.model,
        }
        await saveEntry(entry)
        if (!aliveRef.current || attemptRef.current !== attempt) return
        setState((s) => ({ ...s, step: 'done', entry }))
      } catch (err) {
        if (!aliveRef.current || attemptRef.current !== attempt) return
        if (err instanceof ApiError && err.status === 401) {
          rememberPendingQuestion(user?.id ?? '', question)
          reportUnauthorized()
          return
        }
        const message =
          err instanceof OfflineError
            ? 'Du är offline. Frågor kräver uppkoppling.'
            : err instanceof ApiError && err.status === 0
              ? 'Servern gick inte att nå.'
              : err instanceof Error
                ? err.message
                : 'Frågan kunde inte skickas.'
        setState((s) => ({ ...s, step: 'failed', error: message }))
      }
    }

    void run()
    return () => clearTimeout(toGenerating)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brfId, question, retryNonce])

  const retry = () => setRetryNonce((n) => n + 1)

  return { ...state, retry }
}
