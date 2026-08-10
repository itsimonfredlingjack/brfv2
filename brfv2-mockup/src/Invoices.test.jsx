import React from 'react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Invoices from './components/Invoices';
import { integrationsApi, invoicesApi } from './api';
import { datum } from './components/datum';

/**
 * The invoice workspace.
 *
 * What is asserted here is the set of promises the screen makes, not its
 * markup:
 *
 * * the accounting system's status and this association's review status are two
 *   different things and never one badge;
 * * no control on the screen is an approval, and the local statuses say what
 *   they do not mean;
 * * a finding keeps verified fact, proposal and uncertainty apart, and a
 *   citation navigates to the page it names;
 * * a comparison against the previous invoice says what changed, by how much,
 *   and which part the invoice explains itself;
 * * comments, tasks and decisions are attributable and sit in one timeline that
 *   marks which entries are human;
 * * a weak supplier link reads as weak and asks a person.
 */

// PdfPane pulls in pdfjs-dist, which needs browser canvas APIs jsdom lacks.
vi.mock('./components/PdfPane', () => ({
  default: ({ url, page }) => <div data-testid="pdf-pane" data-url={url} data-page={page} />,
}));

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {
    connections: vi.fn(),
    availableInvoices: vi.fn(),
    decideFinding: vi.fn(),
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
    analysis: vi.fn(),
  },
  intakeApi: {},
  tasksApi: {
    list: vi.fn(),
    forOrigin: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    comment: vi.fn(),
  },
}));

const LABELS = {
  reviewStatus: {
    not_reviewed: 'Ej granskad',
    reviewed_no_objection: 'Granskad – ingen invändning',
    needs_investigation: 'Behöver utredas',
    awaiting_documentation: 'Väntar på underlag',
    question_sent: 'Fråga ställd',
    action_created: 'Åtgärd skapad',
    closed: 'Granskning avslutad',
  },
  reviewStatusCaveats: {
    not_reviewed: 'Ingen här har tagit ställning till fakturan ännu.',
    reviewed_no_objection:
      'En människa här har läst fakturan och inte haft någon invändning. Det är inte ett '
      + 'godkännande, en attest eller en bokföringsåtgärd — ingenting har ändrats i ekonomisystemet.',
    needs_investigation: 'Något behöver kontrolleras innan fakturan kan bedömas.',
    awaiting_documentation: 'Bedömningen väntar på underlag som föreningen inte har.',
    question_sent:
      'Någon här har ställt en fråga till leverantören utanför appen. Produkten skickar '
      + 'ingenting — det här är anteckningen om att frågan är ställd.',
    action_created: 'Arbetet ligger som en uppgift under Uppgifter.',
    closed: 'Granskningen är avslutad här. Ingenting har ändrats i ekonomisystemet.',
  },
  signals: { price_change: 'Prisförändring', missing_contract: 'Avtal saknas' },
  signalSeverity: { price_change: 'warning', missing_contract: 'attention' },
  verdicts: {
    matches: 'överensstämmer',
    possible_deviation: 'möjlig avvikelse',
    cannot_be_verified: 'kan inte verifieras',
  },
  findingTypes: {
    invoice_contract_amount: 'Belopp mot avtal',
    invoice_previous_comparison: 'Jämförelse med föregående faktura',
  },
  changes: {
    added: 'nytt fynd',
    removed: 'fyndet finns inte längre',
    changed: 'fyndet har ändrats',
  },
  engine: 'regelmotor',
  engineVersion: '2026.08.1',
};

const PRICE_SIGNAL = {
  kind: 'price_change',
  label: 'Prisförändring',
  detail: '4 625,00 SEK (+74,0 %)',
  finding_id: 'f-hist',
  severity: 'warning',
};

