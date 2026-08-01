import { useState } from 'react'
import type { ReactNode } from 'react'

import type { Citation, UnresolvedObligation, Watch, WatchBoard } from '../api/types'
import { formatDay } from '../lib/format'
import {
  bucketLabel,
  dueSentence,
  isUnassigned,
  kindLabel,
  recurrenceLabel,
  responsibleLabel,
  statusLabel,
} from '../lib/watches'
import { CitationChip } from './CitationChip'
import { AlertIcon } from './icons'

/**
 * One dated obligation, read-only.
 *
 * The title is already an instruction — the backend writes "Säg upp eller
 * ompröva avtalet senast …" rather than "Uppsägningstid" — so the card's job
 * is to answer the three questions a board member asks next: when, who, and
 * says who. The date and how far off it is come first because that is the
 * reason to look; the passage the date was read from comes last because it is
 * the reason to believe it.
 *
 * Late is stated in words. A red edge alone would leave the one state that
 * matters legible only to people who can see red on white.
 */
export function WatchCard({
  board,
  watch,
  onOpenCitation,
}: {
  board: WatchBoard
  watch: Watch
  onOpenCitation: (citation: Citation) => void
}) {
  const overdue = watch.bucket === 'overdue'
  // A human moved the date off what the contract's own arithmetic gives. Both
  // are kept on the card: that disagreement is the record.
  const adjusted = watch.due_date !== watch.derived_due_date

  return (
    <article
      className={`watch watch--${watch.bucket}`}
      data-testid="watch"
      data-bucket={watch.bucket}
      data-status={watch.status}
    >
      <div className="watch__head">
        <h3 className="watch__title">{watch.title}</h3>
        {/* Only the ones nobody has taken on say so. Inside a bucket every
            watch is approved, and a badge repeating that on every card is
            noise; on a proposal it is the whole point. */}
        {watch.status !== 'approved' && (
          <span className="chip watch__status">{statusLabel(board, watch)}</span>
        )}
      </div>

      <p className="watch__due" data-testid="watch-due">
        {overdue && (
          <span className="chip chip--overdue">
            <AlertIcon size={14} />
            {bucketLabel(board, 'overdue')}
          </span>
        )}
        <span>{dueSentence(watch)}</span>
      </p>

      <dl className="facts__list watch__meta">
        <MetaRow term="Typ" value={kindLabel(board, watch)} />
        <MetaRow
          term="Ansvarig"
          value={responsibleLabel(watch)}
          quiet={isUnassigned(watch)}
          testId="watch-responsible"
        />
        {watch.recurrence !== 'none' && <MetaRow term="Återkommer" value={recurrenceLabel(watch)} />}
        {/* The citation below names the document and the page it was read
            from, so this row would repeat it. It exists for the case where
            there is no passage to open — then the document is the only thing
            standing between the date and a bare assertion. */}
        {watch.citations.length === 0 && (
          <MetaRow term="Källa" value={watch.source_document_name || '—'} />
        )}
      </dl>

      {watch.derivation && (
        <p className="watch__derivation" data-testid="watch-derivation">
          <span className="watch__derivation-label">Datumet är räknat fram så här:</span>{' '}
          {watch.derivation}
          {adjusted && ` Datumet är sedan ändrat från ${formatDay(watch.derived_due_date)}.`}
        </p>
      )}

      <Citations citations={watch.citations} onOpenCitation={onOpenCitation} />
    </article>
  )
}

/**
 * A time limit that was read but could not be turned into a date.
 *
 * Deliberately shaped like a watch and deliberately not one: no date, no
 * bucket, no countdown. It says what was found and why it stops there, because
 * "we found nothing" and "we found something we cannot date" are different
 * answers, and only the second one a board can do anything about.
 */
export function UnresolvedCard({
  obligation,
  onOpenCitation,
}: {
  obligation: UnresolvedObligation
  onOpenCitation: (citation: Citation) => void
}) {
  return (
    <article className="unresolved" data-testid="unresolved">
      <h3 className="unresolved__what">{obligation.what}</h3>
      <p className="unresolved__why" data-testid="unresolved-why">
        {obligation.why}
      </p>

      {obligation.citations.length === 0 && (
        <dl className="facts__list watch__meta">
          <MetaRow term="Källa" value={obligation.source_document_name || '—'} />
        </dl>
      )}

      <Citations citations={obligation.citations} onOpenCitation={onOpenCitation} />
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

/** The passage the obligation was read from. Held here rather than in the
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
    <div className="watch__citations" data-testid="watch-citations">
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
