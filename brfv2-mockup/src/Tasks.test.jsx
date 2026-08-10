import React from 'react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Tasks from './components/Tasks';
import Watches from './components/Watches';
import InvoiceCase from './components/InvoiceCase';
import { integrationsApi, invoicesApi, tasksApi, watchesApi } from './api';
import { datumTid } from './components/datum';

// PdfPane pulls in pdfjs-dist, which needs browser canvas APIs jsdom lacks.
vi.mock('./components/PdfPane', () => ({
  default: () => <div data-testid="pdf-pane" />,
}));

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {
    format: vi.fn(),
    connections: vi.fn(),
    listSourceEvents: vi.fn(),
    listInvoices: vi.fn(),
    listFindings: vi.fn(),
    listSupplierAliases: vi.fn(),
    availableInvoices: vi.fn(),
    decideFinding: vi.fn(),
    reviewInvoice: vi.fn(),
    addSupplierAlias: vi.fn(),
    deleteSupplierAlias: vi.fn(),
    mappingPreview: vi.fn(),
  },
  invoicesApi: {
    workspace: vi.fn(),
    case: vi.fn(),
    importInvoice: vi.fn(),
    refresh: vi.fn(),
    update: vi.fn(),
    comment: vi.fn(),
  },
  watchesApi: {
    board: vi.fn(),
    scan: vi.fn(),
    decide: vi.fn(),
    remove: vi.fn(),
  },
  tasksApi: {
    list: vi.fn(),
    forOrigin: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    comment: vi.fn(),
  },
}));

const CITATION = {
  document_id: 'doc-contract',
  document_name: 'Snöröjningsavtal 2026.pdf',
  page: 3,
  quote: 'Besiktning ska ske vart tredje år av behörig besiktningsman',
  quotes: ['Besiktning ska ske vart tredje år av behörig besiktningsman'],
  chunk_id: 'c7',
  rects: [[72, 120, 430, 134]],
  score: 1.0,
  approximate: false,
  corpus_origin: 'synthetic',
};

const STATUS_LABELS = {
  open: 'att göra',
  in_progress: 'pågår',
  blocked: 'blockerad',
  done: 'klar',
  cancelled: 'avbruten',
};

const ORIGIN_LABELS = {
  finding: 'Fakturagranskning',
  watch: 'Bevakning',
  source_event: 'Inkommande post',
  manual: 'Skapad för hand',
};

/** The same stamp the components render, so "when" is asserted, not guessed.
    It defers to the formatter rather than restating it — restating it is how
    this assertion silently stopped matching the product it was checking. */
const when = (iso) => datumTid(iso);

const event = (overrides) => ({
  id: 'e1',
  at: '2026-08-01T09:00:00+00:00',
  by: 'user-1',
  kind: 'created',
  from_value: '',
  to_value: '',
  note: '',
  kind_label: 'skapad',
  ...overrides,
});

/** A task as the list endpoint serves it, computed fields and all. */
const task = (overrides) => ({
  id: 't1',
  tenant_id: 'brf-a',
  title: 'Begär in offert på fasadarbetet',
  description: '',
  status: 'open',
  responsible: '',
  due_date: null,
  origin: { kind: 'manual', ref_id: '', label: '', kind_label: 'Skapad för hand' },
  citations: [],
  source_document_id: '',
  source_document_name: '',
  created_by: 'user-1',
  created_at: '2026-08-01T09:00:00+00:00',
  activity: [event({})],
  status_label: 'att göra',
  active: true,
  overdue: false,
  days_left: null,
  last_activity_at: '2026-08-01T09:00:00+00:00',
  ...overrides,
});

/** Past its date and still open. */
const OVERDUE = task({
  id: 't-late',
  title: 'Säg upp snöröjningsavtalet',
  status: 'in_progress',
  status_label: 'pågår',
  responsible: 'Ordförande Ek',
  due_date: '2026-07-30',
  days_left: -3,
  overdue: true,
});

/** Nobody named. The number that grows quietly. */
const UNASSIGNED = task({
  id: 't-open',
  title: 'Boka besiktning av ventilationen',
  due_date: '2026-08-20',
  days_left: 18,
});

