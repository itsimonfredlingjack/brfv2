import { useState } from 'react'
import type { ReactNode } from 'react'

import type { Citation, Task, TaskBoard, TaskEvent } from '../api/types'
import { formatTimestamp } from '../lib/format'
import {
  OVERDUE_LABEL,
  TRAIL_HEAD,
  changeSentence,
  dueSentence,
  eventName,
  isUnassigned,
  originSentence,
  responsibleLabel,
  statusLabel,
  stopReason,
  trail,
} from '../lib/tasks'
import { CitationChip } from './CitationChip'
import { AlertIcon } from './icons'

/**
 * One piece of work the association has taken on, read-only.
 *
 * The card answers, in order, the four questions asked of a task in a meeting:
 * what, by when, who, and where it came from — then the evidence it was
 * created out of, then everything that has happened to it. The history is last
 * because it is the longest, and first among equals in importance: "who moved
 * the deadline and when" is the question that gets asked afterwards, and it is
 * the reason this domain exists rather than a shared notebook.
 *
 * Late is stated in words. A red edge alone would leave the one state that
 * matters legible only to people who can see red on white.
 */
export function TaskCard({
  board,
  task,
  onOpenCitation,
}: {
  board: TaskBoard
  task: Task
  onOpenCitation: (citation: Citation) => void
}) {
  const reason = stopReason(task)

  return (
    <article
      className={`task task--${task.status}${task.overdue ? ' task--overdue' : ''}`}
      data-testid="task"
      data-status={task.status}
      data-overdue={task.overdue ? 'true' : 'false'}
    >
      <div className="task__head">
        <h3 className="task__title">{task.title}</h3>
        {/* Always, unlike a watch's: three of the five statuses are active
            work, and they are three different things for a board to do. */}
        <span className={`chip task__status task__status--${task.status}`}>
          {statusLabel(board, task)}
        </span>
      </div>

      <p className="task__due" data-testid="task-due">
        {task.overdue && (
          <span className="chip chip--overdue">
            <AlertIcon size={14} />
            {OVERDUE_LABEL}
          </span>
        )}
        <span>{dueSentence(task)}</span>
      </p>

      {task.description && <p className="task__description">{task.description}</p>}

      {reason && (
        <p className="task__reason" data-testid="task-reason">
          <span className="task__reason-label">
            {task.status === 'blocked' ? 'Blockerad därför att' : 'Avbruten därför att'}:
          </span>{' '}
          {reason}
        </p>
      )}

      <dl className="facts__list task__meta">
        <MetaRow
          term="Ansvarig"
          value={responsibleLabel(task)}
          quiet={isUnassigned(task)}
          testId="task-responsible"
        />
        <MetaRow term="Kommer från" value={originSentence(board, task)} testId="task-origin" />
        {/* The citations below name the document and the page they were read
            from, so this row would repeat it. It exists for the case where
            there is no passage to open — then the document is the only thing
            standing between the work and a bare assertion. */}
        {task.citations.length === 0 && task.source_document_name && (
          <MetaRow term="Källa" value={task.source_document_name} />
        )}
      </dl>

      <Citations citations={task.citations} onOpenCitation={onOpenCitation} />

      <Trail board={board} task={task} />
    </article>
  )
}

function MetaRow({
  term,
  value,
  quiet,
  testId,
}: {
  term: string
  value: ReactNode
  quiet?: boolean
  testId?: string
}) {
  return (
    <div className="facts__row">
      <dt className="facts__term">{term}</dt>
      <dd className={`facts__value${quiet ? ' watch__unassigned' : ''}`} data-testid={testId}>
        {value}
      </dd>
    </div>
  )
}

/** The passage the work was created out of. Held here rather than in the
 * screen so "sources I already opened" survives closing the sheet. */
function Citations({
  citations,
  onOpenCitation,
}: {
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}) {
  const [visited, setVisited] = useState<ReadonlySet<number>>(() => new Set())

  if (citations.length === 0) return null

  return (
    <div className="task__citations" data-testid="task-citations">
      <div className="label">{citations.length === 1 ? 'Källa' : 'Källor'}</div>
      {citations.map((citation, index) => (
        <CitationChip
          key={`${citation.chunk_id}-${index}`}
          citation={citation}
          visited={visited.has(index)}
          onOpen={() => {
            setVisited((current) => new Set(current).add(index))
            onOpenCitation(citation)
          }}
        />
      ))}
    </div>
  )
}

/**
 * Everything that has happened to the task, newest first.
 *
 * A long trail is folded, never truncated: the most recent few stand open and
 * the rest sit behind a control that says how many there are. Dropping the
 * older half would quietly remove the part of the record somebody is most
 * likely to be looking for.
 */
function Trail({ board, task }: { board: TaskBoard; task: Task }) {
  const events = trail(task)
  if (events.length === 0) return null

  const recent = events.slice(0, TRAIL_HEAD)
  const older = events.slice(TRAIL_HEAD)

  return (
    <section className="task__trail" data-testid="task-trail">
      <div className="label">Historik</div>
      <ul className="trail">
        {recent.map((event) => (
          <TrailEvent key={event.id} board={board} event={event} />
        ))}
      </ul>

      {older.length > 0 && (
        <details className="disclosure">
          <summary className="disclosure__summary" data-testid="trail-more">
            Visa {older.length} äldre {older.length === 1 ? 'händelse' : 'händelser'}
          </summary>
          <ul className="trail">
            {older.map((event) => (
              <TrailEvent key={event.id} board={board} event={event} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function TrailEvent({ board, event }: { board: TaskBoard; event: TaskEvent }) {
  const change = changeSentence(board, event)

  return (
    <li className="trail__event" data-testid="trail-event" data-kind={event.kind}>
      <div className="trail__line">
        <span className="chip trail__kind">{eventName(event)}</span>
        <span className="trail__who">{event.by}</span>
        <span aria-hidden="true">·</span>
        <time className="trail__when" dateTime={event.at}>
          {formatTimestamp(event.at)}
        </time>
      </div>
      {change && <div className="trail__change">{change}</div>}
      {event.note && <p className="trail__note">”{event.note}”</p>}
    </li>
  )
}
