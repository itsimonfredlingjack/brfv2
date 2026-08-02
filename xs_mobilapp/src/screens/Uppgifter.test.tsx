import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, OfflineError, api } from '../api/client'
import type { Citation, Extraction, Task, TaskBoard, TaskEvent } from '../api/types'
import { Uppgifter } from './Uppgifter'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: { ...actual.api, listTasks: vi.fn(), getExtraction: vi.fn() },
  }
})

const listTasks = vi.mocked(api.listTasks)
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

function event(overrides: Partial<TaskEvent> = {}): TaskEvent {
  return {
    id: 'e-1',
    at: '2026-07-02T07:40:00+00:00',
    by: 'bo@gjutformen12.se',
    kind: 'created',
    from_value: '',
    to_value: '',
    note: '',
    kind_label: 'skapad',
    ...overrides,
  }
}

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 't-1',
    tenant_id: 'gjutformen-12',
    title: 'Säg upp städavtalet',
    description: '',
    status: 'open',
    responsible: 'Anna Ek',
    due_date: '2026-09-30',
    origin: {
      kind: 'watch',
      ref_id: 'w-1',
      label: 'Säg upp eller ompröva städavtalet senast 2026-09-30',
      kind_label: 'Bevakning',
    },
    citations: [citation()],
    source_document_id: 'doc-1',
    source_document_name: 'Städavtal 2024',
    created_by: 'bo@gjutformen12.se',
    created_at: '2026-07-02T07:40:00+00:00',
    activity: [event()],
    status_label: 'att göra',
    active: true,
    overdue: false,
    days_left: 59,
    last_activity_at: '2026-07-02T07:40:00+00:00',
    ...overrides,
  }
}

/** Empty by default: each test fills only what it is about. The labels are the
 * server's own (backend/app/tasks/models.py) — the screen renders them and
 * never substitutes its own. */
function board(overrides: Partial<TaskBoard> = {}): TaskBoard {
  return {
    today: '2026-08-02',
    active: [],
    done: [],
    cancelled: [],
    statusLabels: {
      open: 'att göra',
      in_progress: 'pågår',
      blocked: 'blockerad',
      done: 'klar',
      cancelled: 'avbruten',
    },
    originLabels: {
      finding: 'Fakturagranskning',
      watch: 'Bevakning',
      source_event: 'Inkommande post',
      manual: 'Skapad för hand',
    },
    counts: { active: 0, overdue: 0, unassigned: 0 },
    ...overrides,
  }
}

