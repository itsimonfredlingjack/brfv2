import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Citation, ReviewFinding } from '../api/types'
import { Finding } from './Finding'

/* A finding says three different kinds of thing at once: what is established,
 * what a rule engine proposes, and what nobody could establish. The card is
 * only correct if a reader can tell which is which without being told — so
 * that is what these assert, alongside the one thing the phone must never
 * grow: a way to decide. */

const SUGGESTION = 'Stäm av fakturans belopp mot avtalets timtaxa innan den attesteras.'
const UNCERTAINTY =
  'Avtalet anger ingen mängd, så det går inte att avgöra om 5 timmar är rimligt för perioden.'

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
      {
        label: 'Leverantör enligt fakturan',
        value: 'Snösvängen AB',
        source: 'invoice',
        citation_index: null,
      },
      { label: 'Fakturabelopp', value: '6 250,00 SEK', source: 'invoice', citation_index: null },
      {
        label: 'À-pris enligt fakturan — Snöröjning enligt avtal',
        value: '1 250,00 SEK',
        source: 'invoice',
        citation_index: null,
      },
      {
        label: 'Belopp i citerat villkor',
        value: '1 250,00 SEK',
        source: 'document',
        citation_index: 0,
      },
    ],
    suggestion: SUGGESTION,
    suggested_by: 'regelmotor',
    uncertainty: UNCERTAINTY,
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

describe('Finding — domarna', () => {
  const cases = [
    { verdict: 'matches', label: 'överensstämmer', tone: 'grounded' },
    { verdict: 'possible_deviation', label: 'möjlig avvikelse', tone: 'deviation' },
    { verdict: 'cannot_be_verified', label: 'kan inte verifieras', tone: 'unknown' },
  ] as const

  for (const { verdict, label, tone } of cases) {
    it(`säger "${label}" och ger domen sin egen behandling`, () => {
      render(
        <Finding
          finding={finding({ verdict, verdict_label: label })}
          onOpenCitation={vi.fn()}
        />,
      )

      expect(screen.getByRole('heading', { name: label })).toBeInTheDocument()
      expect(screen.getByTestId('finding')).toHaveClass(`finding--${tone}`)
      // The mark is part of the treatment, and only a verbatim match gets the
      // one that means "verified".
      expect(screen.getByTestId('verdict-mark')).toHaveAttribute('data-mark', tone)
    })
  }

  it('faller tillbaka på svensk etikett om backenden skickar en tom', () => {
    render(<Finding finding={finding({ verdict_label: '' })} onOpenCitation={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'möjlig avvikelse' })).toBeInTheDocument()
  })
})

