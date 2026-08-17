import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Citation } from '../api/types'
import { CitationChip } from './CitationChip'
import { RefusalCard } from './Notice'

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    document_id: 'doc-1',
    document_name: 'Stadgar',
    page: 4,
    quote: 'Andrahandsuthyrning kräver styrelsens skriftliga samtycke.',
    quotes: ['Andrahandsuthyrning kräver styrelsens skriftliga samtycke.'],
    chunk_id: 'c-1',
    rects: [[72, 100, 300, 114]],
    score: 0.8,
    approximate: false,
    corpus_origin: 'synthetic',
    ...overrides,
  }
}

describe('RefusalCard', () => {
  it('explains the reason and repeats the promise', () => {
    render(<RefusalCard reason="insufficient_data" rejected={[]} />)
    expect(screen.getByText(/Dokumenten innehåller inte svaret/)).toBeInTheDocument()
    expect(screen.getByText('Inget svar visas utan belägg.')).toBeInTheDocument()
  })

  it('shows backend refusal prose when the refusal is the answer', () => {
    render(
      <RefusalCard
        reason="insufficient_data"
        rejected={[]}
        answer="Jag läste Teknisk förvaltning.pdf. Svaret står inte i dem."
      />,
    )
    expect(screen.getByText(/Jag läste Teknisk förvaltning.pdf/)).toBeInTheDocument()
    expect(screen.queryByText(/Dokumenten innehåller inte svaret/)).not.toBeInTheDocument()
  })

  it('announces a refusal as status, not as an error', () => {
    render(<RefusalCard reason="low_relevance" rejected={[]} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('announces a provider failure as an actual error', () => {
    render(<RefusalCard reason="provider_error" rejected={[]} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('keeps rejected citations folded away as diagnostics', () => {
    render(
      <RefusalCard
        reason="grounding_failed"
        rejected={[{ chunk_id: 'c-9', quote: 'ett påhittat citat', reason: 'quote_not_found' }]}
      />,
    )
    // Present for the curious, not in the reading path — and never showing
    // the raw enum.
    expect(screen.getByText('Varför visas inget svar?')).toBeInTheDocument()
    expect(screen.getByText(/gick inte att hitta ordagrant/)).toBeInTheDocument()
    expect(screen.queryByText(/quote_not_found/)).not.toBeInTheDocument()
  })
})

describe('CitationChip', () => {
  it('names the document and page in its accessible name', () => {
    render(<CitationChip citation={citation()} visited={false} onOpen={vi.fn()} />)
    expect(
      screen.getByRole('button', { name: /Källa: Stadgar, sida 4/ }),
    ).toBeInTheDocument()
  })

  it('shows the verified quote', () => {
    render(<CitationChip citation={citation()} visited={false} onOpen={vi.fn()} />)
    expect(screen.getByText(/Andrahandsuthyrning kräver styrelsens skriftliga samtycke/)).toBeInTheDocument()
  })

  it('labels an approximate highlight in text, not by colour alone', () => {
    render(<CitationChip citation={citation({ approximate: true })} visited={false} onOpen={vi.fn()} />)
    expect(screen.getByText('ungefärlig markering')).toBeInTheDocument()
  })

  it('does not label an exact highlight as approximate', () => {
    render(<CitationChip citation={citation()} visited={false} onOpen={vi.fn()} />)
    expect(screen.queryByText('ungefärlig markering')).not.toBeInTheDocument()
  })
})
