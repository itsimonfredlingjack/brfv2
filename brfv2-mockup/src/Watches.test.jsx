import React from 'react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Watches from './components/Watches';
import { watchesApi } from './api';

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {},
  watchesApi: {
    board: vi.fn(),
    scan: vi.fn(),
    decide: vi.fn(),
    remove: vi.fn(),
  },
  // A watch card offers to turn the obligation into work; the panel is only
  // opened by a click, so nothing here is called unless a test asks for it.
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
  quote: 'Uppsägning ska ske senast tre månader före den 31 december 2026',
  quotes: ['Uppsägning ska ske senast tre månader före den 31 december 2026'],
  chunk_id: 'c7',
  rects: [[72, 120, 430, 134]],
  score: 1.0,
  approximate: false,
  corpus_origin: 'synthetic',
};

const OPEN_TERM_CITATION = {
  ...CITATION,
  page: 4,
  quote: 'Uppsägningstiden är tre månader räknat från avtalstidens utgång',
  quotes: ['Uppsägningstiden är tre månader räknat från avtalstidens utgång'],
  chunk_id: 'c9',
};

/** A watch as the board endpoint serves it, computed fields and all. */
const watch = (overrides) => ({
  id: 'w0',
  tenant_id: 'brf-a',
  kind: 'notice_deadline',
  status: 'proposed',
  title: 'Säg upp eller ompröva avtalet senast 2026-09-30',
  due_date: '2026-09-30',
  derived_due_date: '2026-09-30',
  derivation: '2026-12-31 minus 3 månader',
  recurrence: 'none',
  responsible: '',
  remind_lead_days: 30,
  citations: [CITATION],
  source_document_id: 'doc-contract',
  source_document_name: 'Snöröjningsavtal 2026.pdf',
  created_at: '2026-08-01T09:00:00+00:00',
  decided_by: null,
  decided_at: null,
  decision_note: null,
  succeeded_by: null,
  kind_label: 'Uppsägning',
  status_label: 'väntar på godkännande',
  remind_at: '2026-08-31',
  bucket: 'later',
  days_left: 60,
  next_due_after: null,
  ...overrides,
});

const PROPOSAL = watch({ id: 'w1' });

/** Approved, and nobody has been named to do it. */
const UNASSIGNED = watch({
  id: 'w2',
  kind: 'expiry',
  kind_label: 'Avtalet upphör',
  status: 'approved',
  status_label: 'bevakas',
  title: 'Avtalet upphör 2026-08-20',
  due_date: '2026-08-20',
  derived_due_date: '2026-08-20',
  derivation: 'citerad avtalstid 2025-08-21 – 2026-08-20',
  responsible: '',
  remind_at: '2026-07-21',
  bucket: 'soon',
  days_left: 19,
  decided_by: 'user-1',
  decided_at: '2026-08-01T09:30:00+00:00',
});

/** Approved, and a human disagreed with the contract's own arithmetic. */
const MOVED = watch({
  id: 'w3',
  kind: 'warranty',
  kind_label: 'Garanti',
  status: 'approved',
  status_label: 'bevakas',
  title: 'Garantitiden går ut 2026-10-31',
  due_date: '2026-11-15',
  derived_due_date: '2026-10-31',
  derivation: '2021-10-31 plus 5 år',
  responsible: 'Ordförande Ek',
  remind_at: '2026-10-16',
  bucket: 'later',
  days_left: 106,
  decided_by: 'user-1',
  decided_at: '2026-08-01T09:31:00+00:00',
});

const RECURRING = watch({
  id: 'w4',
  kind: 'inspection',
  kind_label: 'Besiktning eller kontroll',
  status: 'approved',
  status_label: 'bevakas',
  title: 'Återkommande kontroll, nästa gång 2026-12-12',
  due_date: '2026-12-12',
  derived_due_date: '2026-12-12',
  derivation: '2023-12-12 plus ett intervall (triennial)',
  recurrence: 'triennial',
  responsible: 'Fastighetsskötare Nilsson',
  remind_at: '2026-11-12',
  bucket: 'recurring',
  days_left: 133,
  next_due_after: '2029-12-12',
  decided_by: 'user-1',
  decided_at: '2026-08-01T09:32:00+00:00',
});

const SETTLED = watch({
  id: 'w5',
  status: 'dismissed',
  status_label: 'avfärdad',
  title: 'Uppsägning måste ske senast 2026-06-30',
  due_date: '2026-06-30',
  derived_due_date: '2026-06-30',
  bucket: 'overdue',
  days_left: -32,
  decided_by: 'user-1',
  decided_at: '2026-07-02T08:00:00+00:00',
  decision_note: 'Avtalet är redan uppsagt skriftligen 2026-05-02.',
});