/** Made from a watch: the evidence travelled with it, and so did the history. */
const FROM_WATCH = task({
  id: 't-watch',
  title: 'Boka besiktningen inför 2026-12-12',
  description: 'Behörig besiktningsman enligt avtalet.',
  status: 'blocked',
  status_label: 'blockerad',
  responsible: 'Ordförande Ek',
  due_date: '2026-09-01',
  days_left: 30,
  origin: {
    kind: 'watch',
    ref_id: 'w4',
    label: 'Återkommande kontroll, nästa gång 2026-12-12 (2026-12-12)',
    kind_label: 'Bevakning',
  },
  citations: [CITATION],
  source_document_id: 'doc-contract',
  source_document_name: 'Snöröjningsavtal 2026.pdf',
  activity: [
    event({ id: 'e1', kind: 'created', kind_label: 'skapad', to_value: 'Boka besiktningen inför 2026-12-12', note: 'Återkommande kontroll, nästa gång 2026-12-12 (2026-12-12)' }),
    event({ id: 'e2', at: '2026-08-01T10:00:00+00:00', by: 'user-2', kind: 'assigned', kind_label: 'ansvarig ändrad', from_value: '', to_value: 'Ordförande Ek' }),
    event({ id: 'e3', at: '2026-08-01T10:05:00+00:00', by: 'user-2', kind: 'due_changed', kind_label: 'datum ändrat', from_value: '', to_value: '2026-09-01' }),
    event({
      id: 'e4',
      at: '2026-08-02T08:00:00+00:00',
      by: 'user-1',
      kind: 'status_changed',
      kind_label: 'status ändrad',
      from_value: 'open',
      to_value: 'blocked',
      note: 'Väntar på att besiktningsmannen svarar.',
    }),
  ],
  last_activity_at: '2026-08-02T08:00:00+00:00',
});

const DONE = task({
  id: 't-done',
  title: 'Teckna nytt städavtal',
  status: 'done',
  status_label: 'klar',
  active: false,
  responsible: 'Kassör Lund',
  due_date: '2026-07-01',
  days_left: -32,
  activity: [
    event({ id: 'd1', kind: 'created', kind_label: 'skapad' }),
    event({
      id: 'd2',
      at: '2026-07-01T11:00:00+00:00',
      by: 'user-3',
      kind: 'status_changed',
      kind_label: 'status ändrad',
      from_value: 'open',
      to_value: 'done',
    }),
  ],
  last_activity_at: '2026-07-01T11:00:00+00:00',
});

const CANCELLED = task({
  id: 't-cancelled',
  title: 'Byt portkod',
  status: 'cancelled',
  status_label: 'avbruten',
  active: false,
  responsible: 'Ordförande Ek',
  activity: [
    event({ id: 'c1', kind: 'created', kind_label: 'skapad' }),
    event({
      id: 'c2',
      at: '2026-07-20T14:30:00+00:00',
      by: 'user-2',
      kind: 'status_changed',
      kind_label: 'status ändrad',
      from_value: 'open',
      to_value: 'cancelled',
      note: 'Låssystemet byts ut i höst, koden ska inte röras dessförinnan.',
    }),
  ],
  last_activity_at: '2026-07-20T14:30:00+00:00',
});

function mountTasks({
  active = [UNASSIGNED],
  done = [],
  cancelled = [],
  counts,
  isAdmin = true,
} = {}) {
  tasksApi.list.mockResolvedValue({
    today: '2026-08-02',
    active,
    done,
    cancelled,
    statusLabels: STATUS_LABELS,
    originLabels: ORIGIN_LABELS,
    counts: counts || {
      active: active.length,
      overdue: active.filter((t) => t.overdue).length,
      unassigned: active.filter((t) => !t.responsible).length,
    },
  });
  const onOpenCitation = vi.fn();
  render(<Tasks brfId="brf-a" isAdmin={isAdmin} onOpenCitation={onOpenCitation} />);
  return { onOpenCitation };
}

