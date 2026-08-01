import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, TaskBoard } from '../api/types'
import { KallaSheet } from '../components/KallaSheet'
import type { KallaTarget } from '../components/KallaSheet'
import { Notice } from '../components/Notice'
import { TaskCard } from '../components/Task'
import { formatDay } from '../lib/format'
import { boardIsEmpty, countsSentence } from '../lib/tasks'

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
      body: 'Uppgifterna ligger inte på telefonen. De hämtas när du är uppkopplad igen.',
    }
  }
  if (err instanceof ApiError && err.status === 404) {
    return {
      tone: 'refusal',
      title: 'Uppgifter finns inte här',
      body: 'Den här installationen håller inget register över föreningens arbete.',
    }
  }
  return {
    tone: 'error',
    title: 'Uppgifterna kunde inte hämtas',
    body: 'Föreningens uppgifter gick inte att läsa just nu.',
  }
}

/**
 * The work the association has taken on, read-only.
 *
 * The desktop is where a task is created and changed; this is where someone
 * reads what is outstanding, who owns it and what has happened to it — in a
 * meeting, with the source one tap away. Nothing here creates, assigns,
 * reschedules or comments, and the screen says so in one line rather than
 * leaving a reader hunting for a button that is not there.
 *
 * The active list is rendered in the server's order and is not re-sorted.
 * Overdue first, then by date, then the undated, is a judgement the backend
 * made once for both clients; a phone that ordered them for itself would be a
 * second opinion about what is urgent.
 *
 * Done and cancelled work is kept, because a task that existed is a record of
 * what the board decided to do and "did we actually deal with that?" is a real
 * question in a meeting. It is folded away under its own heading so it cannot
 * compete with outstanding work, and a cancelled task carries the reason it
 * was cancelled with it — a cancellation without its sentence is the half of
 * the record that is no use.
 *
 * Deliberately not cached on the device, the same decision Granskning and
 * Bevakningar made: what a phone holds is documented as exactly two derived
 * things (README) that logout and förening switch erase. A third store, this
 * one of who in the association owes what and by when, would be a new promise
 * made quietly.
 */
export function Uppgifter({ brfId }: { brfId: string }) {
  const [board, setBoard] = useState<TaskBoard | null>(null)
  const [problem, setProblem] = useState<LoadProblem | null>(null)
  const [target, setTarget] = useState<KallaTarget | null>(null)

  useEffect(() => {
    let cancelled = false

    api
      .listTasks(brfId)
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
        <h1 className="screen__title">Uppgifter</h1>
        <p className="screen__lede">
          Arbete föreningen tagit på sig: vem som har det, när det ska vara gjort och vad som hänt
          med det.
        </p>
        <p className="readonly-note" data-testid="readonly-note">
          Läsvy. Att lägga upp en uppgift, ändra status, utse ansvarig eller skriva i historiken
          görs i webbappen.
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
              <div key={index} className="skeleton" style={{ height: 196 }} />
            ))}
          </div>
        )}

        {board !== null && boardIsEmpty(board) && (
          <div className="empty">
            <div className="empty__title">Inga uppgifter ännu</div>
            <p className="empty__body">
              Föreningen har inte tagit på sig något arbete. Uppgifter skapas ur ett fynd, en
              bevakning eller inkommande post i webbappen.
            </p>
          </div>
        )}

        {board !== null && !boardIsEmpty(board) && (
          <>
            {/* Everything below is counted from the server's today. "Om 12
                dagar" is meaningless without it, and a phone left open over a
                weekend would otherwise quietly go stale. */}
            <p className="task-asof" data-testid="task-asof">
              Räknat från {formatDay(board.today)}
            </p>
            <p className="task-counts" data-testid="task-counts">
              {countsSentence(board.counts)}
            </p>

            {board.active.length > 0 && (
              <Group title="Aktiva uppgifter" count={board.active.length}>
                {board.active.map((task) => (
                  <TaskCard key={task.id} board={board} task={task} onOpenCitation={openCitation} />
                ))}
              </Group>
            )}

            {board.done.length > 0 && (
              <ClosedGroup title="Klara" count={board.done.length} testId="task-group-done">
                {board.done.map((task) => (
                  <TaskCard key={task.id} board={board} task={task} onOpenCitation={openCitation} />
                ))}
              </ClosedGroup>
            )}

            {board.cancelled.length > 0 && (
              <ClosedGroup
                title="Avbrutna"
                count={board.cancelled.length}
                testId="task-group-cancelled"
                note="Avbrutet arbete raderas aldrig. Att föreningen bestämde sig för något och sedan lät bli är också ett beslut, och varje avbruten uppgift bär skälet den avbröts med."
              >
                {board.cancelled.map((task) => (
                  <TaskCard key={task.id} board={board} task={task} onOpenCitation={openCitation} />
                ))}
              </ClosedGroup>
            )}
          </>
        )}
      </div>

      {target && <KallaSheet brfId={brfId} target={target} onClose={() => setTarget(null)} />}
    </>
  )
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="task-group" data-testid="task-group">
      <div className="task-group__head">
        <h2 className="task-group__title">{title}</h2>
        <Count count={count} />
      </div>
      <div className="list">{children}</div>
    </section>
  )
}

/** Finished and abandoned work, folded away.
 *
 * Closed rather than merely below: outstanding work is what the screen is for,
 * and a meeting that has to scroll past forty completed tasks to find the two
 * that are late is a meeting the screen made worse. The count stands open, so
 * "is there anything in there" never costs a tap. */
function ClosedGroup({
  title,
  count,
  note,
  testId,
  children,
}: {
  title: string
  count: number
  note?: string
  testId: string
  children: ReactNode
}) {
  return (
    <section className="task-group task-group--closed" data-testid={testId}>
      <details>
        <summary className="task-group__summary">
          <h2 className="task-group__title">{title}</h2>
          <Count count={count} />
        </summary>
        {note && <p className="task-group__note">{note}</p>}
        <div className="list">{children}</div>
      </details>
    </section>
  )
}

/* A bare "3" beside a heading is a number a screen reader reads as a number.
 * The noun is hidden, not omitted. */
function Count({ count }: { count: number }) {
  return (
    <span className="task-group__count">
      {count} <span className="visually-hidden">{count === 1 ? 'uppgift' : 'uppgifter'}</span>
    </span>
  )
}
