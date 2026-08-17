import type { ReactNode } from 'react'

import type { RefusalReason, RejectedCitation } from '../api/types'
import { GROUNDING_PROMISE, refusalCopy, rejectCopy } from '../lib/refusals'
import { AlertIcon } from './icons'
import { TraffMark } from './TraffMark'

export function Notice({
  tone,
  title,
  children,
  footer,
}: {
  tone: 'refusal' | 'error'
  title: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div className="notice__head">
        {/* §01: the status mark is the app's primary visual state indicator. A
            refusal is a state of the evidence — the ring with nothing in it —
            not a warning triangle. An actual failure is machinery, and keeps
            the triangle. */}
        {tone === 'refusal'
          ? <TraffMark size={17} variant="status" state="ejbelagt" decorative />
          : <AlertIcon />}
        {title}
      </div>
      <div className="notice__body">{children}</div>
      {footer}
    </div>
  )
}

/**
 * A refusal. Amber, explained, with something to do next — and the standing
 * promise underneath. Rejected citations are diagnostics and stay folded
 * away; they are the machinery talking, not the product.
 */
export function RefusalCard({
  reason,
  rejected,
  answer,
}: {
  reason: RefusalReason | null
  rejected: RejectedCitation[]
  /** Backend prose when the refusal itself is the answer. */
  answer?: string
}) {
  const copy = refusalCopy(reason)
  const body = answer?.trim() || copy.body

  return (
    <Notice
      tone={copy.tone}
      title={copy.title}
      footer={<div className="notice__promise">{GROUNDING_PROMISE}</div>}
    >
      <p>{body}</p>
      {copy.next && <p style={{ marginTop: 'var(--s2)', color: 'var(--ink-2)' }}>{copy.next}</p>}

      {rejected.length > 0 && (
        <details className="disclosure">
          <summary className="disclosure__summary">Varför visas inget svar?</summary>
          <div className="disclosure__body">
            <p style={{ padding: 'var(--s2) 0' }}>
              {rejected.length === 1
                ? 'Ett citat avvisades vid verifieringen:'
                : `${rejected.length} citat avvisades vid verifieringen:`}
            </p>
            {rejected.map((item, index) => (
              <div className="disclosure__item" key={`${item.chunk_id}-${index}`}>
                <div>{rejectCopy(item.reason)}</div>
                {item.quote && (
                  <div style={{ marginTop: 4, fontStyle: 'italic', color: 'var(--ink-3)' }}>
                    ”{item.quote.slice(0, 180)}
                    {item.quote.length > 180 ? '…' : ''}”
                  </div>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </Notice>
  )
}