/** One approved watch, so the card that offers to make work out of it exists. */
const WATCH = {
  id: 'w4',
  tenant_id: 'brf-a',
  kind: 'inspection',
  status: 'approved',
  title: 'Återkommande kontroll, nästa gång 2026-12-12',
  due_date: '2026-12-12',
  derived_due_date: '2026-12-12',
  derivation: '2023-12-12 plus ett intervall (triennial)',
  recurrence: 'none',
  responsible: 'Fastighetsskötare Nilsson',
  remind_lead_days: 30,
  citations: [CITATION],
  source_document_id: 'doc-contract',
  source_document_name: 'Snöröjningsavtal 2026.pdf',
  created_at: '2026-08-01T09:00:00+00:00',
  decided_by: 'user-1',
  decided_at: '2026-08-01T09:32:00+00:00',
  decision_note: null,
  succeeded_by: null,
  kind_label: 'Besiktning eller kontroll',
  status_label: 'bevakas',
  remind_at: '2026-11-12',
  bucket: 'later',
  days_left: 132,
  next_due_after: null,
};

function mountWatches({ existing = [] } = {}) {
  watchesApi.board.mockResolvedValue({
    today: '2026-08-02',
    proposed: [],
    buckets: { overdue: [], soon: [], later: [WATCH], recurring: [] },
    bucketLabels: {
      overdue: 'Försenat', soon: 'Snart', later: 'Senare', recurring: 'Återkommande',
    },
    kindLabels: {},
    statusLabels: {},
    settled: [],
    unresolved: [],
  });
  tasksApi.forOrigin.mockResolvedValue(existing);
  render(<Watches brfId="brf-a" isAdmin onOpenCitation={vi.fn()} />);
}

/** One read invoice and one finding about it — the other card that offers work. */
const INVOICE = {
  id: 'inv1',
  tenant_id: 'brf-a',
  adapter: 'fixture-accounting',
  external_ref: 'SI-2026-114',
  supplier_name: 'Snösvängen Entreprenad AB',
  invoice_number: '2026-114',
  invoice_date: '2026-02-03',
  period_start: '',
  period_end: '',
  total_amount: '6250.00',
  currency: 'SEK',
  vat_amount: '1250.00',
  lines: [],
  retrieved_at: '2026-08-01T10:05:00+00:00',
  source_dataset: 'gjutformen12-2026.json',
  content_sha256: '0'.repeat(64),
};