const UNRESOLVED = {
  id: 'u1',
  tenant_id: 'brf-a',
  what: 'Uppsägningstid: tre månader',
  why: 'Klausulen anger hur lång uppsägningstiden är, men inte vilket datum den '
    + 'räknas från. Fyll i avtalets slutdatum för att få en bevakning.',
  citations: [OPEN_TERM_CITATION],
  source_document_id: 'doc-contract',
  source_document_name: 'Snöröjningsavtal 2026.pdf',
  created_at: '2026-08-01T09:00:00+00:00',
};

const EMPTY_BUCKETS = { overdue: [], soon: [], later: [], recurring: [] };

function mountWith({
  proposed = [PROPOSAL],
  buckets = {},
  unresolved = [],
  settled = [],
  isAdmin = true,
} = {}) {
  watchesApi.board.mockResolvedValue({
    today: '2026-08-01',
    proposed,
    buckets: { ...EMPTY_BUCKETS, ...buckets },
    bucketLabels: {
      overdue: 'Försenat', soon: 'Snart', later: 'Senare', recurring: 'Återkommande',
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
    settled,
    unresolved,
  });
  const onOpenCitation = vi.fn();
  render(<Watches brfId="brf-a" isAdmin={isAdmin} onOpenCitation={onOpenCitation} />);
  return { onOpenCitation };
}

const cardFor = (title) => screen.getByText(title).closest('article');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('a proposal', () => {
  it('shows its citation, its arithmetic and all three decisions', async () => {
    const { onOpenCitation } = mountWith();
    await screen.findByText(PROPOSAL.title);
    const card = cardFor(PROPOSAL.title);

    // The arithmetic reads as a sentence on the card rather than as a row in a
    // definition list, so it is asserted where a reader actually meets it.
    expect(within(card).getByText(/ur 2026-12-31 minus 3 månader/)).toBeInTheDocument();
    expect(within(card).getByText('30 sep.')).toBeInTheDocument();
    expect(within(card).getByText(/Snöröjningsavtal 2026\.pdf · s\. 3/)).toBeInTheDocument();
    expect(within(card).getByText(CITATION.quote)).toBeInTheDocument();

    for (const label of ['Godkänn', 'Avfärda', 'Ta bort']) {
      expect(within(card).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }

    fireEvent.click(within(card).getByTitle('Öppna Snöröjningsavtal 2026.pdf sida 3'));
    expect(onOpenCitation).toHaveBeenCalledWith(CITATION);
  });

  it('is never rendered inside a bucket', async () => {
    mountWith({ buckets: { soon: [UNASSIGNED] } });
    await screen.findByText(PROPOSAL.title);

    const card = cardFor(PROPOSAL.title);
    // A proposal is not a watch, and the card has to say so before anything
    // else: the unproven state, which this language draws as a dashed outline
    // against the filled one an approved watch carries.
    expect(within(card).getByText('förslag — ingen bevakning ännu').className)
      .toContain('tillstand--oprovad');
    expect(card.closest('.watch-bucket')).toBeNull();
    expect(card.closest('.watches-proposals')).not.toBeNull();

    // And the board, read on its own, does not mention it at all.
    const board = screen.getByRole('region', { name: 'Bevakas' });
    expect(within(board).queryByText(PROPOSAL.title)).toBeNull();
    expect(within(board).getByText(UNASSIGNED.title)).toBeInTheDocument();
  });

  it('refuses to dismiss without a note, before the backend is asked', async () => {
    mountWith();
    await screen.findByText(PROPOSAL.title);
    const card = cardFor(PROPOSAL.title);

    const dismiss = within(card).getByRole('button', { name: 'Avfärda' });
    expect(dismiss).toBeDisabled();
    fireEvent.click(dismiss);
    expect(watchesApi.decide).not.toHaveBeenCalled();

    fireEvent.change(within(card).getByLabelText('Varför avfärdas den? (krävs)'), {
      target: { value: 'Avtalet sades upp skriftligen 2026-05-02.' },
    });
    expect(dismiss).toBeEnabled();

    watchesApi.decide.mockResolvedValue({
      watch: { ...PROPOSAL, status: 'dismissed', status_label: 'avfärdad' },
      successor: null,
    });
    fireEvent.click(dismiss);
    await waitFor(() => expect(watchesApi.decide).toHaveBeenCalledWith('brf-a', 'w1', {
      status: 'dismissed',
      note: 'Avtalet sades upp skriftligen 2026-05-02.',
    }));
  });

  it('sends the date, the responsible and the reminder a human actually chose', async () => {
    mountWith();
    await screen.findByText(PROPOSAL.title);
    const card = cardFor(PROPOSAL.title);

    fireEvent.change(within(card).getByLabelText('Datum'), { target: { value: '2026-10-15' } });
    fireEvent.change(within(card).getByLabelText('Ansvarig'), { target: { value: 'Ordförande Ek' } });
    fireEvent.change(within(card).getByLabelText('Påminn dagar före'), { target: { value: '14' } });

    watchesApi.decide.mockResolvedValue({
      watch: { ...PROPOSAL, status: 'approved', due_date: '2026-10-15', responsible: 'Ordförande Ek' },
      successor: null,
    });
    fireEvent.click(within(card).getByRole('button', { name: /Godkänn/ }));

    await waitFor(() => expect(watchesApi.decide).toHaveBeenCalledWith('brf-a', 'w1', {
      status: 'approved',
      due_date: '2026-10-15',
      responsible: 'Ordförande Ek',
      remind_lead_days: 14,
    }));
  });

  it('refuses a reminder outside the range the route accepts', async () => {
    mountWith();
    await screen.findByText(PROPOSAL.title);
    const card = cardFor(PROPOSAL.title);

    fireEvent.change(within(card).getByLabelText('Påminn dagar före'), { target: { value: '400' } });
    expect(within(card).getByText(/0–365 dagar före/)).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /Godkänn/ })).toBeDisabled();
    fireEvent.click(within(card).getByRole('button', { name: /Godkänn/ }));
    expect(watchesApi.decide).not.toHaveBeenCalled();
  });

  it('surfaces the backend’s own words when a decided watch cannot be deleted', async () => {
    mountWith();
    await screen.findByText(PROPOSAL.title);
    const card = cardFor(PROPOSAL.title);

    const refusal = new Error(
      'En bevakning som någon tagit ställning till raderas inte. '
      + 'Markera den som avklarad eller avfärdad i stället.',
    );
    refusal.status = 409;
    watchesApi.remove.mockRejectedValue(refusal);

    fireEvent.click(within(card).getByRole('button', { name: /Ta bort/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Markera den som avklarad eller avfärdad i stället/,
    );
  });
});

describe('the board', () => {
  it('renders the four buckets in order, with the server’s own labels', async () => {
    mountWith({ buckets: { soon: [UNASSIGNED], later: [MOVED], recurring: [RECURRING] } });
    await screen.findByText(UNASSIGNED.title);

    const labels = [...document.querySelectorAll('.watch-bucket')]
      .map((section) => section.getAttribute('aria-label'));
    expect(labels).toEqual(['Försenat', 'Snart', 'Senare', 'Återkommande']);
  });

  it('says an empty bucket is empty instead of rendering nothing', async () => {
    mountWith({ buckets: { soon: [UNASSIGNED] } });
    await screen.findByText(UNASSIGNED.title);
    const overdue = screen.getByRole('region', { name: 'Försenat' });
    expect(within(overdue).getByText('Inget är försenat.')).toBeInTheDocument();
  });

  it('reads an unnamed responsible as “ej utsedd”, never as blank', async () => {
    mountWith({ buckets: { soon: [UNASSIGNED] } });
    await screen.findByText(UNASSIGNED.title);
    const card = cardFor(UNASSIGNED.title);

    expect(within(card).getByText('ej utsedd')).toBeInTheDocument();
    expect(within(card).getByText('ansvarig')).toBeInTheDocument();
    // The rest of what a board has to know to act on it.
    expect(within(card).getByText('20 aug.')).toBeInTheDocument();
    expect(within(card).getByText(/om 19 dagar/)).toBeInTheDocument();
    expect(within(card).getByText(/21 juli, 30 d före/)).toBeInTheDocument();
    expect(within(card).getAllByText(/Snöröjningsavtal 2026\.pdf/).length).toBeGreaterThan(0);
    expect(within(card).getByText('Avtalet upphör')).toBeInTheDocument();
  });

  it('keeps both dates when a human moved the one the engine derived', async () => {
    mountWith({ buckets: { later: [MOVED] } });
    await screen.findByText(MOVED.title);
    const card = cardFor(MOVED.title);

    expect(within(card).getByText(/Motorn räknade fram/)).toBeInTheDocument();
    // The engine's arithmetic, and the date that is actually in force.
    expect(within(card).getByText('31 okt.')).toBeInTheDocument();
    expect(within(card).getAllByText('15 nov.').length).toBeGreaterThan(0);
    expect(within(card).getByText(/ur 2021-10-31 plus 5 år/)).toBeInTheDocument();
    expect(within(card).getByText(/En människa har flyttat datumet/)).toBeInTheDocument();
  });

  it('shows the successor when a recurring obligation is completed', async () => {
    mountWith({ buckets: { recurring: [RECURRING] } });
    await screen.findByText(RECURRING.title);
    const card = cardFor(RECURRING.title);

    watchesApi.decide.mockResolvedValue({
      watch: { ...RECURRING, status: 'done', status_label: 'avklarad', succeeded_by: 'w9' },
      successor: {
        ...RECURRING,
        id: 'w9',
        due_date: '2029-12-12',
        derived_due_date: '2029-12-12',
        title: 'Återkommande kontroll, nästa gång 2029-12-12',
      },
    });

    fireEvent.click(within(card).getByRole('button', { name: /Markera som avklarad/ }));
    await waitFor(() => expect(watchesApi.decide)
      .toHaveBeenCalledWith('brf-a', 'w4', { status: 'done' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      /Avklarad\. Nästa gång 12 dec\. 2029 — den turen är redan godkänd/,
    );
  });

  it('shows who settled a watch, when, and why', async () => {
    mountWith({ settled: [SETTLED] });
    await screen.findByText(PROPOSAL.title);
    expect(screen.getByText('Avgjorda bevakningar (1)')).toBeInTheDocument();
    expect(screen.getByText(SETTLED.title)).toBeInTheDocument();
    expect(screen.getByText(/avfärdad · user-1/)).toBeInTheDocument();
    expect(screen.getByText(/Avtalet är redan uppsagt skriftligen 2026-05-02\./))
      .toBeInTheDocument();
  });
});

describe('obligations that could not be dated', () => {
  it('renders what was read, why it has no date, and the passage', async () => {
    const { onOpenCitation } = mountWith({ proposed: [], unresolved: [UNRESOLVED] });
    await screen.findByText(UNRESOLVED.what);
    const card = cardFor(UNRESOLVED.what);

    expect(within(card).getByText(/inte vilket datum den räknas från/)).toBeInTheDocument();
    expect(within(card).getByText(OPEN_TERM_CITATION.quote)).toBeInTheDocument();

    fireEvent.click(within(card).getByTitle('Öppna Snöröjningsavtal 2026.pdf sida 4'));
    expect(onOpenCitation).toHaveBeenCalledWith(OPEN_TERM_CITATION);
  });

  it('reads as an answer rather than as a failure', async () => {
    mountWith({ proposed: [], unresolved: [UNRESOLVED] });
    await screen.findByText(UNRESOLVED.what);
    expect(screen.getByText(/Det är ett svar, inte/)).toBeInTheDocument();
  });
});

describe('reading the archive again', () => {
  it('reports how much was read and how many proposals came back', async () => {
    mountWith();
    await screen.findByText(PROPOSAL.title);
    watchesApi.scan.mockResolvedValue({
      documentsRead: 7,
      proposed: [PROPOSAL, { ...PROPOSAL, id: 'w6' }],
      unresolved: [UNRESOLVED],
    });

    fireEvent.click(screen.getByRole('button', { name: /Läs om arkivet/ }));
    await waitFor(() => expect(watchesApi.scan).toHaveBeenCalledWith('brf-a'));
    expect(await screen.findByRole('status')).toHaveTextContent(
      /Läste 7 dokument\. 2 förslag att ta ställning till/,
    );
  });

  it('offers no decision at all to a member who cannot make one', async () => {
    mountWith({ buckets: { soon: [UNASSIGNED] }, isAdmin: false });
    await screen.findByText(PROPOSAL.title);

    expect(screen.queryByRole('button', { name: /Läs om arkivet/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Markera som avklarad/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Godkänn/ })).toBeDisabled();
    expect(screen.getByText(/Bara administratörer kan besluta/)).toBeInTheDocument();
  });
});

describe('the wire', () => {
  const sourceOf = (relative) => readFileSync(
    fileURLToPath(new URL(relative, import.meta.url)),
    'utf8',
  );

  // Spelled in halves so this file does not trip over its own check when it
  // reads itself.
  const FORBIDDEN = ['local' + 'Storage', 'session' + 'Storage', 'Authoriz' + 'ation', 'Bear' + 'er'];

  it('never reads, stores or sends a token — in the component or in this test', () => {
    for (const file of ['./components/Watches.jsx', './api.js', './Watches.test.jsx']) {
      const source = sourceOf(file).toLowerCase();
      for (const needle of FORBIDDEN) expect(source).not.toContain(needle.toLowerCase());
    }
    // The session is a cookie the browser attaches by itself on every call,
    // which is why there is nothing here to read.
    expect(sourceOf('./api.js')).toContain("credentials: 'include'");
  });
});
