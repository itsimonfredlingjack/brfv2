import { beforeEach, describe, expect, it } from 'vitest'

import { clearPendingQuestion, rememberPendingQuestion, takePendingQuestion } from './pending'

/* A question survives a session expiry so nobody has to retype it while
 * someone is standing there waiting. It must not survive into a DIFFERENT
 * person's session on the same phone. */

const ANNA = 'user-anna'
const BO = 'user-bo'
const QUESTION = 'Vad krävs för att hyra ut sin lägenhet i andra hand?'

beforeEach(() => {
  sessionStorage.clear()
})

describe('pending question', () => {
  it('comes back for the user who typed it', () => {
    rememberPendingQuestion(ANNA, QUESTION)
    expect(takePendingQuestion(ANNA)).toBe(QUESTION)
  })

  it('is never handed to a different user on the same device', () => {
    rememberPendingQuestion(ANNA, QUESTION)
    expect(takePendingQuestion(BO)).toBe('')
  })

  it('is consumed even when the wrong user asks, so it cannot linger', () => {
    rememberPendingQuestion(ANNA, QUESTION)
    takePendingQuestion(BO)
    expect(takePendingQuestion(ANNA)).toBe('')
  })

  it('is consumed on read, so it is restored once and not again', () => {
    rememberPendingQuestion(ANNA, QUESTION)
    expect(takePendingQuestion(ANNA)).toBe(QUESTION)
    expect(takePendingQuestion(ANNA)).toBe('')
  })

  it('ignores blank questions and anonymous users', () => {
    rememberPendingQuestion(ANNA, '   ')
    expect(takePendingQuestion(ANNA)).toBe('')
    rememberPendingQuestion('', QUESTION)
    expect(takePendingQuestion('')).toBe('')
  })

  it('clears on demand — logout must leave nothing typed behind', () => {
    rememberPendingQuestion(ANNA, QUESTION)
    clearPendingQuestion()
    expect(takePendingQuestion(ANNA)).toBe('')
  })

  it('survives corrupt storage without throwing', () => {
    sessionStorage.setItem('kalla.pendingQuestion', 'inte-json{{{')
    expect(takePendingQuestion(ANNA)).toBe('')
  })

  it('ignores a stored value that is not shaped like a pending question', () => {
    sessionStorage.setItem('kalla.pendingQuestion', JSON.stringify({ userId: ANNA }))
    expect(takePendingQuestion(ANNA)).toBe('')
  })
})
