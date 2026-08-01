import type { Recurrence, Watch, WatchBoard, WatchBucket, WatchKind, WatchStatus } from '../api/types'
import { formatDay } from './format'

/* Copy and ordering for the watch board.
 *
 * The backend decides everything of substance — which bucket a watch is in,
 * how many days are left, what the Swedish labels are. What lives here is only
 * how that is *said* on a phone, plus fallbacks for the day the backend grows
 * a kind or a status this build has never seen. A client that re-buckets a
 * deadline is a second calendar, and two calendars disagree.
 */

/**
 * The order a board reads them in: what is late, then what is close, then what
 * is far off, then the rhythm. Declared here rather than taken from the key
 * order of `buckets`, because JSON object order is an implementation detail
 * and this is a decision.
 */
export const BUCKET_ORDER: WatchBucket[] = ['overdue', 'soon', 'later', 'recurring']

/** Only used when the server sends a bucket without a label. */
const BUCKET_FALLBACK: Record<WatchBucket, string> = {
  overdue: 'Försenat',
  soon: 'Snart',
  later: 'Senare',
  recurring: 'Återkommande',
}

const KIND_FALLBACK: Record<WatchKind, string> = {
  notice_deadline: 'Uppsägning',
  expiry: 'Avtalet upphör',
  warranty: 'Garanti',
  inspection: 'Besiktning eller kontroll',
  recurring_obligation: 'Återkommande skyldighet',
}

const STATUS_FALLBACK: Record<WatchStatus, string> = {
  proposed: 'väntar på godkännande',
  approved: 'bevakas',
  dismissed: 'avfärdad',
  done: 'avklarad',
}

const trimmed = (value: string | undefined): string => (value ?? '').trim()

export function bucketLabel(board: WatchBoard, bucket: WatchBucket): string {
  return trimmed(board.bucketLabels[bucket]) || BUCKET_FALLBACK[bucket] || bucket
}

export function kindLabel(board: WatchBoard, watch: Watch): string {
  return (
    trimmed(watch.kind_label) || trimmed(board.kindLabels[watch.kind]) || KIND_FALLBACK[watch.kind] || watch.kind
  )
}

export function statusLabel(board: WatchBoard, watch: Watch): string {
  return (
    trimmed(watch.status_label) ||
    trimmed(board.statusLabels[watch.status]) ||
    STATUS_FALLBACK[watch.status] ||
    watch.status
  )
}

/**
 * Who is on it — or the plain admission that nobody is.
 *
 * An empty responsible must never render as a blank cell: a blank reads as
 * "someone, presumably", and the whole value of a watch is that a person is
 * named or visibly is not.
 */
export const UNASSIGNED = 'ej utsedd'

export function responsibleLabel(watch: Watch): string {
  return watch.responsible.trim() || UNASSIGNED
}

export function isUnassigned(watch: Watch): boolean {
  return watch.responsible.trim() === ''
}

/* A straight reading of the enum, not a judgement about it — the backend has
 * no Swedish for these, and "recurrence: yearly" is not something to put in
 * front of a board member. */
const RECURRENCE_LABELS: Record<Recurrence, string> = {
  none: '',
  monthly: 'varje månad',
  quarterly: 'varje kvartal',
  yearly: 'varje år',
  biennial: 'vartannat år',
  triennial: 'vart tredje år',
}

export function recurrenceLabel(watch: Watch): string {
  return RECURRENCE_LABELS[watch.recurrence] ?? watch.recurrence
}

const days = (count: number): string => `${count} ${count === 1 ? 'dag' : 'dagar'}`

/**
 * The date, and how far away it is, in words.
 *
 * `days_left` is counted from the server's own today, which is why the screen
 * states that day: "om 60 dagar" means nothing without knowing from when.
 */
export function dueSentence(watch: Watch): string {
  const date = formatDay(watch.due_date)
  const left = watch.days_left
  if (left === null) return date
  if (left < 0) return `${date} · ${days(-left)} sedan`
  if (left === 0) return `${date} · i dag`
  return `${date} · om ${days(left)}`
}

/** True when the board has nothing at all to say — as opposed to nothing in
 * the buckets, which is a different sentence. */
export function boardIsEmpty(board: WatchBoard): boolean {
  return (
    board.proposed.length === 0 &&
    board.unresolved.length === 0 &&
    BUCKET_ORDER.every((bucket) => board.buckets[bucket].length === 0)
  )
}
