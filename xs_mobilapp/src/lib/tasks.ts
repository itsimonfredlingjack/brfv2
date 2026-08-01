import type { Task, TaskBoard, TaskEvent, TaskOriginKind, TaskStatus } from '../api/types'
import { formatDay } from './format'

/* Copy and ordering for the task list.
 *
 * The backend decides everything of substance — which tasks are active, what
 * is overdue, how many days are left, what the Swedish labels are, and the
 * order the active list is read in. What lives here is only how that is *said*
 * on a phone, plus fallbacks for the day the backend grows a status, an origin
 * or an event kind this build has never seen.
 *
 * The same rule the watch board follows, for the same reason: a client that
 * re-decides what is late is a second calendar, and two calendars disagree.
 */

const STATUS_FALLBACK: Record<TaskStatus, string> = {
  open: 'att göra',
  in_progress: 'pågår',
  blocked: 'blockerad',
  done: 'klar',
  cancelled: 'avbruten',
}

const ORIGIN_FALLBACK: Record<TaskOriginKind, string> = {
  finding: 'Fakturagranskning',
  watch: 'Bevakning',
  source_event: 'Inkommande post',
  manual: 'Skapad för hand',
}

const trimmed = (value: string | undefined): string => (value ?? '').trim()

function statusWord(board: TaskBoard, status: string): string {
  return (
    trimmed(board.statusLabels[status]) || STATUS_FALLBACK[status as TaskStatus] || status
  )
}

export function statusLabel(board: TaskBoard, task: Task): string {
  return trimmed(task.status_label) || statusWord(board, task.status)
}

/** Where the work came from, and what that thing said at the time. */
export function originSentence(board: TaskBoard, task: Task): string {
  const kind =
    trimmed(task.origin.kind_label) ||
    trimmed(board.originLabels[task.origin.kind]) ||
    ORIGIN_FALLBACK[task.origin.kind] ||
    task.origin.kind
  const label = trimmed(task.origin.label)
  return label ? `${kind} · ${label}` : kind
}

/**
 * Who is on it — or the plain admission that nobody is.
 *
 * Deliberately the same word the watch board uses. An empty responsible must
 * never render as a blank cell: a blank reads as "someone, presumably", and
 * the whole value of a task is that a person is named or visibly is not.
 */
export const UNASSIGNED = 'ej utsedd'

export function responsibleLabel(task: Task): string {
  return task.responsible.trim() || UNASSIGNED
}

export function isUnassigned(task: Task): boolean {
  return task.responsible.trim() === ''
}

/** Said in words on the card. The endpoint sends no label for it — this is
 * the one piece of vocabulary the client owns, because `overdue` is a boolean
 * on the wire and a red edge alone would leave the state that matters legible
 * only to people who can see red on white. */
export const OVERDUE_LABEL = 'Försenad'

/** Not urgent, not late — simply unscheduled, which is a different thing to
 * tell someone than a missing value. */
export const NO_DUE_DATE = 'Inget datum satt'

const days = (count: number): string => `${count} ${count === 1 ? 'dag' : 'dagar'}`

/**
 * The date, and how far away it is, in words.
 *
 * `days_left` is counted from the server's own today, which is why the screen
 * states that day: "om 12 dagar" means nothing without knowing from when.
 *
 * The countdown is only spoken for work that is still open. A finished task's
 * date is history, and "42 dagar sedan" under something already delivered
 * reads as a reproach for a deadline that was met.
 */
export function dueSentence(task: Task): string {
  if (!task.due_date) return NO_DUE_DATE
  const date = formatDay(task.due_date)
  if (!task.active || task.days_left === null) return date
  const left = task.days_left
  if (left < 0) return `${date} · ${days(-left)} sedan`
  if (left === 0) return `${date} · i dag`
  return `${date} · om ${days(left)}`
}

/**
 * Why the work stopped.
 *
 * The backend requires a stated reason for exactly the two statuses that need
 * one — blocked and cancelled — and keeps it on the event that set them. A
 * card that shows "avbruten" without the sentence shows the half of the record
 * that is no use to anybody.
 */
export function stopReason(task: Task): string {
  if (task.status !== 'blocked' && task.status !== 'cancelled') return ''
  for (let index = task.activity.length - 1; index >= 0; index -= 1) {
    const event = task.activity[index]!
    if (event.kind === 'status_changed' && event.to_value === task.status) {
      return event.note.trim()
    }
  }
  return ''
}

export function eventName(event: TaskEvent): string {
  return trimmed(event.kind_label) || event.kind
}

const dayOrNothing = (iso: string): string => (iso.trim() ? formatDay(iso) : 'inget datum')

/**
 * What changed, from what to what.
 *
 * Only for the event kinds that carry a before and an after. `created` and
 * `noted` say everything in their label and their note; `edited` records only
 * that the text moved, and the record does not say from what — inventing a
 * sentence for it here would be precision nobody wrote down.
 */
export function changeSentence(board: TaskBoard, event: TaskEvent): string {
  if (event.kind === 'status_changed') {
    return `från ${statusWord(board, event.from_value)} till ${statusWord(board, event.to_value)}`
  }
  if (event.kind === 'assigned') {
    const from = event.from_value.trim() || UNASSIGNED
    const to = event.to_value.trim() || UNASSIGNED
    return `från ${from} till ${to}`
  }
  if (event.kind === 'due_changed') {
    return `från ${dayOrNothing(event.from_value)} till ${dayOrNothing(event.to_value)}`
  }
  return ''
}

/** Newest first. The backend appends, so the trail arrives oldest first; what
 * a board asks in a meeting is what happened last. */
export function trail(task: Task): TaskEvent[] {
  return [...task.activity].reverse()
}

/** How much of the trail stands open. Three covers the usual "created,
 * assigned, and the thing that just happened" without turning a card into a
 * log — the rest is one tap away and never dropped. */
export const TRAIL_HEAD = 3

/**
 * The two numbers a board actually acts on, as a sentence rather than a row of
 * bare figures — "3" beside a word is a number a screen reader reads as a
 * number.
 */
export function countsSentence(counts: TaskBoard['counts']): string {
  if (counts.active === 0) return 'Inget aktivt arbete just nu.'

  const active = `${counts.active} ${counts.active === 1 ? 'aktiv uppgift' : 'aktiva uppgifter'}`
  const parts: string[] = []
  if (counts.overdue > 0) {
    parts.push(`${counts.overdue} ${counts.overdue === 1 ? 'är försenad' : 'är försenade'}`)
  }
  if (counts.unassigned > 0) parts.push(`${counts.unassigned} saknar ansvarig`)

  if (parts.length === 0) return `${active}. Ingen är försenad och alla har en ansvarig.`
  return `${active}, varav ${parts.join(' och ')}.`
}

/** True when there is nothing at all to say — as opposed to nothing active,
 * which is a different sentence. */
export function boardIsEmpty(board: TaskBoard): boolean {
  return board.active.length === 0 && board.done.length === 0 && board.cancelled.length === 0
}
