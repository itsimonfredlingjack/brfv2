const time = new Intl.DateTimeFormat('sv-SE', { hour: '2-digit', minute: '2-digit' })
const dayTime = new Intl.DateTimeFormat('sv-SE', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const day = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'long', year: 'numeric' })
const stamp = new Intl.DateTimeFormat('sv-SE', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** "14:32" today, "3 mars 14:32" otherwise. */
export function formatMoment(timestamp: number): string {
  const date = new Date(timestamp)
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  return sameDay ? time.format(date) : dayTime.format(date)
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : day.format(date)
}

/**
 * "30 september 2026" out of a bare `YYYY-MM-DD`.
 *
 * Separate from formatDate because a deadline is a calendar day, not an
 * instant. `new Date('2026-09-30')` is parsed as UTC midnight, which renders
 * as the 29th on any phone west of London — a day the contract never mentions.
 * The parts are read out and rebuilt in local time instead.
 */
export function formatDay(iso: string): string {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!parts) return formatDate(iso)
  const date = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
  return Number.isNaN(date.getTime()) ? '—' : day.format(date)
}

/** "12 maj 2026 14:32". For a record of what a person decided, where the hour
 * is part of the record and not decoration. */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : stamp.format(date)
}

/** "Gemma 4 12B (självhostad)" — provenance, not decoration. */
export function formatProvenance(provider: string, model: string): string {
  const providerLabel: Record<string, string> = {
    selfhosted: 'självhostad',
    anthropic: 'Anthropic',
    cli: 'Claude CLI',
    scripted: 'skriptad testmodell',
    fake: 'testmodell',
  }
  const label = providerLabel[provider] ?? provider
  if (!model) return label ? `Genererat av ${label}` : ''
  return `Genererat av ${model} (${label})`
}