const CASE_ROW = {
  id: 'case-1',
  tenant_id: 'brf-a',
  case_key: 'snosvangen entreprenad#2026131',
  identity_basis:
    'Leverantör (Snösvängen Entreprenad AB) och fakturanummer (2026-131) är båda kända, '
    + 'så varje läsning av den här fakturan hamnar på samma ärende.',
  supplier_name: 'Snösvängen Entreprenad AB',
  supplier_key: 'snosvangen entreprenad',
  supplier_ref: '556812-3344',
  invoice_number: '2026-131',
  invoice_date: '2026-03-03',
  due_date: '2026-04-02',
  period_start: '2026-02-01',
  period_end: '2026-02-28',
  total_amount: '10875.00',
  currency: 'SEK',
  vat_amount: '2175.00',
  primary_invoice_id: 'inv-1',
  observations: [
    {
      kind: 'accounting_snapshot',
      ref_id: 'inv-1',
      label: 'fortnox 4711 — faktura 2026-131',
      adapter: 'fortnox',
      external_ref: '4711',
      occurred_at: '2026-03-03',
      retrieved_at: '2026-08-01T10:05:00+00:00',
      basis: 'Läst read-only ur fortnox:supplierinvoices.',
      content_sha256: 'a'.repeat(64),
      document_id: '',
    },
    {
      kind: 'email',
      ref_id: 'ev1',
      label: 'Faktura 2026-131 — från faktura@snosvangen.example',
      adapter: 'eml-file',
      external_ref: '<m1@snosvangen.example>',
      occurred_at: '2026-03-03T08:14:00+01:00',
      retrieved_at: '2026-03-04T09:00:00+00:00',
      basis: 'Meddelandet skriver fakturanumret 2026-131 ordagrant och namnger Snösvängen Entreprenad AB.',
      content_sha256: 'b'.repeat(64),
      document_id: '',
    },
    {
      kind: 'document',
      ref_id: 'att1',
      label: 'faktura-2026-131.pdf',
      adapter: 'eml-file',
      external_ref: '',
      occurred_at: '2026-03-03T08:14:00+01:00',
      retrieved_at: '2026-03-04T09:00:00+00:00',
      basis: 'Bilaga i det meddelande som knutits till ärendet.',
      content_sha256: 'c'.repeat(64),
      document_id: 'doc-invoice',
    },
  ],
  source_status: {
    adapter: 'fortnox',
    external_ref: '4711',
    booked: true,
    cancelled: false,
    balance: null,
    retrieved_at: '2026-08-01T10:05:00+00:00',
  },
  source_status_label: 'Bokförd i ekonomisystemet',
  review_status: 'not_reviewed',
  review_status_label: 'Ej granskad',
  review_status_caveat: 'Ingen här har tagit ställning till fakturan ännu.',
  review_status_note: '',
  review_status_by: '',
  review_status_at: '',
  responsible: '',
  signals: [PRICE_SIGNAL],
  top_signal: PRICE_SIGNAL,
  analysis_at: '2026-08-01T10:06:00+00:00',
  analysis_run_id: 'run-2',
  analysis_sequence: 2,
  analysis_engine_version: '2026.08.1',
  analysis_outdated: false,
  timeline: [
    {
      id: 't1',
      at: '2026-08-01T10:05:00+00:00',
      by: 'regelmotor',
      kind: 'case_opened',
      kind_label: 'ärendet öppnat',
      summary: 'Fakturaärende öppnat för Snösvängen Entreprenad AB 2026-131.',
      ref_id: '',
      note: '',
      from_value: '',
      to_value: '',
      dedupe_key: 'open:x',
      human: false,
    },
    {
      id: 't2',
      at: '2026-08-01T10:06:00+00:00',
      by: 'regelmotor',
      kind: 'analysis_run',
      kind_label: 'granskning körd',
      summary: 'Granskning körd: 2 fynd, Prisförändring.',
      ref_id: '',
      note: '',
      from_value: '',
      to_value: '',
      dedupe_key: 'analysis:x',
      human: false,
    },
    {
      id: 't3',
      at: '2026-08-01T11:00:00+00:00',
      by: 'anna',
      kind: 'commented',
      kind_label: 'kommentar',
      summary: 'Ringde leverantören om taxan.',
      ref_id: '',
      note: 'Ringde leverantören om taxan.',
      from_value: '',
      to_value: '',
      dedupe_key: '',
      human: true,
    },
  ],
  comments: [
    {
      id: 't3',
      at: '2026-08-01T11:00:00+00:00',
      by: 'anna',
      kind: 'commented',
      kind_label: 'kommentar',
      summary: 'Ringde leverantören om taxan.',
      note: 'Ringde leverantören om taxan.',
      ref_id: '',
      from_value: '',
      to_value: '',
      dedupe_key: '',
      human: true,
    },
  ],
  created_at: '2026-08-01T10:05:00+00:00',
  open: true,
  overdue: true,
  days_until_due: -122,
  last_activity_at: '2026-08-01T11:00:00+00:00',
  observation_kinds: ['accounting_snapshot', 'document', 'email'],
};

const SETTLED_ROW = {
  ...CASE_ROW,
  id: 'case-2',
  case_key: 'nordisk hissteknik#2026207',
  supplier_name: 'Nordisk Hissteknik AB',
  supplier_key: 'nordisk hissteknik',
  invoice_number: '2026-207',
  invoice_date: '2026-04-11',
  due_date: '2026-05-11',
  total_amount: '18750.00',
  primary_invoice_id: 'inv-2',
  source_status: null,
  source_status_label: '',
  review_status: 'reviewed_no_objection',
  review_status_label: 'Granskad – ingen invändning',
  review_status_caveat: LABELS.reviewStatusCaveats.reviewed_no_objection,
  responsible: 'Bo',
  signals: [],
  top_signal: null,
  open: false,
  overdue: false,
  observation_kinds: ['accounting_snapshot'],
  comments: [],
  timeline: [],
  last_activity_at: '2026-08-02T08:00:00+00:00',
};

const WORKSPACE = {
  today: '2026-08-02',
  cases: [CASE_ROW, SETTLED_ROW],
  counts: { total: 2, open: 1, overdue: 1, unassigned: 1, withSignal: 1, amountOpen: '10875.00' },
  labels: LABELS,
  sources: ['fixture', 'fortnox'],
  suppliers: ['Nordisk Hissteknik AB', 'Snösvängen Entreprenad AB'],
  responsibles: ['Bo'],
};

const CITATION = {
  document_id: 'doc-contract',
  document_name: 'Snöröjningsavtal 2026.pdf',
  page: 2,
  quote: 'maskinell snöröjning med traktor 1 250 kronor per timme',
  quotes: ['maskinell snöröjning med traktor 1 250 kronor per timme'],
  chunk_id: 'c1',
  rects: [[72, 100, 400, 114]],
  score: 0.88,
  approximate: false,
  corpus_origin: 'synthetic',
};

