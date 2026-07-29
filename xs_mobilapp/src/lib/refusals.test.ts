import { describe, expect, it } from 'vitest'

import type { RefusalReason, RejectReason } from '../api/types'
import { GROUNDING_PROMISE, refusalCopy, rejectCopy } from './refusals'

/** Every reason the backend can emit (backend/app/schemas.py RefusalReason). */
const ALL_REASONS: RefusalReason[] = [
  'no_documents',
  'low_relevance',
  'insufficient_data',
  'grounding_failed',
  'provider_error',
  'numeric_grounding_failed',
]

const ALL_REJECTS: RejectReason[] = [
  'quote_not_found',
  'provenance_mismatch',
  'bbox_out_of_bounds',
  'unknown_chunk',
  'too_many_spans',
]

describe('refusalCopy', () => {
  it('has real copy for every refusal reason the backend defines', () => {
    for (const reason of ALL_REASONS) {
      const copy = refusalCopy(reason)
      expect(copy.title.length, reason).toBeGreaterThan(3)
      expect(copy.body.length, reason).toBeGreaterThan(10)
    }
  })

  it('gives each reason a distinct explanation', () => {
    // If two reasons render identically, the user cannot tell "we have no
    // documents" from "the model invented a number" — which are entirely
    // different problems with entirely different next steps.
    const bodies = ALL_REASONS.map((reason) => refusalCopy(reason).body)
    expect(new Set(bodies).size).toBe(ALL_REASONS.length)
  })

  it('treats a refusal as correct behavior (amber), not as an error', () => {
    const refusals: RefusalReason[] = [
      'no_documents',
      'low_relevance',
      'insufficient_data',
      'grounding_failed',
      'numeric_grounding_failed',
    ]
    for (const reason of refusals) {
      expect(refusalCopy(reason).tone, reason).toBe('refusal')
    }
  })

  it('reserves the error tone for something that is actually broken', () => {
    expect(refusalCopy('provider_error').tone).toBe('error')
  })

  it('still refuses honestly for an unknown reason', () => {
    // A backend that grows a seventh reason must not render an empty card.
    const copy = refusalCopy('nagot_helt_nytt' as RefusalReason)
    expect(copy.tone).toBe('refusal')
    expect(copy.body.length).toBeGreaterThan(10)
  })

  it('handles a null reason', () => {
    expect(refusalCopy(null).title.length).toBeGreaterThan(3)
  })

  it('states the promise the product is actually making', () => {
    expect(GROUNDING_PROMISE).toBe('Inget svar visas utan belägg.')
  })
})

describe('rejectCopy', () => {
  it('explains every rejection reason in plain Swedish', () => {
    for (const reason of ALL_REJECTS) {
      expect(rejectCopy(reason), reason).not.toMatch(/_/)
      expect(rejectCopy(reason).length, reason).toBeGreaterThan(10)
    }
  })

  it('never leaks a raw enum value to the user', () => {
    expect(rejectCopy('helt_okant' as RejectReason)).not.toContain('helt_okant')
  })
})
