import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, Extraction, UnresolvedObligation, Watch, WatchBoard } from '../api/types'
import { Bevakningar } from './Bevakningar'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: { ...actual.api, listWatches: vi.fn(), getExtraction: vi.fn() },
  }
})

const listWatches = vi.mocked(api.listWatches)
const getExtraction = vi.mocked(api.getExtraction)

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    document_id: 'doc-1',
    document_name: 'Städavtal 2024',
    page: 4,
    quote: 'Uppsägning ska ske skriftligen senast tre månader före avtalstidens utgång.',
    quotes: ['Uppsägning ska ske skriftligen senast tre månader före avtalstidens utgång.'],
    chunk_id: 'c-1',
    rects: [[72, 320, 380, 334]],
    score: 0.86,
    approximate: false,
    corpus_origin: 'synthetic',
    ...overrides,
  }
}

function watch(overrides: Partial<Watch> = {}): Watch {
  return {
    id: 'w-1',
    tenant_id: 'gjutformen-12',
    kind: 'notice_deadline',
    status: 'approved',
    title: 'Säg upp eller ompröva städavtalet senast 2026-09-30',
    due_date: '2026-09-30',
    derived_due_date: '2026-09-30',
    derivation: '2026-12-31 minus tre månaders uppsägningstid',
    recurrence: 'none',
    responsible: 'Anna Ek',
    remind_lead_days: 30,
    citations: [citation()],
    source_document_id: 'doc-1',
    source_document_name: 'Städavtal 2024',
    created_at: '2026-07-01T09:00:00+00:00',
    decided_by: 'bo@gjutformen12.se',
    decided_at: '2026-07-02T07:40:00+00:00',
    decision_note: null,
    succeeded_by: null,
    kind_label: 'Uppsägning',
    status_label: 'bevakas',
    remind_at: '2026-08-31',
    bucket: 'later',
    days_left: 60,
    next_due_after: null,
    ...overrides,
  }
}

function unresolved(overrides: Partial<UnresolvedObligation> = {}): UnresolvedObligation {
  return {
    id: 'u-1',
    tenant_id: 'gjutformen-12',
    what: 'Garantitiden är fem år från slutbesiktningen.',
    why: 'Slutbesiktningens datum står inte i handlingen, så garantins slut går inte att räkna fram.',
    citations: [citation({ document_name: 'Entreprenadkontrakt fasad', document_id: 'doc-2', page: 7 })],
    source_document_id: 'doc-2',
    source_document_name: 'Entreprenadkontrakt fasad',
    created_at: '2026-07-01T09:00:00+00:00',
    ...overrides,
  }
}

/** Empty by default: each test fills only what it is about. The labels are the
 * server's own (backend/app/watches/models.py) — the screen renders them and
 * never substitutes its own. */
function board(overrides: Partial<WatchBoard> = {}): WatchBoard {
  return {
    today: '2026-08-01',
    proposed: [],
    buckets: { overdue: [], soon: [], later: [], recurring: [] },
    bucketLabels: {
      overdue: 'Försenat',
      soon: 'Snart',
      later: 'Senare',
      recurring: 'Återkommande',
    },
    kindLabels: {
      notice_deadline: 'Uppsägning',
      expiry: 'Avtalet upphör',
      warranty: 'Garanti',
      inspection: 'Besiktning eller kontroll',
      recurring_obligation: 'Återkommande skyldighet',
    },
    statusLabels: {
      proposed: 'väntar på godkännande',
      approved: 'bevakas',
      dismissed: 'avfärdad',
      done: 'avklarad',
    },
    settled: [],
    unresolved: [],
    ...overrides,
  }
}

/** One approved watch in each of the four buckets. */
function fullBoard(): WatchBoard {
  return board({
    buckets: {
      overdue: [
        watch({
          id: 'w-overdue',
          title: 'Beställ OVK-besiktning, förfallen sedan 2026-07-20',
          kind: 'inspection',
          kind_label: 'Besiktning eller kontroll',
          due_date: '2026-07-20',
          derived_due_date: '2026-07-20',
          bucket: 'overdue',
          days_left: -12,
        }),
      ],
      soon: [watch({ id: 'w-soon', bucket: 'soon', due_date: '2026-08-20', days_left: 19 })],
      later: [watch({ id: 'w-later', bucket: 'later', days_left: 60 })],
      recurring: [
        watch({
          id: 'w-recurring',
          title: 'Lämna in brandskyddskontrollen senast 2026-11-01',
          kind: 'recurring_obligation',
          kind_label: 'Återkommande skyldighet',
          recurrence: 'yearly',
          due_date: '2026-11-01',
          derived_due_date: '2026-11-01',
          bucket: 'recurring',
          days_left: 92,
          next_due_after: '2027-11-01',
        }),
      ],
    },
  })
}