const CONTRACT_FINDING = {
  id: 'f-doc',
  tenant_id: 'brf-a',
  finding_type: 'invoice_contract_amount',
  created_at: '2026-08-01T10:06:00+00:00',
  invoice_id: 'inv-1',
  source_event_id: null,
  verdict: 'possible_deviation',
  verdict_label: 'möjlig avvikelse',
  verified_facts: [
    { label: 'Fakturabelopp', value: '10 875,00 SEK', source: 'invoice', citation_index: null },
    { label: 'Belopp i citerat villkor', value: '1 250,00 SEK', source: 'document', citation_index: 0 },
  ],
  suggestion: 'À-priset på fakturan är 1 450,00 SEK. Det jämförbara beloppet i avtalet är 1 250,00 SEK.',
  suggested_by: 'regelmotor',
  uncertainty: 'Det här är inte ett konstaterat avtalsbrott.',
  citations: [CITATION],
  anchor_strength: 'exact',
  anchor_note: 'Snöröjningsavtal 2026.pdf namnger Snösvängen Entreprenad AB ordagrant.',
  alias_proposal: null,
  status: 'open',
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

const HISTORY_FINDING = {
  ...CONTRACT_FINDING,
  id: 'f-hist',
  finding_type: 'invoice_previous_comparison',
  verified_facts: [
    { label: 'Föregående faktura', value: 'Faktura 2026-114 (2026-02-03)', source: 'invoice', citation_index: null },
    { label: 'Belopp föregående', value: '6 250,00 SEK', source: 'invoice', citation_index: null },
    { label: 'Belopp den här fakturan', value: '10 875,00 SEK', source: 'invoice', citation_index: null },
    { label: 'Förändring', value: '4 625,00 SEK (+74,0 %)', source: 'invoice', citation_index: null },
  ],
  suggestion:
    'Fakturan är 4 625,00 SEK högre än Faktura 2026-114 (2026-02-03) (6 250,00 SEK → 10 875,00 SEK, +74,0 %). '
    + 'Fakturan förklarar själv en del av det: antalet för Maskinell snöröjning med traktor har gått från 4 till 6, '
    + 'vilket förklarar 2 500,00 SEK av skillnaden. Det här förklarar den inte: à-priset för Maskinell snöröjning '
    + 'med traktor har gått från 1 250,00 SEK till 1 450,00 SEK (+16,0 %), vilket är 1 200,00 SEK av skillnaden.',
  uncertainty:
    'Det här är en jämförelse mellan två fakturor, inte mot ett avtal. En höjning kan vara helt avtalsenlig.',
  citations: [],
  anchor_strength: null,
  anchor_note: null,
};

const WEAK_FINDING = {
  ...CONTRACT_FINDING,
  id: 'f-weak',
  anchor_strength: 'partial',
  anchor_note:
    'Snöröjningsavtal 2026.pdf skriver "Snösvängen AB", fakturan säger "Snösvängen Entreprenad AB". '
    + 'Namnen är inte identiska; kopplingen bygger på att den särskiljande delen är densamma.',
  alias_proposal: {
    invoice_name: 'Snösvängen Entreprenad AB',
    document_name: 'Snösvängen AB',
    document_id: 'doc-contract',
    basis: 'Den särskiljande delen "Snösvängen AB" står ordagrant i Snöröjningsavtal 2026.pdf.',
  },
};

const ALIAS = {
  id: 'al1',
  tenant_id: 'brf-a',
  invoice_name: 'Snösvängen Entreprenad AB',
  document_name: 'Snösvängen AB',
  normalized_key: 'snosvangen entreprenad',
  created_by: 'user-1',
  created_at: '2026-08-01T10:20:00+00:00',
  note: null,
};

const SUPPLIER = {
  supplier_name: 'Snösvängen Entreprenad AB',
  supplier_key: 'snosvangen entreprenad',
  org_numbers: ['556812-3344'],
  invoice_count: 2,
  amount_low: '6250.00',
  amount_high: '10875.00',
  currency: 'SEK',
  previous: [
    {
      id: 'case-0',
      invoice_number: '2026-114',
      invoice_date: '2026-02-03',
      total_amount: '6250.00',
      currency: 'SEK',
      review_status: 'closed',
      review_status_label: 'Granskning avslutad',
      responsible: 'Anna',
    },
  ],
  documents: [{ id: 'doc-contract', name: 'Snöröjningsavtal 2026.pdf' }],
  deviation_count: 1,
  aliases: [],
  tasks: [],
  responsibles: ['Anna'],
};

// Two recorded analyses, newest first, exactly as the backend serialises them:
// the superseded findings themselves are *not* here — those come from
// invoicesApi.analysis when somebody asks for them.
const REPLACED_FINDING = {
  ...HISTORY_FINDING,
  id: 'f-hist-old',
  verdict: 'matches',
  verdict_label: 'överensstämmer',
  suggestion: 'Beloppet är oförändrat mot Faktura 2026-114 (2026-02-03) (6 250,00 SEK).',
  verified_facts: [
    { label: 'Förändring', value: 'oförändrat belopp', source: 'invoice', citation_index: null },
  ],
};

const ANALYSES = [
  {
    id: 'run-2',
    tenant_id: 'brf-a',
    case_id: 'case-1',
    invoice_id: 'inv-1',
    sequence: 2,
    ran_at: '2026-08-01T10:06:00+00:00',
    engine: 'regelmotor',
    engine_version: '2026.08.1',
    source: {
      invoice_id: 'inv-1',
      adapter: 'fortnox',
      external_ref: '4711',
      source_dataset: 'fortnox:supplierinvoices',
      content_sha256: 'a'.repeat(64),
      retrieved_at: '2026-08-01T10:05:00+00:00',
    },
    supersedes: 'run-1',
    supersedes_sequence: 1,
    source_changed: true,
    finding_count: 2,
    kept_count: 0,
    already_decided_count: 0,
    changes: [
      {
        kind: 'changed',
        kind_label: 'fyndet har ändrats',
        finding_type: 'invoice_previous_comparison',
        finding_type_label: 'Jämförelse med föregående faktura',
        summary: 'Jämförelse med föregående faktura: överensstämmer → möjlig avvikelse.',
        from_verdict: 'matches',
        to_verdict: 'possible_deviation',
        from_text: 'Beloppet är oförändrat mot Faktura 2026-114 (2026-02-03) (6 250,00 SEK).',
        to_text: 'Fakturan är 4 625,00 SEK högre än Faktura 2026-114 (2026-02-03).',
        fact_changes: [
          { label: 'Förändring', from_value: 'oförändrat belopp', to_value: '4 625,00 SEK (+74,0 %)' },
        ],
        finding_id: 'f-hist',
        replaced_finding_id: 'f-hist-old',
      },
    ],
    replaced_count: 1,
    summary: 'Ersatte den föregående granskningen: 1 ändrat fynd. Fakturan hade lästs om ur källan sedan dess.',
    note:
      'Fynden är förslag från en regelmotor, inte beslut. Det som ersatts ligger kvar här och '
      + 'går att läsa, men gäller inte längre som aktuell granskning. Ingenting en människa '
      + 'beslutat om har rörts av den här körningen.',
  },
  {
    id: 'run-1',
    tenant_id: 'brf-a',
    case_id: 'case-1',
    invoice_id: 'inv-1',
    sequence: 1,
    ran_at: '2026-07-28T09:00:00+00:00',
    engine: 'regelmotor',
    engine_version: '2026.08.1',
    source: {
      invoice_id: 'inv-1',
      adapter: 'fortnox',
      external_ref: '4711',
      source_dataset: 'fortnox:supplierinvoices',
      content_sha256: 'd'.repeat(64),
      retrieved_at: '2026-07-28T08:59:00+00:00',
    },
    supersedes: '',
    supersedes_sequence: 0,
    source_changed: false,
    finding_count: 2,
    kept_count: 0,
    already_decided_count: 0,
    changes: [],
    replaced_count: 0,
    summary: 'Första inspelade granskningen: 2 fynd.',
    note: 'Fynden är förslag från en regelmotor, inte beslut.',
  },
];

const DETAIL = {
  today: '2026-08-02',
  case: CASE_ROW,
  invoice: {
    id: 'inv-1',
    adapter: 'fortnox',
    external_ref: '4711',
    retrieved_at: '2026-08-01T10:05:00+00:00',
    source_dataset: 'fortnox:supplierinvoices',
    content_sha256: 'a'.repeat(64),
    lines: [
      {
        description: 'Maskinell snöröjning med traktor',
        quantity: '6',
        unit_price: '1450.00',
        amount: '8700.00',
        vat_amount: '2175.00',
      },
    ],
  },
  findings: [CONTRACT_FINDING, HISTORY_FINDING],
  documents: [
    {
      id: 'doc-invoice',
      name: 'faktura-2026-131.pdf',
      pages: 1,
      role: 'Originalfil ur meddelandet',
      basis: 'Bilaga i det meddelande som knutits till ärendet.',
    },
  ],
  sourceEvent: {
    id: 'ev1',
    origin: 'faktura@snosvangen.example',
    origin_display: 'Snösvängen Entreprenad AB',
    subject: 'Faktura 2026-131 — snöröjning februari',
    body_text: 'Bifogat finner ni faktura 2026-131.',
    occurred_at: '2026-03-03T08:14:00+01:00',
    received_at: '2026-03-04T09:00:00+00:00',
  },
  supplier: SUPPLIER,
  tasks: [],
  analyses: ANALYSES,
  labels: LABELS,
};

const NO_CONNECTIONS = {
  'microsoft-graph': { provider: 'microsoft-graph', configured: false, connection: null },
  fortnox: { provider: 'fortnox', configured: false, connection: null },
};

function mount({
  workspace = WORKSPACE,
  detail = DETAIL,
  connections = NO_CONNECTIONS,
  isAdmin = true,
} = {}) {
  invoicesApi.workspace.mockResolvedValue(workspace);
  invoicesApi.case.mockResolvedValue(detail);
  integrationsApi.connections.mockResolvedValue(connections);
  integrationsApi.availableInvoices.mockResolvedValue({
    adapter: 'fixture-accounting',
    source: 'fixture',
    invoices: [
      {
        external_ref: 'SI-2026-131',
        supplier_name: 'Snösvängen Entreprenad AB',
        invoice_number: '2026-131',
        invoice_date: '2026-03-03',
        due_date: '2026-04-02',
        total_amount: '10875.00',
        currency: 'SEK',
        adapter: 'fixture-accounting',
        dataset: 'gjutformen12-2026.json',
      },
    ],
  });
  const onOpenCitation = vi.fn();
  const onOpenDocument = vi.fn();
  render(
    <Invoices
      brfId="brf-a"
      isAdmin={isAdmin}
      onOpenCitation={onOpenCitation}
      onOpenDocument={onOpenDocument}
    />,
  );
  return { onOpenCitation, onOpenDocument };
}

async function openCase() {
  fireEvent.click(await screen.findByRole('button', { name: /Snösvängen Entreprenad AB/ }));
  return screen.findByText(/Källor och härkomst/);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the queue', () => {
  it('separates the accounting system’s status from our own review', async () => {
    mount();
    const row = (await screen.findByText('2026-131')).closest('tr');
    expect(within(row).getByText('Bokförd i ekonomisystemet')).toBeInTheDocument();
    expect(within(row).getByText('Ej granskad')).toBeInTheDocument();
    // Two columns with two headings, never one badge.
    expect(screen.getByRole('columnheader', { name: 'I ekonomisystemet' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Vår granskning' })).toBeInTheDocument();
  });

  it('offers no control that could be mistaken for approving an invoice', async () => {
    mount();
    await screen.findByText('2026-131');
    const buttons = screen.getAllByRole('button').map((b) => b.textContent.toLowerCase());
    expect(buttons.some((label) => label.includes('godkänn faktura'))).toBe(false);
    expect(buttons.some((label) => label.includes('attestera'))).toBe(false);
    expect(buttons.some((label) => label.includes('betala'))).toBe(false);
  });

  it('says where each case has been seen', async () => {
    mount();
    const row = (await screen.findByText('2026-131')).closest('tr');
    expect(within(row).getByText('Ekonomisystem')).toBeInTheDocument();
    expect(within(row).getByText('E-post')).toBeInTheDocument();
  });

  it('shows the most important signal and marks an overdue case', async () => {
    mount();
    const row = (await screen.findByText('2026-131')).closest('tr');
    expect(within(row).getByText(/Prisförändring/)).toBeInTheDocument();
    expect(within(row).getByText('förfallen')).toBeInTheDocument();
  });

  it('filters to what still needs a decision, and can show everything', async () => {
    mount();
    await screen.findByText('2026-131');
    // The default is what is open, so a settled case is out of the way.
    expect(screen.queryByText('2026-207')).toBeNull();
    fireEvent.change(screen.getByLabelText('Filtrera på granskningsläge'), {
      target: { value: 'all' },
    });
    expect(await screen.findByText('2026-207')).toBeInTheDocument();
  });

  it('searches by supplier, number and responsible', async () => {
    mount();
    await screen.findByText('2026-131');
    fireEvent.change(screen.getByLabelText('Filtrera på granskningsläge'), { target: { value: 'all' } });
    fireEvent.change(screen.getByLabelText('Sök i fakturakön'), { target: { value: 'nordisk' } });
    expect(await screen.findByText('2026-207')).toBeInTheDocument();
    expect(screen.queryByText('2026-131')).toBeNull();
  });

  it('reads an invoice in and analyses it in one operator action', async () => {
    mount();
    await screen.findByText('2026-131');
    fireEvent.click(screen.getByText(/Läs in fakturor/));
    invoicesApi.importInvoice.mockResolvedValue(CASE_ROW);

    fireEvent.click(await screen.findByRole('button', { name: /Läs in och granska/ }));
    // The source is named in the request, never inferred from what happens to
    // be connected: a demo read and a live read must not look alike.
    await waitFor(() => expect(invoicesApi.importInvoice)
      .toHaveBeenCalledWith('brf-a', 'SI-2026-131', 'fixture'));
  });

  it('says plainly that nothing is written back', async () => {
    mount();
    await screen.findByText('2026-131');
    fireEvent.click(screen.getByText(/Läs in fakturor/));
    expect(
      await screen.findByText(/kan inte bokföra, kontera, attestera, betala/),
    ).toBeInTheDocument();
  });

  it('does not offer the read-in panel to a member', async () => {
    mount({ isAdmin: false });
    await screen.findByText('2026-131');
    expect(screen.queryByText(/Läs in fakturor/)).toBeNull();
  });
});

describe('the case', () => {
  it('brings the original, the fields and the provenance together', async () => {
    mount();
    await openCase();
    // The original file is opened through the app's own document viewer.
    expect(screen.getByTestId('pdf-pane').dataset.url)
      .toBe('/api/brf/brf-a/documents/doc-invoice/pdf');
    expect(screen.getByText(/Originalfil ur meddelandet/)).toBeInTheDocument();
    // The extracted fields sit beside the original, never instead of it.
    expect(screen.getByText('Maskinell snöröjning med traktor')).toBeInTheDocument();
    expect(screen.getAllByText(/fortnox:supplierinvoices/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Faktura 2026-131 — snöröjning februari/)).toBeInTheDocument();
  });

  it('says why its sources are the same invoice', async () => {
    mount();
    await openCase();
    expect(screen.getByText(/hamnar på samma ärende/)).toBeInTheDocument();
    // And every observation carries the basis it was attached on.
    expect(screen.getByText(/skriver fakturanumret 2026-131 ordagrant/)).toBeInTheDocument();
  });

  it('keeps the two statuses apart and spells out what ours does not mean', async () => {
    mount();
    await openCase();
    const source = screen.getByText('I ekonomisystemet').closest('.case-status-card');
    const local = screen.getByText('Vår granskning').closest('.case-status-card');
    expect(within(source).getByText('Bokförd i ekonomisystemet')).toBeInTheDocument();
    expect(within(source).getByText(/ändrar den aldrig/)).toBeInTheDocument();
    expect(within(local).getByText('Ej granskad')).toBeInTheDocument();
  });

  it('separates verified fact, proposal and uncertainty', async () => {
    mount();
    await openCase();
    expect(screen.getAllByText('Verifierat ur fakturorna').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Verifierat ur dokumenten').length).toBeGreaterThan(0);
    expect(screen.getByText(/Det jämförbara beloppet i avtalet är 1 250,00 SEK/)).toBeInTheDocument();
    expect(screen.getByText(/inte ett konstaterat avtalsbrott/)).toBeInTheDocument();
    expect(screen.getAllByText('(regelmotor)').length).toBe(2);
  });

  it('opens a cited page through the app’s own citation navigation', async () => {
    const { onOpenCitation } = mount();
    await openCase();
    fireEvent.click(screen.getAllByTitle('Öppna Snöröjningsavtal 2026.pdf sida 2')[0]);
    expect(onOpenCitation).toHaveBeenCalledWith(CITATION);
  });

  it('says in plain language what changed and which part is unexplained', async () => {
    mount();
    await openCase();
    const history = screen.getByText(/Jämfört med föreningens tidigare fakturor/).closest('.case-panel');
    expect(within(history).getByText(/4 625,00 SEK högre/)).toBeInTheDocument();
    expect(within(history).getAllByText(/\+74,0 %/).length).toBeGreaterThan(0);
    expect(within(history).getByText(/förklarar 2 500,00 SEK av skillnaden/)).toBeInTheDocument();
    expect(within(history).getByText(/Det här förklarar den inte/)).toBeInTheDocument();
  });

  it('does not pretend a history finding should have had a citation', async () => {
    mount();
    await openCase();
    const history = screen.getByText(/Jämfört med föreningens tidigare fakturor/).closest('.case-panel');
    expect(within(history).getByText(/Därför saknar de citat, och det är avsiktligt/))
      .toBeInTheDocument();
    expect(within(history).getByText(/jämförelsen är gjord mot föreningens egna tidigare fakturor/))
      .toBeInTheDocument();
  });

  it('keeps machine findings and human decisions apart in one timeline', async () => {
    mount();
    await openCase();
    const timeline = screen.getByText('Allt som hänt').closest('.case-timeline');
    const entries = within(timeline).getAllByRole('listitem');
    expect(entries).toHaveLength(3);
    expect(entries[0].className).toContain('engine');
    expect(entries[2].className).toContain('human');
    expect(within(entries[1]).getByText('maskinellt')).toBeInTheDocument();
  });

  it('records a local review status with a required explanation', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Granskningsläge').closest('.case-review-status');
    fireEvent.change(within(panel).getByRole('combobox'), {
      target: { value: 'needs_investigation' },
    });
    const save = within(panel).getByRole('button', { name: 'Spara granskningsläget' });
    expect(save).toBeDisabled();

    fireEvent.change(within(panel).getByRole('textbox'), {
      target: { value: 'Fråga om timtaxan' },
    });
    expect(save).toBeEnabled();

    invoicesApi.update.mockResolvedValue({ ...CASE_ROW, review_status: 'needs_investigation' });
    fireEvent.click(save);
    await waitFor(() => expect(invoicesApi.update).toHaveBeenCalledWith('brf-a', 'case-1', {
      review_status: 'needs_investigation',
      note: 'Fråga om timtaxan',
    }));
  });

  it('shows what a status does not mean before it is chosen', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Granskningsläge').closest('.case-review-status');
    fireEvent.change(within(panel).getByRole('combobox'), {
      target: { value: 'reviewed_no_objection' },
    });
    expect(within(panel).getByText(/inte ett godkännande, en attest eller en bokföringsåtgärd/))
      .toBeInTheDocument();
  });

  it('keeps comments attributable', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Kommentarer och frågor').closest('.case-panel');
    expect(within(panel).getByText('Ringde leverantören om taxan.')).toBeInTheDocument();
    expect(within(panel).getByText(/anna ·/)).toBeInTheDocument();

    invoicesApi.comment.mockResolvedValue(CASE_ROW);
    fireEvent.change(within(panel).getByLabelText('Ny kommentar'), {
      target: { value: 'Avtalet efterfrågat.' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Kommentera' }));
    await waitFor(() => expect(invoicesApi.comment)
      .toHaveBeenCalledWith('brf-a', 'case-1', 'Avtalet efterfrågat.'));
  });

  it('names who is looking at the invoice', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Ansvarig').closest('.case-panel');
    invoicesApi.update.mockResolvedValue({ ...CASE_ROW, responsible: 'Anna' });
    fireEvent.change(within(panel).getByLabelText('Ansvarig'), { target: { value: 'Anna' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Spara' }));
    await waitFor(() => expect(invoicesApi.update)
      .toHaveBeenCalledWith('brf-a', 'case-1', { responsible: 'Anna' }));
  });

  it('re-reads the source and says it changed nothing over there', async () => {
    mount();
    await openCase();
    invoicesApi.refresh.mockResolvedValue({
      case: CASE_ROW,
      source: 'Fakturan lästes om ur fortnox.',
    });
    fireEvent.click(screen.getByRole('button', { name: /Läs om och granska/ }));
    await waitFor(() => expect(invoicesApi.refresh).toHaveBeenCalledWith('brf-a', 'case-1'));
    expect(await screen.findByText(/Ingenting ändrades i ekonomisystemet/)).toBeInTheDocument();
  });

  it('offers a member nothing to change', async () => {
    mount({ isAdmin: false });
    await openCase();
    expect(screen.queryByRole('button', { name: 'Spara granskningsläget' })).toBeNull();
    expect(screen.queryByLabelText('Ny kommentar')).toBeNull();
    expect(screen.queryByRole('button', { name: /Läs om och granska/ })).toBeNull();
  });

  it('carries the supplier’s own history without a second supplier record', async () => {
    mount();
    await openCase();
    const panel = screen.getByText(/Om Snösvängen Entreprenad AB/).closest('.case-panel');
    expect(within(panel).getByText('556812-3344')).toBeInTheDocument();
    expect(within(panel).getByText(/6 250,00 SEK – 10 875,00 SEK/)).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: /2026-114 · 2026-02-03/ })).toBeInTheDocument();
  });
});

describe('a weak supplier link', () => {
  const weakDetail = { ...DETAIL, findings: [WEAK_FINDING] };

  it('reads as weak and asks a person', async () => {
    mount({ detail: weakDetail });
    await openCase();
    const weak = screen.getByText('Svag koppling till leverantören').closest('.finding-anchor');
    expect(weak.className).toContain('weak');
    expect(within(weak).getByText(/kan alltså gälla fel leverantör/)).toBeInTheDocument();
    expect(screen.getByText(/Den särskiljande delen "Snösvängen AB" står ordagrant/))
      .toBeInTheDocument();
  });

  it('posts exactly what was proposed, and offers the re-run that would use it', async () => {
    mount({ detail: weakDetail });
    await openCase();
    fireEvent.change(screen.getByLabelText('Anteckning om leverantörsnamnen'), {
      target: { value: 'Samma org.nr i avtalets sidhuvud.' },
    });
    integrationsApi.addSupplierAlias.mockResolvedValue(ALIAS);
    fireEvent.click(screen.getByRole('button', { name: 'Ja, samma leverantör' }));

    await waitFor(() => expect(integrationsApi.addSupplierAlias).toHaveBeenCalledWith('brf-a', {
      invoice_name: 'Snösvängen Entreprenad AB',
      document_name: 'Snösvängen AB',
      note: 'Samma org.nr i avtalets sidhuvud.',
    }));
    expect(await screen.findByRole('button', { name: /Kör om granskningen/ })).toBeInTheDocument();
  });
});

describe('deciding on a finding', () => {
  it('refuses a correction that does not say what is correct', async () => {
    mount();
    await openCase();
    const finding = screen.getAllByText('möjlig avvikelse')[0].closest('article');
    const correct = within(finding).getByRole('button', { name: 'Korrigera' });
    expect(correct).toBeDisabled();

    fireEvent.change(within(finding).getByLabelText('Beskriv korrigeringen'), {
      target: { value: 'Timtaxan höjdes i tilläggsavtal.' },
    });
    expect(correct).toBeEnabled();

    integrationsApi.decideFinding.mockResolvedValue({ ...CONTRACT_FINDING, status: 'corrected' });
    fireEvent.click(correct);
    await waitFor(() => expect(integrationsApi.decideFinding).toHaveBeenCalledWith('brf-a', 'f-doc', {
      status: 'corrected',
      note: 'Timtaxan höjdes i tilläggsavtal.',
    }));
  });

  it('is about the finding, not about the invoice', async () => {
    mount();
    await openCase();
    const finding = screen.getAllByText('möjlig avvikelse')[0].closest('article');
    expect(within(finding).getByRole('button', { name: 'Godkänn fyndet' })).toBeInTheDocument();
    expect(within(finding).getByText(/ställningstagande till/)).toBeInTheDocument();
  });
});

describe('the analysis audit trail', () => {
  /**
   * A re-analysis replaces the engine's open findings. The screen has to be
   * able to answer five questions about that afterwards: that it happened,
   * which reading it was built on, what changed, when, and under which rules.
   * The replaced version stops being a card; it does not stop being readable.
   */

  it('says that a new analysis replaced the old one, and when', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Analyshistorik').closest('.case-panel');
    const [latest] = within(panel).getAllByRole('listitem');

    expect(within(latest).getByText('Version 2')).toBeInTheDocument();
    expect(within(latest).getByText('gäller nu')).toBeInTheDocument();
    expect(within(latest).getByText(/Ersatte den föregående granskningen/)).toBeInTheDocument();
    expect(within(latest).getAllByText(new RegExp(datum('2026-08-01'))).length).toBeGreaterThan(0);
    // And the first run is still there, as its own version.
    expect(within(panel).getByText('Version 1')).toBeInTheDocument();
  });

  it('names the source version and the rule version behind each run', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Analyshistorik').closest('.case-panel');
    const [latest] = within(panel).getAllByRole('listitem');

    expect(within(latest).getByText('regelmotor 2026.08.1')).toBeInTheDocument();
    expect(within(latest).getByText('aaaaaaaaaaaa…')).toBeInTheDocument();
    expect(within(latest).getByText(/fortnox 4711/)).toBeInTheDocument();
    expect(within(latest).getByText(/lästs om sedan förra granskningen/)).toBeInTheDocument();
  });

  it('says what changed, with the previous value beside the current one', async () => {
    mount();
    await openCase();
    const panel = screen.getByText('Analyshistorik').closest('.case-panel');

    expect(within(panel).getByText('fyndet har ändrats')).toBeInTheDocument();
    expect(
      within(panel).getByText(/Jämförelse med föregående faktura: överensstämmer → möjlig avvikelse/),
    ).toBeInTheDocument();
    // The number itself, then and now — not a paraphrase of it.
    expect(within(panel).getByText('oförändrat belopp')).toBeInTheDocument();
    expect(within(panel).getByText('4 625,00 SEK (+74,0 %)')).toBeInTheDocument();
  });

  it('keeps the replaced findings out of the way until somebody asks', async () => {
    mount();
    await openCase();
    // The change list already says what the old finding *said* — what is not
    // here is the finding itself, as a card, and nothing was fetched for it.
    expect(document.querySelectorAll('.finding.replaced')).toHaveLength(0);
    expect(invoicesApi.analysis).not.toHaveBeenCalled();

    invoicesApi.analysis.mockResolvedValue({
      case_id: 'case-1',
      run: { ...ANALYSES[0], replaced: [REPLACED_FINDING] },
      labels: LABELS,
    });
    fireEvent.click(screen.getByRole('button', { name: /Visa den ersatta versionen \(1 fynd\)/ }));

    await waitFor(() => expect(invoicesApi.analysis)
      .toHaveBeenCalledWith('brf-a', 'case-1', 'run-2'));
    expect(await screen.findByText('ersatt')).toBeInTheDocument();
    expect(document.querySelectorAll('.finding.replaced')).toHaveLength(1);
  });

  it('marks a replaced finding as no longer applying and offers no decision on it', async () => {
    mount();
    await openCase();
    invoicesApi.analysis.mockResolvedValue({
      case_id: 'case-1',
      run: { ...ANALYSES[0], replaced: [REPLACED_FINDING] },
      labels: LABELS,
    });
    fireEvent.click(screen.getByRole('button', { name: /Visa den ersatta versionen/ }));

    const old = (await screen.findByText('ersatt')).closest('.finding');
    expect(within(old).getByText('överensstämmer')).toBeInTheDocument();
    expect(within(old).getByText('oförändrat belopp')).toBeInTheDocument();
    // No control on a superseded card: it is a record, not something in play.
    expect(within(old).queryByRole('button')).toBeNull();
  });

  it('does not call a re-run that changed nothing a version', async () => {
    mount({
      detail: { ...DETAIL, analyses: [ANALYSES[1]] },
    });
    await openCase();
    const panel = screen.getByText('Analyshistorik').closest('.case-panel');
    expect(within(panel).getAllByRole('listitem')).toHaveLength(1);
    expect(
      within(panel).getByText(/En omkörning som kom fram till exakt samma sak är ingen ny version/),
    ).toBeInTheDocument();
  });

  it('flags findings that nobody has re-run since the rules changed', async () => {
    mount({
      detail: {
        ...DETAIL,
        case: { ...CASE_ROW, analysis_outdated: true, analysis_engine_version: '2026.05.1' },
      },
    });
    await openCase();
    const banner = await screen.findByRole('status');
    expect(banner).toHaveTextContent('regelversion 2026.05.1');
    expect(banner).toHaveTextContent('Nu gäller 2026.08.1');
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

  it('never reads, stores or sends a token', () => {
    for (const file of ['./components/Invoices.jsx', './components/InvoiceCase.jsx']) {
      const source = sourceOf(file).toLowerCase();
      for (const needle of FORBIDDEN) expect(source).not.toContain(needle.toLowerCase());
    }
  });

  it('has no route that could write to an accounting system', () => {
    const source = sourceOf('./api.js');
    const block = source.slice(source.indexOf('export const invoicesApi'), source.indexOf('export const intakeApi'));
    for (const verb of ["'PUT'", "'PATCH'", "'DELETE'"]) {
      expect(block).not.toContain(verb);
    }
    expect(block).not.toMatch(/approve|attest|book|pay/i);
  });
});

describe('the keyboard flow', () => {
  it('"/" focuses the queue search', async () => {
    mount();
    await screen.findByText('2026-131');
    fireEvent.keyDown(window, { key: '/' });
    expect(document.activeElement).toBe(screen.getByLabelText('Sök i fakturakön'));
  });

  it('arrows move between rows and Enter opens the marked case', async () => {
    mount();
    await screen.findByText('2026-131');
    fireEvent.change(screen.getByLabelText('Filtrera på granskningsläge'), { target: { value: 'all' } });
    const rows = document.querySelectorAll('.invoices-queue tbody tr');
    expect(rows.length).toBe(2);

    rows[0].focus();
    fireEvent.keyDown(rows[0], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(rows[1]);

    fireEvent.keyDown(rows[1], { key: 'Enter' });
    expect(await screen.findByText(/Källor och härkomst/)).toBeInTheDocument();
  });

  it('Escape empties the search field', async () => {
    mount();
    await screen.findByText('2026-131');
    const input = screen.getByLabelText('Sök i fakturakön');
    fireEvent.change(input, { target: { value: 'zzz' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(input).toHaveValue('');
  });
});
