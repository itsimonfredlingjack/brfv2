/* A question that was typed but never answered — because the session had
 * expired underneath it.
 *
 * Losing it is a small data loss with an outsized cost: it happens exactly
 * when someone is mid-conversation with another person, and retyping in
 * front of them is the moment the tool stops feeling dependable.
 *
 * In-memory only, not persisted: this is the user's own unsent text, it
 * only needs to survive a re-login within the same app session, and — like
 * the PWA's sessionStorage choice — should not outlive it. Bound to the
 * user who typed it, so a shared phone where one board member's session
 * expires and a different one signs in does not hand the second person the
 * first person's half-finished question. */

interface Pending {
  userId: string
  question: string
}

let pending: Pending | null = null

export function rememberPendingQuestion(userId: string, question: string): void {
  if (!userId || !question.trim()) return
  pending = { userId, question }
}

/** The pending question, but only for the user who typed it. Consumed
 * either way, so a question left by someone else is discarded rather than
 * lingering. */
export function takePendingQuestion(userId: string): string {
  const current = pending
  pending = null
  if (!current || current.userId !== userId) return ''
  return current.question
}

export function clearPendingQuestion(): void {
  pending = null
}
