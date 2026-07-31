import type { Citation } from '../api/types'
import { CheckIcon } from './icons'

/**
 * One verified source. Never signalled by colour alone: a check glyph for a
 * verified citation, a dashed edge plus an explicit label when the highlight
 * is approximate (OCR word boxes on a scanned page).
 */
export function CitationChip({
  citation,
  visited,
  onOpen,
}: {
  citation: Citation
  visited: boolean
  onOpen: () => void
}) {
  const className = [
    'cite',
    citation.approximate ? 'cite--approximate' : '',
    visited ? 'cite--visited' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      className={className}
      onClick={onOpen}
      data-testid="citation-chip"
      aria-label={`Källa: ${citation.document_name}, sida ${citation.page}. Öppna sidan med markerad passage.`}
    >
      <span className="cite__head">
        <CheckIcon />
        <span className="cite__doc">{citation.document_name}</span>
        <span aria-hidden="true">·</span>
        <span>sida {citation.page}</span>
        {citation.approximate && <span className="chip chip--scanned">ungefärlig markering</span>}
      </span>
      <span className="cite__quote">”{citation.quote}”</span>
    </button>
  )
}
