const time = new Intl.DateTimeFormat('sv-SE', { hour: '2-digit', minute: '2-digit' })
const dayTime = new Intl.DateTimeFormat('sv-SE', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const day = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'long', year: 'numeric' })

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