describe('Finding — vad som är fastställt, föreslaget respektive osäkert', () => {
  it('håller isär de tre i DOM:en, inte bara i texten', () => {
    render(<Finding finding={finding()} onOpenCitation={vi.fn()} />)

    const facts = screen.getByTestId('finding-facts')
    const suggestion = screen.getByTestId('finding-suggestion')
    const uncertainty = screen.getByTestId('finding-uncertainty')

    expect(within(facts).getByText('Fakturabelopp')).toBeInTheDocument()
    expect(within(facts).getByText('6 250,00 SEK')).toBeInTheDocument()
    expect(within(facts).getByText('Belopp i citerat villkor')).toBeInTheDocument()
    expect(within(suggestion).getByText(SUGGESTION)).toBeInTheDocument()
    expect(within(uncertainty).getByText(UNCERTAINTY)).toBeInTheDocument()

    // Three blocks, none inside another: the suggestion must not be readable
    // as part of what was verified, and the uncertainty must not be readable
    // as part of the suggestion.
    expect(facts.contains(suggestion)).toBe(false)
    expect(suggestion.contains(uncertainty)).toBe(false)
    expect(within(suggestion).queryByText(UNCERTAINTY)).toBeNull()
    expect(within(facts).queryByText(SUGGESTION)).toBeNull()
  })

  it('skiljer på vad som är läst ur fakturan och vad som är belagt i dokumenten', () => {
    render(<Finding finding={finding()} onOpenCitation={vi.fn()} />)
    expect(screen.getByText('Verifierat ur fakturan')).toBeInTheDocument()
    expect(screen.getByText('Verifierat ur dokumenten')).toBeInTheDocument()
  })

  it('säger vem som skrivit förslaget', () => {
    render(<Finding finding={finding()} onOpenCitation={vi.fn()} />)
    expect(screen.getByText('Förslag från regelmotor')).toBeInTheDocument()
  })

  it('säger att ingenting kunde beläggas när dokumenten inte bär något', () => {
    render(
      <Finding
        finding={finding({
          verdict: 'cannot_be_verified',
          verdict_label: 'kan inte verifieras',
          verified_facts: [
            { label: 'Fakturabelopp', value: '6 250,00 SEK', source: 'invoice', citation_index: null },
          ],
          citations: [],
        })}
        onOpenCitation={vi.fn()}
      />,
    )
    expect(
      screen.getByText('Ingenting kunde verifieras ordagrant i föreningens dokument.'),
    ).toBeInTheDocument()
  })

  it('visar inget osäkerhetsblock för en ren match utan osäkerhet', () => {
    render(
      <Finding
        finding={finding({ verdict: 'matches', verdict_label: 'överensstämmer', uncertainty: null })}
        onOpenCitation={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('finding-uncertainty')).toBeNull()
  })
})

describe('Finding — citaten', () => {
  it('öppnar källan på den citerade sidan', () => {
    const onOpenCitation = vi.fn()
    render(<Finding finding={finding()} onOpenCitation={onOpenCitation} />)

    fireEvent.click(screen.getByTestId('citation-chip'))

    expect(onOpenCitation).toHaveBeenCalledTimes(1)
    expect(onOpenCitation).toHaveBeenCalledWith(
      expect.objectContaining({ document_id: 'doc-1', page: 4 }),
    )
  })
})

describe('Finding — det mänskliga ställningstagandet', () => {
  const decided = finding({
    status: 'approved',
    decided_by: 'Bo Ek',
    decided_at: '2026-05-12T14:32:00+00:00',
    decision_note: 'Timtaxan är omförhandlad sedan avtalet skrevs.',
  })

  it('visar vem som avgjorde och när', () => {
    render(<Finding finding={decided} onOpenCitation={vi.fn()} />)

    const decision = screen.getByTestId('finding-decision')
    expect(within(decision).getByText(/Godkänt av Bo Ek/)).toBeInTheDocument()
    expect(within(decision).getByText(/2026/)).toBeInTheDocument()
    expect(
      within(decision).getByText('Anteckning: Timtaxan är omförhandlad sedan avtalet skrevs.'),
    ).toBeInTheDocument()
  })

  it('erbjuder ingen väg att ändra det', () => {
    render(<Finding finding={decided} onOpenCitation={vi.fn()} />)

    expect(
      screen.queryByRole('button', { name: /Godkänn|Avfärda|Korrigera|Öppna igen/ }),
    ).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    // The only control on a finding is its evidence.
    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(screen.getByTestId('citation-chip')).toBeInTheDocument()
  })

  it('säger att inget ställningstagande gjorts när fyndet är öppet', () => {
    render(<Finding finding={finding()} onOpenCitation={vi.fn()} />)
    expect(screen.getByText('Inget ställningstagande gjort ännu.')).toBeInTheDocument()
  })
})

describe('Finding — ankaret', () => {
  const weak = finding({
    anchor_strength: 'partial',
    anchor_note:
      'Snöröjningsavtal 2026 skriver "Snösvängen Entreprenad AB", fakturan säger "Snösvängen AB". Namnen är inte identiska.',
  })

  it('låter en partiell koppling läsas som svag', () => {
    render(<Finding finding={weak} onOpenCitation={vi.fn()} />)

    const anchor = screen.getByTestId('finding-anchor')
    expect(anchor).toHaveClass('finding__anchor--weak')
    expect(within(anchor).getByText('Svag koppling till leverantören')).toBeInTheDocument()
    expect(within(anchor).getByText(/Namnen är inte identiska/)).toBeInTheDocument()
  })

  it('håller en stark koppling som en tyst rad', () => {
    render(<Finding finding={finding()} onOpenCitation={vi.fn()} />)

    const anchor = screen.getByTestId('finding-anchor')
    expect(anchor).not.toHaveClass('finding__anchor--weak')
    expect(within(anchor).getByText(/Kopplad på leverantörens namn/)).toBeInTheDocument()
  })

  it('visar att ett aliasförslag väntar på någon annanstans, utan att erbjuda det här', () => {
    render(
      <Finding
        finding={finding({
          anchor_strength: 'partial',
          anchor_note: 'Namnen är inte identiska.',
          alias_proposal: {
            invoice_name: 'Snösvängen AB',
            document_name: 'Snösvängen Entreprenad AB',
            document_id: 'doc-1',
            basis: 'Den särskiljande delen "Snösvängen" står ordagrant i Snöröjningsavtal 2026.',
          },
        })}
        onOpenCitation={vi.fn()}
      />,
    )

    const alias = screen.getByTestId('finding-alias')
    expect(within(alias).getByText(/Snösvängen Entreprenad AB/)).toBeInTheDocument()
    expect(within(alias).getByText(/görs i webbappen/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /bekräfta/i })).toBeNull()
  })
})
