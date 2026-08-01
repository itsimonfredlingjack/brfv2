import type { AnchorStrength, FindingStatus, ReviewFinding, Verdict } from '../api/types'
import { formatTimestamp } from './format'

/* Copy and classification for a review finding.
 *
 * The backend decides everything of substance — the verdict, its Swedish
 * label, which facts are verified, what is uncertain. What lives here is only
 * how that is *said* on a phone, plus fallbacks for the day the backend grows
 * a value this build has never seen. A client that guesses a verdict is a
 * second opinion nobody asked for.
 */

/** Only used when `verdict_label` arrives empty; the backend fills it. */
const VERDICT_LABELS: Record<Verdict, string> = {
  matches: 'överensstämmer',
  possible_deviation: 'möjlig avvikelse',
  cannot_be_verified: 'kan inte verifieras',
}

/**
 * How a verdict is drawn. `grounded` is the only one that gets the verified
 * mark — a check next to "kan inte verifieras" would say the opposite of the
 * words beside it.
 */
export type VerdictTone = 'grounded' | 'deviation' | 'unknown'

const VERDICT_TONES: Record<Verdict, VerdictTone> = {
  matches: 'grounded',
  possible_deviation: 'deviation',
  cannot_be_verified: 'unknown',
}

export function verdictLabel(finding: ReviewFinding): string {
  const fromBackend = finding.verdict_label.trim()
  if (fromBackend) return fromBackend
  return VERDICT_LABELS[finding.verdict] ?? 'okänt utfall'
}

export function verdictTone(verdict: Verdict): VerdictTone {
  return VERDICT_TONES[verdict] ?? 'unknown'
}

/* The neuter forms: the subject is *ett fynd*. "Öppet" is not a softer word
 * than "öppen", it is the one that agrees with what it describes. */
const STATUS_LABELS: Record<FindingStatus, string> = {
  open: 'Öppet',
  approved: 'Godkänt',
  dismissed: 'Avfärdat',
  corrected: 'Korrigerat',
}

export function statusLabel(status: FindingStatus): string {
  return STATUS_LABELS[status] ?? status
}

/** `partial` is the backend's whole WEAK_STRENGTHS set. A weak anchor means
 * the two papers are probably, not certainly, about the same company. */
export function anchorIsWeak(strength: AnchorStrength | null): boolean {
  return strength === 'partial'
}

const ANCHOR_LABELS: Record<AnchorStrength, string> = {
  org_number: 'Kopplad på organisationsnummer',
  exact: 'Kopplad på leverantörens namn',
  alias: 'Kopplad via bekräftat alias',
  legal_form: 'Kopplad på namnet, med annan bolagsform',
  partial: 'Svag koppling till leverantören',
}

export function anchorLabel(strength: AnchorStrength | null): string {
  if (!strength) return 'Koppling till leverantören'
  return ANCHOR_LABELS[strength] ?? 'Koppling till leverantören'
}

/**
 * The human decision, as one line — or null while none has been taken.
 *
 * Written as a sentence about a person rather than a status badge, because
 * that is what it is: a record that someone at the association looked at this
 * and said something. The phone shows it; it cannot add to it.
 */
export function decisionSentence(finding: ReviewFinding): string | null {
  if (finding.status === 'open') return null

  const parts = [statusLabel(finding.status)]
  if (finding.decided_by) parts.push(`av ${finding.decided_by}`)
  if (finding.decided_at) parts.push(formatTimestamp(finding.decided_at))
  return parts.join(' ')
}
