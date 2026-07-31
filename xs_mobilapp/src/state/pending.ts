/* A question that was typed but never answered — because the session had
 * expired underneath it.
 *
 * Losing it is a small data loss with an outsized cost: it happens exactly
 * when someone is mid-conversation with another person, and retyping in
 * front of them is the moment the tool stops feeling dependable.
 *
 * sessionStorage, not localStorage: this is the user's own text, it only has
 * to survive a re-login in the same tab, and it should not outlive the tab.
 *
 * Bound to the user who typed it. A shared phone where one board member's
 * session expires and a different one signs in must not hand the second
 * person the first person's half-finished question.
 */

const KEY = 'kalla.pendingQuestion'

interface Pending {
  userId: string
  question: string
}

export function rememberPendingQuestion(userId: string, question: string): void {
  try {
    if (!userId || !question.trim()) return
    sessionStorage.setItem(KEY, JSON.stringify({ userId, question } satisfies Pending))
  } catch {
    // Storage unavailable — the question is simply not restored.
  }
}

/** The pending question, but only for the user who typed it. Consumed either
 * way, so a question left by someone else is discarded rather than lingering. */
export function takePendingQuestion(userId: string): string {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return ''
    sessionStorage.removeItem(KEY)
    const parsed = JSON.parse(raw) as Partial<Pending>
    if (!parsed || parsed.userId !== userId || typeof parsed.question !== 'string') return ''
    return parsed.question
  } catch {
    return ''
  }
}

export function clearPendingQuestion(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // nothing to clear
  }
}
