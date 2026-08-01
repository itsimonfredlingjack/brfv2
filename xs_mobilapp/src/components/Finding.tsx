import { useState } from 'react'

import type { Citation, ReviewFinding, VerifiedFact } from '../api/types'
import { formatDate } from '../lib/format'
import {
  anchorIsWeak,
  anchorLabel,
  decisionSentence,
  statusLabel,
  verdictLabel,
  verdictTone,
} from '../lib/findings'
import { CitationChip } from './CitationChip'
import { AlertIcon, CheckIcon, UnknownIcon } from './icons'

/**
 * One review finding, read-only.
 *
 * The visual hierarchy carries the epistemic one, exactly as the desktop
 * does: verified facts read as data, the engine's suggestion reads as prose
 * and is named as a suggestion, and the uncertainty sits in its own warmer
 * block that cannot be skimmed past. They are three separate blocks because
 * they are three separate kinds of claim — a card that merges them teaches
 * its reader that a proposal is a fact.
 *
 * Every citation opens the source at its page with the passage highlighted,
 * through the same Källa machinery an answer's citation uses. A finding whose
 * evidence cannot be opened is an assertion, not a finding.
 */
export function Finding({
  finding,
  onOpenCitation,
}: {
  finding: ReviewFinding
  onOpenCitation: (citation: Citation) => void
}) {
  // Held here rather than in the screen: the card stays mounted while the
  // sheet is open, so "sources I already looked at" survives closing it.
  const [visited, setVisited] = useState<ReadonlySet<number>>(() => new Set())

  const tone = verdictTone(finding.verdict)
  const invoiceFacts = finding.verified_facts.filter((fact) => fact.source === 'invoice')
  const documentFacts = finding.verified_facts.filter((fact) => fact.source === 'document')
  const decision = decisionSentence(finding)
  const weakAnchor = anchorIsWeak(finding.anchor_strength)

  const open = (citation: Citation, index: number) => {
    setVisited((current) => new Set(current).add(index))
    onOpenCitation(citation)
  }

  return (
    <article className={`finding finding--${tone}`} data-testid="finding" data-verdict={finding.verdict}>
      <div className="finding__head">
        <h2 className="finding__verdict">
          <span className="finding__mark" data-testid="verdict-mark" data-mark={tone}>
            <VerdictMark tone={tone} />
          </span>
          {verdictLabel(finding)}
        </h2>
        <span className={`chip finding__status finding__status--${finding.status}`}>
          {statusLabel(finding.status)}
        </span>
      </div>

      <p className="finding__when">Fynd från {formatDate(finding.created_at)}</p>

      <div className="finding__facts" data-testid="finding-facts">
        <FactList
          title="Verifierat ur fakturan"
          facts={invoiceFacts}
          empty="Inget fält lästes ur fakturan."
        />
        <FactList
          title="Verifierat ur dokumenten"
          facts={documentFacts}
          empty="Ingenting kunde verifieras ordagrant i föreningens dokument."
        />
      </div>

      {finding.citations.length > 0 && (
        <div className="finding__citations" data-testid="finding-citations">
          <div className="label">{finding.citations.length === 1 ? 'Källa' : 'Källor'}</div>
          {finding.citations.map((citation, index) => (
            <CitationChip
              key={`${citation.chunk_id}-${index}`}
              citation={citation}
              visited={visited.has(index)}
              onOpen={() => open(citation, index)}
            />
          ))}
        </div>
      )}

      <div className="finding__suggestion" data-testid="finding-suggestion">
        <div className="label">Förslag från {finding.suggested_by}</div>
        <p className="finding__prose">{finding.suggestion}</p>
      </div>

      {finding.uncertainty && (
        <div className="finding__uncertainty" data-testid="finding-uncertainty">
          <div className="finding__warm-head">
            <AlertIcon />
            Osäkerhet
          </div>
          <p className="finding__prose">{finding.uncertainty}</p>
        </div>
      )}

      {finding.anchor_note &&
        (weakAnchor ? (
          /* A weak anchor is not a footnote. The two papers are probably —
           * not certainly — about the same company, and a reader weighing a
           * "möjlig avvikelse" has to see that before the number. */
          <div className="finding__anchor finding__anchor--weak" data-testid="finding-anchor">
            <div className="finding__warm-head">
              <AlertIcon />
              {anchorLabel(finding.anchor_strength)}
            </div>
            <p className="finding__prose">{finding.anchor_note}</p>
          </div>
        ) : (
          <p className="finding__anchor" data-testid="finding-anchor">
            <span className="finding__anchor-label">{anchorLabel(finding.anchor_strength)}.</span>{' '}
            {finding.anchor_note}
          </p>
        ))}

      {finding.alias_proposal && (
        <div className="finding__alias" data-testid="finding-alias">
          <div className="label">Väntar på bekräftelse</div>
          <p className="finding__prose">
            Fyndet vilar på att ”{finding.alias_proposal.invoice_name}” och ”
            {finding.alias_proposal.document_name}” är samma leverantör.{' '}
            {finding.alias_proposal.basis} Att bekräfta det är ett ställningstagande med en person
            bakom sig och görs i webbappen.
          </p>
        </div>
      )}

      <div className="finding__decision" data-testid="finding-decision">
        {decision ? (
          <>
            <span className="finding__decision-who">{decision}</span>
            {finding.decision_note && (
              <span className="finding__decision-note">Anteckning: {finding.decision_note}</span>
            )}
          </>
        ) : (
          <span>Inget ställningstagande gjort ännu.</span>
        )}
      </div>
    </article>
  )
}

/** The check is reserved for a verbatim match; the other two verdicts get
 * marks that do not claim one. Never colour alone — the word is right beside
 * it either way. */
function VerdictMark({ tone }: { tone: ReturnType<typeof verdictTone> }) {
  if (tone === 'grounded') return <CheckIcon />
  if (tone === 'deviation') return <AlertIcon size={16} />
  return <UnknownIcon />
}

function FactList({ title, facts, empty }: { title: string; facts: VerifiedFact[]; empty: string }) {
  return (
    <div className="facts">
      <div className="label">{title}</div>
      {facts.length > 0 ? (
        <dl className="facts__list">
          {facts.map((fact, index) => (
            <div className="facts__row" key={`${fact.label}-${index}`}>
              <dt className="facts__term">{fact.label}</dt>
              <dd className="facts__value">{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="facts__empty">{empty}</p>
      )}
    </div>
  )
}
