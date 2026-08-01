import type { RefusalReason, RejectReason } from '../api/types'
import { GROUNDING_PROMISE, refusalCopy, rejectCopy } from './refusals'

const ALL_REASONS: RefusalReason[] = [
  'no_documents',
  'low_relevance',
  'insufficient_data',
  'grounding_failed',
  'provider_error',
  'numeric_grounding_failed',
]

const ALL_REJECT_REASONS: RejectReason[] = [
  'quote_not_found',
  'provenance_mismatch',
  'bbox_out_of_bounds',
  'unknown_chunk',
  'too_many_spans',
]

describe('refusalCopy', () => {
  it('has copy for every known refusal reason', () => {
    for (const reason of ALL_REASONS) {
      const copy = refusalCopy(reason)
      expect(copy.title.length).toBeGreaterThan(0)
      expect(copy.body.length).toBeGreaterThan(0)
    }
  })

  it('is amber (refusal), never red (error), except for provider_error', () => {
    for (const reason of ALL_REASONS) {
      const copy = refusalCopy(reason)
      expect(copy.tone).toBe(reason === 'provider_error' ? 'error' : 'refusal')
    }
  })

  it('still refuses honestly for an unknown reason instead of an empty card', () => {
    const copy = refusalCopy('some_future_reason' as RefusalReason)
    expect(copy.tone).toBe('refusal')
    expect(copy.title.length).toBeGreaterThan(0)
    expect(copy.body.length).toBeGreaterThan(0)
  })

  it('handles a null reason the same way as unknown', () => {
    expect(refusalCopy(null).tone).toBe('refusal')
  })
})

describe('rejectCopy', () => {
  it('has copy for every reject reason', () => {
    for (const reason of ALL_REJECT_REASONS) {
      expect(rejectCopy(reason).length).toBeGreaterThan(0)
    }
  })
})

describe('GROUNDING_PROMISE', () => {
  it('is the exact proven copy', () => {
    expect(GROUNDING_PROMISE).toBe('Inget svar visas utan belägg.')
  })
})
