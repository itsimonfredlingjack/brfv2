import { useEffect, useState } from 'react'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, ReviewFinding } from '../api/types'
import { Finding } from '../components/Finding'
import { KallaSheet } from '../components/KallaSheet'
import type { KallaTarget } from '../components/KallaSheet'
import { Notice } from '../components/Notice'

interface LoadProblem {
  tone: 'refusal' | 'error'
  title: string
  body: string
}

/* Newest first. The backend appends in review order, so it arrives oldest
 * first; in a meeting the thing that just came in is the thing being talked
 * about. An unparseable timestamp sorts last rather than poisoning the
 * comparator. */
const at = (iso: string): number => {
  const parsed = Date.parse(iso)
  return Number.isNaN(parsed) ? 0 : parsed
}

function problemFor(err: unknown): LoadProblem {
  if (err instanceof OfflineError) {
    return {
      tone: 'error',
      title: 'Du är offline',
      body: 'Fynden ligger inte på telefonen. De hämtas när du är uppkopplad igen.',
    }
  }
  if (err instanceof ApiError && err.status === 404) {
    return {
      tone: 'refusal',
      title: 'Granskning finns inte här',
      body: 'Den här installationen tar inte emot fakturor för granskning.',
    }
  }
  return {
    tone: 'error',
    title: 'Fynden kunde inte hämtas',
    body: 'Granskningens fynd gick inte att läsa just nu.',
  }
}

/**
 * The association's review findings, read-only.
 *
 * The desktop is where a board *works* on incoming material; this is where
 * someone reads it, in a meeting, with the source one tap away. Nothing here
 * approves, dismisses or corrects anything, and the screen says so in one
 * line rather than leaving a reader hunting for a button that is not there.
 *
 * Deliberately not cached on the device. What a phone holds is documented as
 * exactly two derived things (README) that logout and förening switch erase;
 * a third store of supplier invoices and board decisions would be a new
 * promise, made quietly. A finding is read where there is a connection.
 */
export function Granskning({ brfId }: { brfId: string }) {
  const [findings, setFindings] = useState<ReviewFinding[] | null>(null)
  const [problem, setProblem] = useState<LoadProblem | null>(null)
  const [target, setTarget] = useState<KallaTarget | null>(null)

  useEffect(() => {
    let cancelled = false

    api
      .listFindings(brfId)
      .then((list) => {
        if (cancelled) return
        setFindings([...list].sort((a, b) => at(b.created_at) - at(a.created_at)))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setProblem(problemFor(err))
      })

    return () => {
      cancelled = true
    }
  }, [brfId])

  const openCitation = (citation: Citation) => {
    setTarget({
      documentId: citation.document_id,
      documentName: citation.document_name,
      page: citation.page,
      citation,
    })
  }

  return (
    <>
      <div className="screen">
        <h1 className="screen__title">Granskning</h1>
        <p className="screen__lede">
          Fynd ur granskningen av inkommande fakturor mot föreningens egna dokument, nyast först.
        </p>
        <p className="readonly-note" data-testid="readonly-note">
          Läsvy. Att godkänna, avfärda eller korrigera ett fynd görs i webbappen.
        </p>

        {problem && (
          <div style={{ marginTop: 'var(--s5)' }}>
            <Notice tone={problem.tone} title={problem.title}>
              {problem.body}
            </Notice>
          </div>
        )}

        {findings === null && !problem && (
          <div className="list">
            {[0, 1].map((index) => (
              <div key={index} className="skeleton" style={{ height: 168 }} />
            ))}
          </div>
        )}

        {findings !== null && findings.length === 0 && (
          <div className="empty">
            <div className="empty__title">Inga fynd ännu</div>
            <p className="empty__body">
              Granskningen har inte lagt fram något fynd för föreningen. Fakturor läses in och
              granskas i webbappen.
            </p>
          </div>
        )}

        {findings !== null && findings.length > 0 && (
          <div className="list">
            {findings.map((finding) => (
              <Finding key={finding.id} finding={finding} onOpenCitation={openCitation} />
            ))}
          </div>
        )}
      </div>

      {target && <KallaSheet brfId={brfId} target={target} onClose={() => setTarget(null)} />}
    </>
  )
}
