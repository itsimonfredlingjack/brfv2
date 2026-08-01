import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, Extraction, ReviewFinding } from '../api/types'
import { Granskning } from './Granskning'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: { ...actual.api, listFindings: vi.fn(), getExtraction: vi.fn() },
  }
})

const listFindings = vi.mocked(api.listFindings)
const getExtraction = vi.mocked(api.getExtraction)

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    document_id: 'doc-1',
    document_name: 'Snöröjningsavtal 2026',
    page: 4,
    quote: 'Ersättning utgår med 1 250 kronor per timme.',
    quotes: ['Ersättning utgår med 1 250 kronor per timme.'],
    chunk_id: 'c-1',
    rects: [[72, 320, 380, 334]],
    score: 0.82,
    approximate: false,
    corpus_origin: 'synthetic',
    ...overrides,
  }
}

function finding(overrides: Partial<ReviewFinding> = {}): ReviewFinding {
  return {
    id: 'f-1',
    tenant_id: 'gjutformen-12',
    finding_type: 'invoice_contract_amount',
    created_at: '2026-05-12T09:15:00+00:00',
    invoice_id: 'inv-1',
    source_event_id: null,
    verdict: 'possible_deviation',
    verdict_label: 'möjlig avvikelse',
    verified_facts: [
      { label: 'Fakturabelopp', value: '6 250,00 SEK', source: 'invoice', citation_index: null },
    ],
    suggestion: 'Stäm av fakturans belopp mot avtalets timtaxa innan den attesteras.',
    suggested_by: 'regelmotor',
    uncertainty: 'Avtalet anger ingen mängd.',
    citations: [citation()],
    anchor_strength: 'exact',
    anchor_note: 'Snöröjningsavtal 2026 namnger Snösvängen AB ordagrant.',
    alias_proposal: null,
    status: 'open',
    decided_by: null,
    decided_at: null,
    decision_note: null,
    ...overrides,
  }
}

function extraction(): Extraction {
  return {
    document: {
      id: 'doc-1',
      name: 'Snöröjningsavtal 2026',
      pages: 12,
      words: 4200,
      chunks: 18,
      uploaded_at: '2026-01-04T08:00:00+00:00',
      source: 'digital',
      corpus_origin: 'synthetic',
    },
    pages: Array.from({ length: 12 }, (_, index) => ({
      number: index + 1,
      width: 595,
      height: 842,
      words: 350,
    })),
    chunks: [],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom has neither, and the Källa sheet legitimately uses both. Nothing
  // here is about rasterization, so the page image is allowed to fail: the
  // sheet still has to open on the cited page.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ingen sidbild i testet')))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Granskning', () => {
  it('listar nyaste fyndet först', async () => {
    listFindings.mockResolvedValue([
      finding({
        id: 'gammalt',
        created_at: '2026-05-01T09:00:00+00:00',
        verdict: 'matches',
        verdict_label: 'överensstämmer',
      }),
      finding({ id: 'nytt', created_at: '2026-05-20T09:00:00+00:00' }),
    ])

    render(<Granskning brfId="gjutformen-12" />)

    const cards = await screen.findAllByTestId('finding')
    expect(cards.map((card) => card.dataset.verdict)).toEqual(['possible_deviation', 'matches'])
  })

  it('säger rakt ut att ställningstaganden görs i webbappen', async () => {
    listFindings.mockResolvedValue([finding()])

    render(<Granskning brfId="gjutformen-12" />)
    await screen.findByTestId('finding')

    expect(screen.getByTestId('readonly-note')).toHaveTextContent(
      'Läsvy. Att godkänna, avfärda eller korrigera ett fynd görs i webbappen.',
    )
    // Every control on the screen is a source. There is nothing else to press.
    expect(screen.getAllByRole('button')).toHaveLength(screen.getAllByTestId('citation-chip').length)
  })

  it('öppnar källan på den citerade sidan med passagen markerad', async () => {
    listFindings.mockResolvedValue([finding()])
    getExtraction.mockResolvedValue(extraction())

    render(<Granskning brfId="gjutformen-12" />)
    fireEvent.click(await screen.findByTestId('citation-chip'))

    const sheet = await screen.findByRole('dialog', { name: /Källa: Snöröjningsavtal 2026/ })
    expect(await within(sheet).findByText(/Sida 4 av 12/)).toBeInTheDocument()
    expect(within(sheet).getByText(/Verifierat ordagrant i dokumentet/)).toBeInTheDocument()
    expect(within(sheet).getByText(/1 250 kronor per timme/)).toBeInTheDocument()
    // The passage is placed on the page, not merely named above it.
    expect(within(sheet).getAllByTestId('citation-highlight').length).toBeGreaterThan(0)
  })

  it('har ett eget tomtillstånd, inte en spinnare som aldrig tar slut', async () => {
    listFindings.mockResolvedValue([])

    render(<Granskning brfId="gjutformen-12" />)

    expect(await screen.findByText('Inga fynd ännu')).toBeInTheDocument()
    expect(screen.getByText(/granskas i webbappen/)).toBeInTheDocument()
    expect(screen.queryByTestId('finding')).toBeNull()
  })

  it('säger till när fynden inte gick att hämta', async () => {
    listFindings.mockRejectedValue(new ApiError('boom', 500))

    render(<Granskning brfId="gjutformen-12" />)

    expect(await screen.findByText('Fynden kunde inte hämtas')).toBeInTheDocument()
    // Not the empty state: "nothing came back" and "there is nothing" are
    // different things to tell someone.
    expect(screen.queryByText('Inga fynd ännu')).toBeNull()
  })

  it('säger att fynden inte ligger på telefonen när man är offline', async () => {
    listFindings.mockRejectedValue(new OfflineError())

    render(<Granskning brfId="gjutformen-12" />)

    expect(await screen.findByText('Du är offline')).toBeInTheDocument()
    expect(screen.getByText(/hämtas när du är uppkopplad igen/)).toBeInTheDocument()
  })

  it('hämtar fynden för den aktiva föreningen, aldrig för ett id den hittat på', async () => {
    listFindings.mockResolvedValue([])

    render(<Granskning brfId="gjutformen-12" />)
    await screen.findByText('Inga fynd ännu')

    expect(listFindings).toHaveBeenCalledWith('gjutformen-12')
  })
})
