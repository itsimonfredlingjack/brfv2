import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, WatchBoard } from '../api/types'
import { KallaSheet } from '../components/KallaSheet'
import type { KallaTarget } from '../components/KallaSheet'
import { Notice } from '../components/Notice'
import { UnresolvedCard, WatchCard } from '../components/Watch'
import { formatDay } from '../lib/format'
import { BUCKET_ORDER, boardIsEmpty, bucketLabel } from '../lib/watches'

interface LoadProblem {
  tone: 'refusal' | 'error'
  title: string
  body: string
}

function problemFor(err: unknown): LoadProblem {
  if (err instanceof OfflineError) {
    return {
      tone: 'error',
      title: 'Du är offline',
      body: 'Bevakningarna ligger inte på telefonen. De hämtas när du är uppkopplad igen.',
    }
  }
  if (err instanceof ApiError && err.status === 404) {
    return {
      tone: 'refusal',
      title: 'Bevakningar finns inte här',
      body: 'Den här installationen bevakar inga datum ur föreningens avtal.',
    }
  }
  return {
    tone: 'error',
    title: 'Bevakningarna kunde inte hämtas',
    body: 'Föreningens bevakningar gick inte att läsa just nu.',
  }
}

/**
 * The association's dated obligations, read-only.
 *
 * The four buckets, the labels and the countdown all arrive computed: "snart"
 * is a function of each watch's own reminder lead time, and a phone that
 * worked it out for itself would be a second calendar quietly disagreeing with
 * the desktop. This screen groups, orders and says.
 *
 * Proposals are kept below the buckets, under a heading that names them as
 * proposals, because a suggestion a rule engine derived is not an obligation
 * the association has taken on — and a list that blends the two commits people
 * to things nobody approved.
 *
 * Deliberately not cached on the device, the same decision the Granskning view
 * made: what a phone holds is documented as exactly two derived things
 * (README) that logout and förening switch erase. A third store, this one of
 * the association's deadlines and who is answerable for them, would be a new
 * promise made quietly.
 */
export function Bevakningar({ brfId }: { brfId: string }) {
  const [board, setBoard] = useState<WatchBoard | null>(null)
  const [problem, setProblem] = useState<LoadProblem | null>(null)
  const [target, setTarget] = useState<KallaTarget | null>(null)

  useEffect(() => {
    let cancelled = false

    api
      .listWatches(brfId)
      .then((next) => {
        if (cancelled) return
        setBoard(next)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setProblem(problemFor(err))
      })

    return () => {
      cancelled = true
    }
  }, [brfId])

  const openCitation = (citation: Citation) => {
    setTarget({
      documentId: citation.document_id,
      documentName: citation.document_name,
      page: citation.page,
      citation,
    })
  }

  return (
    <>
      <div className="screen">
        <h1 className="screen__title">Bevakningar</h1>
        <p className="screen__lede">
          Datum som föreningens egna avtal binder styrelsen vid, med passagen varje datum är läst
          ur.
        </p>
        <p className="readonly-note" data-testid="readonly-note">
          Läsvy. Att godkänna, ändra eller markera en bevakning som avklarad görs i webbappen.
        </p>

        {problem && (
          <div style={{ marginTop: 'var(--s5)' }}>
            <Notice tone={problem.tone} title={problem.title}>
              {problem.body}
            </Notice>
          </div>
        )}

        {board === null && !problem && (
          <div className="list">
            {[0, 1].map((index) => (
              <div key={index} className="skeleton" style={{ height: 148 }} />
            ))}
          </div>
        )}

        {board !== null && boardIsEmpty(board) && (
          <div className="empty">
            <div className="empty__title">Inga bevakningar ännu</div>
            <p className="empty__body">
              Föreningens avtal har inte gett några datum att bevaka. Avtal läses in och bevakningar
              godkänns i webbappen.
            </p>
          </div>
        )}

        {board !== null && !boardIsEmpty(board) && (
          <>
            {/* Everything below is counted from the server's today. "Om 60
                dagar" is meaningless without it, and a phone left open over
                a weekend would otherwise quietly go stale. */}
            <p className="watch-asof" data-testid="watch-asof">
              Räknat från {formatDay(board.today)}
            </p>

            {BUCKET_ORDER.map((bucket) => {
              const rows = board.buckets[bucket]
              if (rows.length === 0) return null
              return (
                <Group key={bucket} title={bucketLabel(board, bucket)} count={rows.length}>
                  {rows.map((watch) => (
                    <WatchCard
                      key={watch.id}
                      board={board}
                      watch={watch}
                      onOpenCitation={openCitation}
                    />
                  ))}
                </Group>
              )
            })}

            {board.proposed.length > 0 && (
              <Group
                title="Förslag, inte beslutade"
                count={board.proposed.length}
                note="Framräknat ur avtalen och ännu inte godkänt av någon. Föreningen har inte åtagit sig något av det här. Att godkänna, ändra datum eller utse ansvarig görs i webbappen."
              >
                {board.proposed.map((watch) => (
                  <WatchCard
                    key={watch.id}
                    board={board}
                    watch={watch}
                    onOpenCitation={openCitation}
                  />
                ))}
              </Group>
            )}

            {board.unresolved.length > 0 && (
              <Group
                title="Tidsvillkor utan datum"
                count={board.unresolved.length}
                note="Villkor som talar om tid, men där dagen inte gick att räkna fram. Det som saknas står inte i handlingen — och det är oftast något någon i föreningen vet."
              >
                {board.unresolved.map((obligation) => (
                  <UnresolvedCard
                    key={obligation.id}
                    obligation={obligation}
                    onOpenCitation={openCitation}
                  />
                ))}
              </Group>
            )}
          </>
        )}
      </div>

      {target && <KallaSheet brfId={brfId} target={target} onClose={() => setTarget(null)} />}
    </>
  )
}

function Group({
  title,
  count,
  note,
  children,
}: {
  title: string
  count: number
  note?: string
  children: ReactNode
}) {
  return (
    <section className="watch-group" data-testid="watch-group">
      <div className="watch-group__head">
        <h2 className="watch-group__title">{title}</h2>
        {/* A bare "3" beside a heading is a number a screen reader reads as a
            number. The noun is hidden, not omitted. */}
        <span className="watch-group__count">
          {count} <span className="visually-hidden">{count === 1 ? 'post' : 'poster'}</span>
        </span>
      </div>
      {note && <p className="watch-group__note">{note}</p>}
      <div className="list">{children}</div>
    </section>
  )
}