/** The order the server sends: overdue first, then by date, undated last. */
function fullBoard(): TaskBoard {
  return board({
    active: [
      task({
        id: 't-overdue',
        title: 'Beställ OVK-besiktning',
        status: 'in_progress',
        status_label: 'pågår',
        due_date: '2026-07-20',
        days_left: -13,
        overdue: true,
      }),
      task({ id: 't-soon', title: 'Skicka in brandskyddskontrollen', due_date: '2026-08-20', days_left: 18 }),
      task({
        id: 't-blocked',
        title: 'Byt ut portkoden',
        status: 'blocked',
        status_label: 'blockerad',
        due_date: '2026-09-30',
        days_left: 59,
        activity: [
          event(),
          event({
            id: 'e-block',
            kind: 'status_changed',
            from_value: 'open',
            to_value: 'blocked',
            note: 'Väntar på offert från låssmeden.',
            kind_label: 'status ändrad',
          }),
        ],
      }),
      task({ id: 't-undated', title: 'Se över städrutinerna', due_date: null, days_left: null }),
    ],
    counts: { active: 4, overdue: 1, unassigned: 0 },
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

const cardFor = (status: string): HTMLElement => {
  const card = screen.getAllByTestId('task').find((element) => element.dataset.status === status)
  if (!card) throw new Error(`ingen uppgift med status ${status}`)
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

describe('Uppgifter', () => {
  it('visar det aktiva arbetet i serverns ordning, utan att sortera om', async () => {
    listTasks.mockResolvedValue(fullBoard())

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Beställ OVK-besiktning',
      'Skicka in brandskyddskontrollen',
      'Byt ut portkoden',
      'Se över städrutinerna',
    ])
  })

  it('renderar statusetiketterna som de kommer från servern', async () => {
    listTasks.mockResolvedValue(fullBoard())

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    expect(within(cardFor('in_progress')).getByText('pågår')).toBeInTheDocument()
    expect(within(cardFor('open')).getByText('att göra')).toBeInTheDocument()
    expect(within(cardFor('blocked')).getByText('blockerad')).toBeInTheDocument()
  })

  it('skiljer en försenad uppgift från en kommande i text, inte bara i färg', async () => {
    listTasks.mockResolvedValue(fullBoard())

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    const late = within(cardFor('in_progress'))
    expect(late.getByText('Försenad')).toBeInTheDocument()
    expect(late.getByText(/13 dagar sedan/)).toBeInTheDocument()

    const coming = within(cardFor('open'))
    expect(coming.getByText(/om 18 dagar/)).toBeInTheDocument()
    expect(coming.queryByText('Försenad')).toBeNull()
  })

  it('säger att en uppgift saknar datum i stället för att lämna raden tom', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task({ due_date: null, days_left: null })], counts: { active: 1, overdue: 0, unassigned: 0 } }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByTestId('task-due')).toHaveTextContent('Inget datum satt')
  })

  it('säger vilken dag räkningen utgår från', async () => {
    listTasks.mockResolvedValue(fullBoard())

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByTestId('task-asof')).toHaveTextContent('Räknat från 2 augusti 2026')
  })

  it('läser tom ansvarig som "ej utsedd", aldrig som blank', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task({ responsible: '' })], counts: { active: 1, overdue: 0, unassigned: 1 } }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('task'))
    expect(card.getByTestId('task-responsible')).toHaveTextContent('ej utsedd')
    expect(card.getByText('Ansvarig')).toBeInTheDocument()
  })

  it('säger hur många aktiva uppgifter som saknar ansvarig', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task({ responsible: '' })], counts: { active: 4, overdue: 1, unassigned: 2 } }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByTestId('task-counts')).toHaveTextContent(
      '4 aktiva uppgifter, varav 1 är försenad och 2 saknar ansvarig.',
    )
  })

  it('namnger varifrån arbetet kom och vad den saken sa', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task()], counts: { active: 1, overdue: 0, unassigned: 0 } }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByTestId('task-origin')).toHaveTextContent(
      'Bevakning · Säg upp eller ompröva städavtalet senast 2026-09-30',
    )
  })

  it('visar vem som gjorde vad, när, och från vad till vad, för varje sorts händelse', async () => {
    listTasks.mockResolvedValue(
      board({
        active: [
          task({
            activity: [
              event({ id: 'e-created', kind: 'created', by: 'bo@gjutformen12.se', kind_label: 'skapad' }),
              event({
                id: 'e-assigned',
                kind: 'assigned',
                by: 'bo@gjutformen12.se',
                at: '2026-07-03T09:00:00+00:00',
                from_value: '',
                to_value: 'Anna Ek',
                kind_label: 'ansvarig ändrad',
              }),
              event({
                id: 'e-due',
                kind: 'due_changed',
                by: 'anna@gjutformen12.se',
                at: '2026-07-10T11:15:00+00:00',
                from_value: '2026-09-30',
                to_value: '2026-10-15',
                kind_label: 'datum ändrat',
              }),
              event({
                id: 'e-status',
                kind: 'status_changed',
                by: 'anna@gjutformen12.se',
                at: '2026-07-20T08:05:00+00:00',
                from_value: 'open',
                to_value: 'in_progress',
                kind_label: 'status ändrad',
              }),
              event({
                id: 'e-edited',
                kind: 'edited',
                by: 'anna@gjutformen12.se',
                at: '2026-07-21T08:05:00+00:00',
                to_value: 'Säg upp städavtalet',
                kind_label: 'text ändrad',
              }),
              event({
                id: 'e-noted',
                kind: 'noted',
                by: 'anna@gjutformen12.se',
                at: '2026-07-28T16:00:00+00:00',
                note: 'Ringde leverantören, väntar på skriftligt besked.',
                kind_label: 'kommentar',
              }),
            ],
          }),
        ],
        counts: { active: 1, overdue: 0, unassigned: 0 },
      }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findByTestId('task')

    // Nothing is dropped: three stand open, the rest are one tap away.
    fireEvent.click(screen.getByTestId('trail-more'))
    const events = screen.getAllByTestId('trail-event')
    expect(events).toHaveLength(6)

    const byKind = (kind: string): HTMLElement => {
      const found = events.find((element) => element.dataset.kind === kind)
      if (!found) throw new Error(`ingen händelse av sorten ${kind}`)
      return found
    }

    const created = within(byKind('created'))
    expect(created.getByText('skapad')).toBeInTheDocument()
    expect(created.getByText('bo@gjutformen12.se')).toBeInTheDocument()
    // The record's own instant, machine-readable as well as legible.
    expect(byKind('created').querySelector('time')).toHaveAttribute(
      'datetime',
      '2026-07-02T07:40:00+00:00',
    )

    // An unassigned "from" is a fact about the record, not a blank.
    expect(within(byKind('assigned')).getByText('från ej utsedd till Anna Ek')).toBeInTheDocument()
    expect(
      within(byKind('due_changed')).getByText('från 30 september 2026 till 15 oktober 2026'),
    ).toBeInTheDocument()
    // Status codes are read out through the server's own words.
    expect(within(byKind('status_changed')).getByText('från att göra till pågår')).toBeInTheDocument()
    expect(within(byKind('edited')).getByText('text ändrad')).toBeInTheDocument()
    expect(
      within(byKind('noted')).getByText(/Ringde leverantören, väntar på skriftligt besked/),
    ).toBeInTheDocument()
    expect(within(byKind('noted')).getByText('anna@gjutformen12.se')).toBeInTheDocument()
  })

  it('viker ihop en lång historik i stället för att kapa den', async () => {
    listTasks.mockResolvedValue(
      board({
        active: [
          task({
            activity: Array.from({ length: 7 }, (_, index) =>
              event({
                id: `e-${index}`,
                kind: 'noted',
                kind_label: 'kommentar',
                note: `Anteckning ${index}`,
                at: `2026-07-0${index + 1}T09:00:00+00:00`,
              }),
            ),
          }),
        ],
        counts: { active: 1, overdue: 0, unassigned: 0 },
      }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findByTestId('task')

    expect(screen.getByTestId('trail-more')).toHaveTextContent('Visa 4 äldre händelser')
    // Newest first: the most recent note is the one standing open.
    expect(screen.getAllByTestId('trail-event')[0]).toHaveTextContent('Anteckning 6')
    expect(screen.getAllByTestId('trail-event')).toHaveLength(7)
  })

  it('visar skälet en blockerad uppgift bär med sig', async () => {
    listTasks.mockResolvedValue(fullBoard())

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    const blocked = within(cardFor('blocked'))
    expect(blocked.getByTestId('task-reason')).toHaveTextContent(
      'Blockerad därför att: Väntar på offert från låssmeden.',
    )
  })

  it('håller klart och avbrutet arbete för sig, och avbrutet bär sitt skäl', async () => {
    listTasks.mockResolvedValue(
      board({
        active: [task()],
        done: [
          task({
            id: 't-done',
            title: 'Teckna nytt hissavtal',
            status: 'done',
            status_label: 'klar',
            active: false,
            days_left: -3,
          }),
        ],
        cancelled: [
          task({
            id: 't-cancelled',
            title: 'Byt ut cykelställen',
            status: 'cancelled',
            status_label: 'avbruten',
            active: false,
            activity: [
              event(),
              event({
                id: 'e-cancel',
                kind: 'status_changed',
                from_value: 'open',
                to_value: 'cancelled',
                note: 'Stämman beslutade att skjuta upp till nästa år.',
                kind_label: 'status ändrad',
              }),
            ],
          }),
        ],
        counts: { active: 1, overdue: 0, unassigned: 0 },
      }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    // Under their own headings, not mixed into the active list.
    expect(screen.getByRole('heading', { level: 2, name: 'Aktiva uppgifter' })).toBeInTheDocument()
    const done = within(screen.getByTestId('task-group-done'))
    expect(done.getByRole('heading', { level: 2, name: 'Klara' })).toBeInTheDocument()
    expect(done.getByTestId('task')).toHaveAttribute('data-status', 'done')
    // A finished task's date is history, not a countdown.
    expect(done.getByTestId('task-due')).toHaveTextContent('30 september 2026')
    expect(done.getByTestId('task-due')).not.toHaveTextContent('sedan')

    const cancelled = within(screen.getByTestId('task-group-cancelled'))
    expect(cancelled.getByRole('heading', { level: 2, name: 'Avbrutna' })).toBeInTheDocument()
    expect(cancelled.getByTestId('task-reason')).toHaveTextContent(
      'Avbruten därför att: Stämman beslutade att skjuta upp till nästa år.',
    )
  })

  it('öppnar avtalet på den citerade sidan med passagen markerad', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task()], counts: { active: 1, overdue: 0, unassigned: 0 } }),
    )
    getExtraction.mockResolvedValue(extraction())

    render(<Uppgifter brfId="gjutformen-12" />)
    fireEvent.click(await screen.findByTestId('citation-chip'))

    const sheet = await screen.findByRole('dialog', { name: /Källa: Städavtal 2024/ })
    expect(await within(sheet).findByText(/Sida 4 av 12/)).toBeInTheDocument()
    expect(within(sheet).getByText(/Verifierat ordagrant i dokumentet/)).toBeInTheDocument()
    expect(within(sheet).getByText(/tre månader före avtalstidens utgång/)).toBeInTheDocument()
    // The passage is placed on the page, not merely named above it.
    expect(within(sheet).getAllByTestId('citation-highlight').length).toBeGreaterThan(0)
  })

  it('namnger källdokumentet även när det inte finns någon passage att öppna', async () => {
    listTasks.mockResolvedValue(
      board({ active: [task({ citations: [] })], counts: { active: 1, overdue: 0, unassigned: 0 } }),
    )

    render(<Uppgifter brfId="gjutformen-12" />)

    const card = within(await screen.findByTestId('task'))
    expect(card.getByText('Källa')).toBeInTheDocument()
    expect(card.getByText('Städavtal 2024')).toBeInTheDocument()
  })

  it('har ett eget tomtillstånd, inte en spinnare som aldrig tar slut', async () => {
    listTasks.mockResolvedValue(board())

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByText('Inga uppgifter ännu')).toBeInTheDocument()
    expect(screen.getByText(/skapas ur ett fynd, en bevakning eller inkommande post i webbappen/)).toBeInTheDocument()
    expect(screen.queryByTestId('task')).toBeNull()
    expect(screen.queryByTestId('task-group')).toBeNull()
    expect(screen.queryByTestId('task-counts')).toBeNull()
  })

  it('säger en gång att uppgifter sköts i webbappen, och har ingenting att ändra med', async () => {
    listTasks.mockResolvedValue(fullBoard())

    const { container } = render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findAllByTestId('task')

    expect(screen.getAllByTestId('readonly-note')).toHaveLength(1)
    expect(screen.getByTestId('readonly-note')).toHaveTextContent(
      'Läsvy. Att lägga upp en uppgift, ändra status, utse ansvarig eller skriva i historiken görs i webbappen.',
    )

    // Every button on the screen opens a source. There is nothing else to
    // press: no status control, no assign, no comment, not a disabled one.
    const buttons = Array.from(container.querySelectorAll('button'))
    expect(buttons.length).toBeGreaterThan(0)
    expect(buttons.every((button) => button.dataset.testid === 'citation-chip')).toBe(true)
    // Nothing to type in, tick or pick from either.
    expect(container.querySelectorAll('input, textarea, select, form')).toHaveLength(0)
    expect(container.querySelectorAll('[disabled], [aria-disabled="true"]')).toHaveLength(0)
  })

  it('klienten har ingen skrivmetod för uppgifter över huvud taget', async () => {
    const actual = await vi.importActual<typeof import('../api/client')>('../api/client')

    // The backend has create, update and comment. None of them exists here, so
    // a write from the phone does not compile.
    expect(Object.keys(actual.api).filter((name) => /task/i.test(name))).toEqual(['listTasks'])
  })

  it('säger till när uppgifterna inte gick att hämta', async () => {
    listTasks.mockRejectedValue(new ApiError('boom', 500))

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByText('Uppgifterna kunde inte hämtas')).toBeInTheDocument()
    // Not the empty state: "nothing came back" and "there is nothing" are
    // different things to tell someone.
    expect(screen.queryByText('Inga uppgifter ännu')).toBeNull()
  })

  it('säger att uppgifterna inte ligger på telefonen när man är offline', async () => {
    listTasks.mockRejectedValue(new OfflineError())

    render(<Uppgifter brfId="gjutformen-12" />)

    expect(await screen.findByText('Du är offline')).toBeInTheDocument()
    expect(screen.getByText(/hämtas när du är uppkopplad igen/)).toBeInTheDocument()
  })

  it('hämtar uppgifterna för den aktiva föreningen, aldrig för ett id den hittat på', async () => {
    listTasks.mockResolvedValue(board())

    render(<Uppgifter brfId="gjutformen-12" />)
    await screen.findByText('Inga uppgifter ännu')

    expect(listTasks).toHaveBeenCalledWith('gjutformen-12')
  })
})