const FINDING = {
  id: 'f1',
  tenant_id: 'brf-a',
  finding_type: 'invoice_contract_amount',
  created_at: '2026-08-01T10:06:00+00:00',
  invoice_id: 'inv1',
  verdict: 'possible_deviation',
  verdict_label: 'möjlig avvikelse',
  verified_facts: [],
  suggestion: 'Kontrollera à-priset mot det citerade villkoret innan fakturan betalas.',
  suggested_by: 'regelmotor',
  uncertainty: 'Jämförelsen gäller det citerade villkoret och ingenting annat.',
  citations: [CITATION],
  anchor_strength: 'exact',
  anchor_note: '',
  alias_proposal: null,
  status: 'open',
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

/** The invoice case, which is where a finding is turned into work. */
function mountInvoiceCase() {
  integrationsApi.connections.mockResolvedValue({
    'microsoft-graph': { provider: 'microsoft-graph', configured: false, connection: null },
    fortnox: { provider: 'fortnox', configured: false, connection: null },
  });
  invoicesApi.case.mockResolvedValue({
    today: '2026-08-02',
    case: {
      id: 'case-1',
      supplier_name: 'Snösvängen Entreprenad AB',
      supplier_ref: '556812-3344',
      invoice_number: '2026-114',
      invoice_date: '2026-02-03',
      due_date: '2026-03-05',
      total_amount: '6250.00',
      currency: 'SEK',
      vat_amount: '1250.00',
      identity_basis: 'Leverantör och fakturanummer är båda kända.',
      observations: [],
      source_status: null,
      source_status_label: '',
      review_status: 'not_reviewed',
      review_status_label: 'Ej granskad',
      review_status_caveat: 'Ingen här har tagit ställning till fakturan ännu.',
      review_status_note: '',
      review_status_by: '',
      review_status_at: '',
      responsible: '',
      signals: [],
      top_signal: null,
      timeline: [],
      comments: [],
      open: true,
      overdue: false,
    },
    invoice: INVOICE,
    findings: [FINDING],
    documents: [],
    sourceEvent: null,
    supplier: {
      supplier_name: 'Snösvängen Entreprenad AB',
      org_numbers: [],
      invoice_count: 1,
      amount_low: null,
      amount_high: null,
      currency: 'SEK',
      previous: [],
      documents: [],
      deviation_count: 0,
      aliases: [],
      tasks: [],
      responsibles: [],
    },
    tasks: [],
    labels: {
      reviewStatus: { not_reviewed: 'Ej granskad', closed: 'Granskning avslutad' },
      reviewStatusCaveats: { not_reviewed: '…', closed: '…' },
      signals: {},
      signalSeverity: {},
      verdicts: {},
    },
  });
  tasksApi.forOrigin.mockResolvedValue([]);
  render(<InvoiceCase brfId="brf-a" caseId="case-1" isAdmin onOpenCitation={vi.fn()} />);
}

const cardFor = (title) => screen.getByText(title).closest('article');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the active list', () => {
  it('says in words that a task is late, not only in colour', async () => {
    mountTasks({ active: [OVERDUE] });
    await screen.findByText(OVERDUE.title);
    const card = cardFor(OVERDUE.title);

    expect(within(card).getByText('försenad')).toBeInTheDocument();
    expect(within(card).getByText('2026-07-30 · 3 dagar försenat')).toBeInTheDocument();
  });

  it('reads an unnamed responsible as “ej utsedd”, and counts them', async () => {
    mountTasks({ active: [UNASSIGNED, OVERDUE] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    expect(within(card).getByText('ej utsedd')).toBeInTheDocument();
    expect(within(card).getByText('2026-08-20 · om 18 dagar')).toBeInTheDocument();

    // And the same fact as a number somebody can act on. The three numerals
    // live in the masthead band's instrument now, not in a counter row on the
    // paper below it — same three readings, one home.
    const counts = document.querySelector('.instrument-readings');
    const unassigned = within(counts).getByText('Utan ansvarig').closest('div');
    expect(within(unassigned).getByText('1')).toBeInTheDocument();
    expect(screen.getByText(/1 av 2 pågående uppgifter har ingen namngiven ansvarig/))
      .toBeInTheDocument();
  });

  it('says an undated task is undated rather than leaving the field blank', async () => {
    mountTasks({ active: [task({})] });
    await screen.findByText('Begär in offert på fasadarbetet');
    expect(screen.getByText('inget datum satt')).toBeInTheDocument();
  });

  it('keeps the order the server sent, without re-sorting it', async () => {
    mountTasks({ active: [OVERDUE, UNASSIGNED, task({ id: 't-last' })] });
    await screen.findByText(OVERDUE.title);

    const titles = [...document.querySelectorAll('.tasks-active .task-title')]
      .map((node) => node.textContent);
    expect(titles).toEqual([OVERDUE.title, UNASSIGNED.title, 'Begär in offert på fasadarbetet']);
  });

  it('opens the passage the work came out of', async () => {
    const { onOpenCitation } = mountTasks({ active: [FROM_WATCH] });
    await screen.findByText(FROM_WATCH.title);
    const card = cardFor(FROM_WATCH.title);

    expect(within(card).getByText(/Bevakning — Återkommande kontroll/)).toBeInTheDocument();
    fireEvent.click(within(card).getByTitle('Öppna Snöröjningsavtal 2026.pdf sida 3'));
    expect(onOpenCitation).toHaveBeenCalledWith(CITATION);
  });
});

describe('the activity trail', () => {
  it('renders every event with who, when and what changed from what to what', async () => {
    mountTasks({ active: [FROM_WATCH] });
    await screen.findByText(FROM_WATCH.title);
    const card = cardFor(FROM_WATCH.title);

    const what = [...card.querySelectorAll('.task-event-what')].map((n) => n.textContent);
    expect(what).toEqual([
      'skapad',
      'ansvarig ändrad från ej utsedd till Ordförande Ek',
      'datum ändrat från inget datum till 2026-09-01',
      'status ändrad från att göra till blockerad',
    ]);

    // Newest last: the trail is read downwards, like the events happened.
    const stamps = [...card.querySelectorAll('.task-event-when')].map((n) => n.textContent);
    expect(stamps).toEqual([
      when('2026-08-01T09:00:00+00:00'),
      when('2026-08-01T10:00:00+00:00'),
      when('2026-08-01T10:05:00+00:00'),
      when('2026-08-02T08:00:00+00:00'),
    ]);

    const who = [...card.querySelectorAll('.task-event-who')].map((n) => n.textContent);
    expect(who).toEqual(['user-1', 'user-2', 'user-2', 'user-1']);

    expect(within(card).getByText('Väntar på att besiktningsmannen svarar.')).toBeInTheDocument();
  });

  it('is on the card, not behind a closed toggle', async () => {
    mountTasks({ active: [FROM_WATCH] });
    await screen.findByText(FROM_WATCH.title);
    const card = cardFor(FROM_WATCH.title);

    expect(card.querySelector('.task-history-earlier')).toBeNull();
    for (const line of card.querySelectorAll('.task-events')) {
      expect(line.closest('details')).toBeNull();
    }
  });

  it('folds only the oldest away when the history has grown long', async () => {
    const many = Array.from({ length: 9 }, (_, i) => event({
      id: `m${i}`,
      at: `2026-08-01T09:0${i}:00+00:00`,
      kind: 'noted',
      kind_label: 'kommentar',
      note: `kommentar nummer ${i}`,
    }));
    mountTasks({ active: [task({ id: 't-long', activity: many })] });
    await screen.findByText('Begär in offert på fasadarbetet');
    const card = cardFor('Begär in offert på fasadarbetet');

    expect(within(card).getByText('Tidigare händelser (6)')).toBeInTheDocument();
    // The three most recent stay out of the fold.
    for (const i of [6, 7, 8]) {
      const line = within(card).getByText(`kommentar nummer ${i}`);
      expect(line.closest('details')).toBeNull();
    }
    expect(within(card).getByText('kommentar nummer 0').closest('details')).not.toBeNull();
  });
});

describe('changing a task', () => {
  it('refuses to block without a reason before any request is made', async () => {
    mountTasks({ active: [UNASSIGNED] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    fireEvent.change(within(card).getByLabelText('Status'), { target: { value: 'blocked' } });
    const save = within(card).getByRole('button', { name: 'Spara ändring' });
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(tasksApi.update).not.toHaveBeenCalled();
    expect(within(card).getByText(/Skriv varför uppgiften blockeras eller avbryts/))
      .toBeInTheDocument();

    fireEvent.change(within(card).getByLabelText(/Anteckning/), {
      target: { value: 'Väntar på att besiktningsmannen svarar.' },
    });
    expect(save).toBeEnabled();

    tasksApi.update.mockResolvedValue({ ...UNASSIGNED, status: 'blocked', status_label: 'blockerad' });
    fireEvent.click(save);
    await waitFor(() => expect(tasksApi.update).toHaveBeenCalledWith('brf-a', 't-open', {
      status: 'blocked',
      note: 'Väntar på att besiktningsmannen svarar.',
    }));
  });

  it('refuses to cancel without a reason, and says the task stays', async () => {
    mountTasks({ active: [UNASSIGNED] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    fireEvent.change(within(card).getByLabelText('Status'), { target: { value: 'cancelled' } });
    expect(within(card).getByRole('button', { name: 'Spara ändring' })).toBeDisabled();
    fireEvent.click(within(card).getByRole('button', { name: 'Spara ändring' }));
    expect(tasksApi.update).not.toHaveBeenCalled();
    expect(within(card).getByText(/Uppgiften tas aldrig bort/)).toBeInTheDocument();
  });

  it('sends only what actually changed, and nothing when nothing did', async () => {
    mountTasks({ active: [UNASSIGNED] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    // A write that says nothing happened is 422 "Inget att ändra" — so it is
    // never sent.
    expect(within(card).getByRole('button', { name: 'Spara ändring' })).toBeDisabled();
    expect(within(card).getByText('Inget är ändrat än.')).toBeInTheDocument();

    fireEvent.change(within(card).getByLabelText('Ansvarig'), {
      target: { value: 'Ordförande Ek' },
    });
    tasksApi.update.mockResolvedValue({ ...UNASSIGNED, responsible: 'Ordförande Ek' });
    fireEvent.click(within(card).getByRole('button', { name: 'Spara ändring' }));

    await waitFor(() => expect(tasksApi.update).toHaveBeenCalledWith('brf-a', 't-open', {
      responsible: 'Ordförande Ek',
    }));
  });

  it('surfaces the route’s own refusal when it turns a change down anyway', async () => {
    mountTasks({ active: [UNASSIGNED] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    fireEvent.change(within(card).getByLabelText('Ansvarig'), { target: { value: 'Ordförande Ek' } });
    const refusal = new Error('Ange varför uppgiften blockeras eller avbryts.');
    refusal.status = 422;
    tasksApi.update.mockRejectedValue(refusal);

    fireEvent.click(within(card).getByRole('button', { name: 'Spara ändring' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ange varför uppgiften blockeras eller avbryts.',
    );
  });

  it('appends a plain comment without changing anything', async () => {
    mountTasks({ active: [UNASSIGNED] });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    fireEvent.change(within(card).getByLabelText('Kommentar'), {
      target: { value: 'Ringde entreprenören, de återkommer på måndag.' },
    });
    tasksApi.comment.mockResolvedValue(UNASSIGNED);
    fireEvent.click(within(card).getByRole('button', { name: 'Kommentera' }));

    await waitFor(() => expect(tasksApi.comment).toHaveBeenCalledWith(
      'brf-a', 't-open', 'Ringde entreprenören, de återkommer på måndag.',
    ));
    expect(tasksApi.update).not.toHaveBeenCalled();
  });

  it('offers no change at all to a member who cannot make one', async () => {
    mountTasks({ active: [UNASSIGNED], isAdmin: false });
    await screen.findByText(UNASSIGNED.title);

    expect(screen.queryByRole('button', { name: 'Spara ändring' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Ny uppgift/ })).toBeNull();
    expect(screen.getByText(/Bara administratörer kan skapa och ändra uppgifter/))
      .toBeInTheDocument();
  });
});

describe('work that is finished or was called off', () => {
  it('keeps cancelled work visible, with who decided it and why', async () => {
    mountTasks({ active: [], done: [DONE], cancelled: [CANCELLED] });
    await screen.findByText('Avbrutna uppgifter (1)');

    expect(screen.getByText('Klara uppgifter (1)')).toBeInTheDocument();

    const row = screen.getByText(CANCELLED.title).closest('li');
    expect(within(row).getByText(/avbruten · user-2/)).toBeInTheDocument();
    expect(within(row).getByText(
      'Anledning: Låssystemet byts ut i höst, koden ska inte röras dessförinnan.',
    )).toBeInTheDocument();

    const finished = screen.getByText(DONE.title).closest('li');
    expect(within(finished).getByText(/klar · user-3/)).toBeInTheDocument();
  });
});

describe('creating work', () => {
  it('takes the watch as origin, with the watch’s own date and responsible', async () => {
    mountWatches();
    await screen.findByText(WATCH.title);
    const card = cardFor(WATCH.title);

    fireEvent.click(within(card).getByRole('button', { name: /Skapa uppgift/ }));
    await waitFor(() => expect(tasksApi.forOrigin)
      .toHaveBeenCalledWith('brf-a', 'watch', 'w4'));

    tasksApi.create.mockResolvedValue(task({
      id: 't9',
      title: WATCH.title,
      responsible: 'Fastighetsskötare Nilsson',
      due_date: '2026-12-12',
      origin: { kind: 'watch', ref_id: 'w4', label: '…', kind_label: 'Bevakning' },
    }));
    fireEvent.click(within(card).getByRole('button', { name: 'Skapa uppgift' }));

    await waitFor(() => expect(tasksApi.create).toHaveBeenCalledWith('brf-a', {
      title: WATCH.title,
      description: '',
      responsible: 'Fastighetsskötare Nilsson',
      due_date: '2026-12-12',
      origin_kind: 'watch',
      origin_ref: 'w4',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      /Uppgift skapad.*Bevakningen är oförändrad/,
    );
  });

  it('surfaces the work that already exists instead of quietly duplicating it', async () => {
    mountWatches({
      existing: [task({
        id: 't5',
        title: 'Boka besiktningen inför 2026-12-12',
        status: 'in_progress',
        status_label: 'pågår',
        responsible: 'Ordförande Ek',
        due_date: '2026-09-01',
      })],
    });
    await screen.findByText(WATCH.title);
    const card = cardFor(WATCH.title);

    fireEvent.click(within(card).getByRole('button', { name: /Skapa uppgift/ }));
    expect(await within(card).findByText('Det finns redan en uppgift för det här'))
      .toBeInTheDocument();
    expect(within(card).getByText('Boka besiktningen inför 2026-12-12')).toBeInTheDocument();
    expect(within(card).getByText(/pågår · Ordförande Ek · 2026-09-01/)).toBeInTheDocument();

    // Creating a second one is still possible, but only as a deliberate act.
    expect(within(card).queryByRole('button', { name: 'Skapa uppgift' })).toBeNull();
    expect(within(card).getByRole('button', { name: 'Skapa ändå' })).toBeInTheDocument();
    expect(tasksApi.create).not.toHaveBeenCalled();
  });

  it('takes the finding as origin, prefilled with what the review suggested', async () => {
    mountInvoiceCase();
    const card = (await screen.findByText(FINDING.suggestion)).closest('article');

    fireEvent.click(within(card).getByRole('button', { name: /Skapa uppgift/ }));
    await waitFor(() => expect(tasksApi.forOrigin)
      .toHaveBeenCalledWith('brf-a', 'finding', 'f1'));

    tasksApi.create.mockResolvedValue(task({ id: 't8', title: FINDING.suggestion }));
    fireEvent.click(within(card).getByRole('button', { name: 'Skapa uppgift' }));

    await waitFor(() => expect(tasksApi.create).toHaveBeenCalledWith('brf-a', {
      title: FINDING.suggestion,
      description: '',
      responsible: '',
      due_date: null,
      origin_kind: 'finding',
      origin_ref: 'f1',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent(/Fyndet är oförändrat/);
  });

  it('creates manual work with no origin claimed for it', async () => {
    mountTasks({ active: [] });
    await screen.findByText('Inga uppgifter på gång.');

    fireEvent.click(screen.getByRole('button', { name: /Ny uppgift/ }));
    fireEvent.change(screen.getByLabelText('Rubrik'), {
      target: { value: 'Kalla till extrastämma' },
    });
    tasksApi.create.mockResolvedValue(task({ id: 't7', title: 'Kalla till extrastämma' }));
    fireEvent.click(screen.getByRole('button', { name: 'Skapa uppgift' }));

    await waitFor(() => expect(tasksApi.create).toHaveBeenCalledWith('brf-a', {
      title: 'Kalla till extrastämma',
      description: '',
      responsible: '',
      due_date: null,
      origin_kind: 'manual',
      origin_ref: '',
    }));
    // Manual work claims no source, so nothing was asked about one.
    expect(tasksApi.forOrigin).not.toHaveBeenCalled();
  });
});

describe('what the screen must not offer', () => {
  it('has no control anywhere that deletes a task', async () => {
    mountTasks({ active: [UNASSIGNED, FROM_WATCH], done: [DONE], cancelled: [CANCELLED] });
    await screen.findByText(UNASSIGNED.title);

    for (const button of screen.getAllByRole('button')) {
      expect(button.textContent).not.toMatch(/ta bort|radera|släng|rensa/i);
      expect(button.getAttribute('aria-label') || '')
        .not.toMatch(/ta bort|radera|släng|rensa/i);
    }
  });
});

describe('the wire', () => {
  const sourceOf = (relative) => readFileSync(
    fileURLToPath(new URL(relative, import.meta.url)),
    'utf8',
  );

  const FILES = ['./components/Tasks.jsx', './components/CreateTask.jsx'];

  // Spelled in halves so this file does not trip over its own check when it
  // reads itself.
  const FORBIDDEN = ['local' + 'Storage', 'session' + 'Storage', 'Authoriz' + 'ation', 'Bear' + 'er'];

  it('never reads, stores or sends a token — in the components or in this test', () => {
    for (const file of [...FILES, './api.js', './Tasks.test.jsx']) {
      const source = sourceOf(file).toLowerCase();
      for (const needle of FORBIDDEN) expect(source).not.toContain(needle.toLowerCase());
    }
    // The session is a cookie the browser attaches by itself on every call,
    // which is why there is nothing here to read.
    expect(sourceOf('./api.js')).toContain("credentials: 'include'");
  });

  it('has no delete route to call and no control that implies one', () => {
    const api = sourceOf('./api.js');
    const block = api.slice(api.indexOf('export const tasksApi'));
    expect(block.slice(0, block.indexOf('};'))).not.toContain('DELETE');

    for (const file of FILES) {
      const source = sourceOf(file);
      expect(source).not.toContain('DELETE');
      expect(source).not.toContain('Trash2');
    }
  });
});
