import { useEffect, useState } from 'react'

import { back } from '../app/router'
import { CitationChip } from '../components/CitationChip'
import { KallaSheet } from '../components/KallaSheet'
import type { KallaTarget } from '../components/KallaSheet'
import { Notice, RefusalCard } from '../components/Notice'
import { ChevronLeft } from '../components/icons'
import { formatMoment, formatProvenance } from '../lib/format'
import { getEntry } from '../state/localStore'
import type { JournalEntry } from '../state/localStore'

export function Svar({ brfId, entryId }: { brfId: string; entryId: string }) {
  const [entry, setEntry] = useState<JournalEntry | null | undefined>(undefined)
  const [target, setTarget] = useState<KallaTarget | null>(null)
  const [visited, setVisited] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    getEntry(brfId, entryId)
      .then((found) => !cancelled && setEntry(found ?? null))
      .catch(() => !cancelled && setEntry(null))
    return () => {
      cancelled = true
    }
  }, [brfId, entryId])

  if (entry === undefined) {
    return (
      <div className="screen">
        <div className="skeleton" style={{ height: 20, width: '60%' }} />
        <div className="skeleton" style={{ height: 120, marginTop: 'var(--s4)' }} />
      </div>
    )
  }

  if (entry === null) {
    return (
      <div className="screen">
        <button type="button" className="backlink" onClick={back}>
          <ChevronLeft size={16} />
          Tillbaka
        </button>
        <div style={{ marginTop: 'var(--s5)' }}>
          <Notice tone="refusal" title="Svaret finns inte kvar">
            Svaret har tagits bort — antingen av retentionsgränsen på 30 dagar eller när
            svarshistoriken rensades.
          </Notice>
        </div>
      </div>
    )
  }

  const openCitationIndex = (index: number) => {
    const citation = entry.citations[index]
    if (!citation) return
    setVisited((prev) => new Set(prev).add(`${citation.document_id}:${citation.page}:${index}`))
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
        <button
          type="button"
          className="backlink"
          onClick={back}
        >
          <ChevronLeft size={16} />
          Tillbaka
        </button>

        <div style={{ marginTop: 'var(--s4)' }}>
          <p className="answer__question">{entry.question}</p>

          {entry.refusal ? (
            <div style={{ marginTop: 'var(--s4)' }}>
              <RefusalCard reason={entry.refusalReason} rejected={entry.rejected} />
            </div>
          ) : (
            <>
              <p className="answer__text" data-testid="answer-text">
                {entry.answer}
              </p>

              {entry.warning && (
                <div style={{ marginTop: 'var(--s4)' }}>
                  <Notice tone="refusal" title="Osäkert underlag">
                    {entry.warning}
                  </Notice>
                </div>
              )}

              {entry.citations.length > 0 && (
                <>
                  <div className="answer__rule" />
                  <div className="label" style={{ marginBottom: 'var(--s3)' }}>
                    {entry.citations.length === 1 ? 'Källa' : 'Källor'}
                  </div>
                  {entry.citations.map((citation, index) => (
                    <CitationChip
                      key={`${citation.chunk_id}-${index}`}
                      citation={citation}
                      visited={visited.has(`${citation.document_id}:${citation.page}:${index}`)}
                      onOpen={() => openCitationIndex(index)}
                    />
                  ))}
                </>
              )}
            </>
          )}

          <p className="answer__meta">
            {[formatProvenance(entry.provider, entry.model), formatMoment(entry.createdAt)]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
      </div>

      {target && <KallaSheet brfId={brfId} target={target} onClose={() => setTarget(null)} />}
    </>
  )
}