function extraction(): Extraction {
  return {
    document: {
      id: 'doc-1',
      name: 'Städavtal 2024',
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

const cardFor = (bucket: string): HTMLElement => {
  const card = screen.getAllByTestId('watch').find((element) => element.dataset.bucket === bucket)
  if (!card) throw new Error(`ingen bevakning i hinken ${bucket}`)
  return card
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

describe('Bevakningar', () => {
  it('visar de fyra hinkarna med serverns rubriker, i ordning', async () => {
    listWatches.mockResolvedValue(fullBoard())

    render(<Bevakningar brfId="gjutformen-12" />)
    await screen.findAllByTestId('watch')

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Försenat', 'Snart', 'Senare', 'Återkommande'])
  })

  it('renderar hinkarnas rubriker som de kommer från servern, inte ur en egen ordlista', async () => {
    listWatches.mockResolvedValue({
      ...fullBoard(),
      bucketLabels: { overdue: 'Passerat', soon: 'Nära', later: 'Längre fram', recurring: 'Cykliskt' },
    })

    render(<Bevakningar brfId="gjutformen-12" />)
    await screen.findAllByTestId('watch')

    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Passerat',
      'Nära',
      'Längre fram',
      'Cykliskt',
    ])
  })

  it('skiljer en försenad bevakning från en senare i text, inte bara i färg', async () => {
    listWatches.mockResolvedValue(fullBoard())

    render(<Bevakningar brfId="gjutformen-12" />)
    await screen.findAllByTestId('watch')

    const late = within(cardFor('overdue'))
    expect(late.getByText('Försenat')).toBeInTheDocument()
    expect(late.getByText(/12 dagar sedan/)).toBeInTheDocument()

    const later = within(cardFor('later'))
    expect(later.getByText(/om 60 dagar/)).toBeInTheDocument()
    expect(later.queryByText('Försenat')).toBeNull()
  })

  it('säger vilken dag räkningen utgår från', async () => {
    listWatches.mockResolvedValue(fullBoard())

    render(<Bevakningar brfId="gjutformen-12" />)

    expect(await screen.findByTestId('watch-asof')).toHaveTextContent('Räknat från 1 augusti 2026')
  })

  it('läser tom ansvarig som "ej utsedd", aldrig som blank', async () => {
    listWatches.mockResolvedValue(
      board({ buckets: { overdue: [], soon: [], later: [watch({ responsible: '' })], recurring: [] } }),
    )

    render(<Bevakningar brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('watch'))
    expect(card.getByTestId('watch-responsible')).toHaveTextContent('ej utsedd')
    expect(card.getByText('Ansvarig')).toBeInTheDocument()
  })

  it('visar sort, ansvarig och källdokument för varje bevakning', async () => {
    listWatches.mockResolvedValue(
      board({ buckets: { overdue: [], soon: [], later: [watch()], recurring: [] } }),
    )

    render(<Bevakningar brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('watch'))
    expect(card.getByText('Uppsägning')).toBeInTheDocument()
    expect(card.getByTestId('watch-responsible')).toHaveTextContent('Anna Ek')
    expect(card.getByText(/30 september 2026/)).toBeInTheDocument()
    // The document is named where it can also be opened.
    expect(card.getByTestId('citation-chip')).toHaveTextContent('Städavtal 2024')
  })

  it('namnger källdokumentet även när det inte finns någon passage att öppna', async () => {
    listWatches.mockResolvedValue(
      board({ buckets: { overdue: [], soon: [], later: [watch({ citations: [] })], recurring: [] } }),
    )

    render(<Bevakningar brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('watch'))
    expect(card.getByText('Källa')).toBeInTheDocument()
    expect(card.getByText('Städavtal 2024')).toBeInTheDocument()
  })

  it('öppnar avtalet på den citerade sidan med passagen markerad', async () => {
    listWatches.mockResolvedValue(
      board({ buckets: { overdue: [], soon: [], later: [watch()], recurring: [] } }),
    )
    getExtraction.mockResolvedValue(extraction())

    render(<Bevakningar brfId="gjutformen-12" />)
    fireEvent.click(await screen.findByTestId('citation-chip'))

    const sheet = await screen.findByRole('dialog', { name: /Källa: Städavtal 2024/ })
    expect(await within(sheet).findByText(/Sida 4 av 12/)).toBeInTheDocument()
    expect(within(sheet).getByText(/Verifierat ordagrant i dokumentet/)).toBeInTheDocument()
    expect(within(sheet).getByText(/tre månader före avtalstidens utgång/)).toBeInTheDocument()
    // The passage is placed on the page, not merely named above it.
    expect(within(sheet).getAllByTestId('citation-highlight').length).toBeGreaterThan(0)
  })

  it('visar förslag för sig, som förslag, med godkännandet någon annanstans', async () => {
    listWatches.mockResolvedValue(
      board({ proposed: [watch({ id: 'w-proposed', status: 'proposed', status_label: 'väntar på godkännande' })] }),
    )

    render(<Bevakningar brfId="gjutformen-12" />)

    const card = await screen.findByTestId('watch')
    expect(card.dataset.status).toBe('proposed')
    // Not in a bucket, and its own heading says what it is.
    expect(screen.getByRole('heading', { level: 2, name: 'Förslag, inte beslutade' })).toBeInTheDocument()
    expect(screen.getByText(/Föreningen har inte åtagit sig något av det här/)).toBeInTheDocument()
    expect(within(card).getByText('väntar på godkännande')).toBeInTheDocument()
  })

  it('visar olösta tidsvillkor med vad, varför och citat', async () => {
    listWatches.mockResolvedValue(board({ unresolved: [unresolved()] }))

    render(<Bevakningar brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('unresolved'))
    expect(card.getByText('Garantitiden är fem år från slutbesiktningen.')).toBeInTheDocument()
    expect(card.getByTestId('unresolved-why')).toHaveTextContent(
      'Slutbesiktningens datum står inte i handlingen',
    )
    expect(card.getByTestId('citation-chip')).toBeInTheDocument()
    // A real answer, not an error dressed up as one.
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('Inga bevakningar ännu')).toBeNull()
  })

  it('har ett eget tomtillstånd, inte en spinnare som aldrig tar slut', async () => {
    listWatches.mockResolvedValue(board())

    render(<Bevakningar brfId="gjutformen-12" />)

    expect(await screen.findByText('Inga bevakningar ännu')).toBeInTheDocument()
    expect(screen.getByText(/godkänns i webbappen/)).toBeInTheDocument()
    expect(screen.queryByTestId('watch')).toBeNull()
    expect(screen.queryByTestId('watch-group')).toBeNull()
  })

  it('säger en gång att bevakningar sköts i webbappen, och har ingenting att trycka på', async () => {
    listWatches.mockResolvedValue(fullBoard())

    render(<Bevakningar brfId="gjutformen-12" />)
    await screen.findAllByTestId('watch')

    expect(screen.getAllByTestId('readonly-note')).toHaveLength(1)
    expect(screen.getByTestId('readonly-note')).toHaveTextContent(
      'Läsvy. Att godkänna, ändra eller markera en bevakning som avklarad görs i webbappen.',
    )
    // Every control on the screen is a source. There is nothing else to press:
    // no approve, no dismiss, no complete, not even a disabled one.
    expect(screen.getAllByRole('button')).toHaveLength(screen.getAllByTestId('citation-chip').length)
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  })

  it('klienten har ingen skrivmetod för bevakningar över huvud taget', async () => {
    const actual = await vi.importActual<typeof import('../api/client')>('../api/client')

    // The backend has scan, decision and delete. None of them exists here, so
    // a write from the phone does not compile.
    expect(Object.keys(actual.api).filter((name) => /watch/i.test(name))).toEqual(['listWatches'])
  })

  it('säger till när bevakningarna inte gick att hämta', async () => {
    listWatches.mockRejectedValue(new ApiError('boom', 500))

    render(<Bevakningar brfId="gjutformen-12" />)

    expect(await screen.findByText('Bevakningarna kunde inte hämtas')).toBeInTheDocument()
    // Not the empty state: "nothing came back" and "there is nothing" are
    // different things to tell someone.
    expect(screen.queryByText('Inga bevakningar ännu')).toBeNull()
  })

  it('säger att bevakningarna inte ligger på telefonen när man är offline', async () => {
    listWatches.mockRejectedValue(new OfflineError())

    render(<Bevakningar brfId="gjutformen-12" />)

    expect(await screen.findByText('Du är offline')).toBeInTheDocument()
    expect(screen.getByText(/hämtas när du är uppkopplad igen/)).toBeInTheDocument()
  })

  it('hämtar bevakningarna för den aktiva föreningen, aldrig för ett id den hittat på', async () => {
    listWatches.mockResolvedValue(board())

    render(<Bevakningar brfId="gjutformen-12" />)
    await screen.findByText('Inga bevakningar ännu')

    expect(listWatches).toHaveBeenCalledWith('gjutformen-12')
  })
})
