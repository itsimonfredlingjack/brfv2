import React from 'react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Integrations from './components/Integrations';
import { integrationsApi } from './api';

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {
    format: vi.fn(),
    connections: vi.fn(),
    configureGraph: vi.fn(),
    configureFortnox: vi.fn(),
    beginLogin: vi.fn(),
    pollLogin: vi.fn(),
    completeLogin: vi.fn(),
    disconnect: vi.fn(),
    listMailboxMessages: vi.fn(),
    importMailboxMessage: vi.fn(),
    listSourceEvents: vi.fn(),
    importSourceEvent: vi.fn(),
    decideSourceEvent: vi.fn(),
    deleteSourceEvent: vi.fn(),
    archiveAttachment: vi.fn(),
    withdrawAttachment: vi.fn(),
    availableInvoices: vi.fn(),
    listInvoices: vi.fn(),
    importInvoice: vi.fn(),
    mappingPreview: vi.fn(),
    reviewInvoice: vi.fn(),
    listFindings: vi.fn(),
    decideFinding: vi.fn(),
    listSupplierAliases: vi.fn(),
    addSupplierAlias: vi.fn(),
    deleteSupplierAlias: vi.fn(),
  },
  tasksApi: {
    list: vi.fn(),
    forOrigin: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    comment: vi.fn(),
  },
}));

const FORMAT = {
  mail: {
    extension: '.eml',
    maxMessageBytes: 26214400,
    maxAttachments: 10,
    maxAttachmentBytes: 20971520,
    bodyTypes: ['text/plain', 'text/html'],
    attachmentTypes: ['application/pdf'],
    requiredHeaders: ['From', 'Subject'],
    rejections: [],
  },
  accountingAdapter: 'fixture-accounting',
  invoiceSources: ['fixture', 'fortnox'],
  mailFolders: ['inbox', 'archive', 'junkemail'],
};

/** Nothing connected: the delivery the manual .eml import has to keep working in. */
const NO_CONNECTIONS = {
  'microsoft-graph': {
    provider: 'microsoft-graph',
    configured: false,
    connection: null,
    pendingLogin: null,
    loginKind: 'device',
    scopes: ['offline_access', 'User.Read', 'Mail.Read'],
    hosts: ['graph.microsoft.com', 'login.microsoftonline.com'],
  },
  fortnox: {
    provider: 'fortnox',
    configured: false,
    connection: null,
    pendingLogin: null,
    loginKind: 'code',
    scopes: ['supplierinvoice', 'companyinformation'],
    hosts: ['api.fortnox.se', 'apps.fortnox.se'],
  },
};

const connected = (provider, extra = {}) => ({
  ...NO_CONNECTIONS[provider],
  configured: true,
  connection: {
    provider,
    tenant_id: 'brf-a',
    status: 'connected',
    account_label: provider === 'fortnox' ? 'Brf Gjutformen 12 (769600-1234)' : 'styrelsen@gjutformen12.example',
    granted_scopes: NO_CONNECTIONS[provider].scopes,
    client_id: 'c1',
    authority: 'organizations',
    mailbox: '',
    folder: 'inbox',
    redirect_uri: '',
    read_supplier_register: false,
    configured_by: 'user-1',
    configured_at: '2026-07-01T09:00:00+00:00',
    connected_by: 'user-1',
    connected_at: '2026-07-01T09:05:00+00:00',
    access_expires_at: '2026-08-01T11:00:00+00:00',
    last_used_at: '2026-08-01T10:00:00+00:00',
    last_error: null,
    ...extra,
  },
});

const EVENT = {
  id: 'ev1',
  tenant_id: 'brf-a',
  source_type: 'email',
  received_at: '2026-08-01T10:00:00+00:00',
  occurred_at: '2026-02-03T08:14:00+01:00',
  external_ref: '<snosvangen114@fixture.invalid>',
  content_sha256: 'f9bac952a56cfe18b2d7248ca6953cf1e7d8e38e2f46b0261bd6a04be6cf302f',
  provenance: {
    method: 'manual-file-import',
    adapter: 'eml-file',
    origin_filename: 'faktura.eml',
    origin_bytes: 4546,
    imported_by: 'user-1',
    imported_at: '2026-08-01T10:00:00+00:00',
  },
  origin: 'faktura@snosvangen.example',
  origin_display: 'Snösvängen Entreprenad AB',
  recipients: ['styrelsen@gjutformen12.example'],
  subject: 'Faktura 2026-114 — snöröjning januari 2026',
  body_text: 'Bifogat finner ni faktura 2026-114.',
  attachments: [
    {
      id: 'att1',
      filename: 'faktura-2026-114.pdf',
      media_type: 'application/pdf',
      bytes: 2549,
      sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
      document_id: 'doc-invoice',
      ingested: true,
      reused_existing_document: false,
      archived: false,
      archived_by: null,
      archived_at: null,
      archive_note: null,
    },
  ],
  import_status: 'imported',
  review_status: 'open',
  error: null,
  linked_document_ids: [],
  suggested_document_ids: ['doc-contract'],
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

/** The same envelope, taken out of a connected mailbox instead of off a disk. */
const MAILBOX_EVENT = {
  ...EVENT,
  id: 'ev2',
  content_sha256: 'b'.repeat(64),
  subject: 'Faktura 2026-115 — snöröjning februari 2026',
  provenance: {
    ...EVENT.provenance,
    method: 'graph-mailbox-import',
    adapter: 'microsoft-graph',
    origin_filename: 'AAMkAGI2.eml',
  },
  attachments: [{ ...EVENT.attachments[0], id: 'att2' }],
};

const INVOICE = {
  id: 'inv1',
  tenant_id: 'brf-a',
  adapter: 'fixture-accounting',
  external_ref: 'SI-2026-114',
  supplier_name: 'Snösvängen Entreprenad AB',
  supplier_ref: '556812-3344',
  invoice_number: '2026-114',
  invoice_date: '2026-02-03',
  due_date: '2026-03-05',
  period_start: '2026-01-01',
  period_end: '2026-01-31',
  total_amount: '6250.00',
  currency: 'SEK',
  vat_amount: '1250.00',
  lines: [
    {
      description: 'Maskinell snöröjning med traktor',
      quantity: '4',
      unit_price: '1250.00',
      amount: '5000.00',
      vat_amount: '1250.00',
    },
  ],
  retrieved_at: '2026-08-01T10:05:00+00:00',
  source_dataset: 'gjutformen12-2026.json',
  content_sha256: '0'.repeat(64),
  source_event_id: null,
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

const MATCH_FINDING = {
  id: 'f1',
  tenant_id: 'brf-a',
  finding_type: 'invoice_contract_amount',
  created_at: '2026-08-01T10:06:00+00:00',
  invoice_id: 'inv1',
  source_event_id: null,
  verdict: 'matches',
  verdict_label: 'överensstämmer',
  verified_facts: [
    { label: 'Leverantör enligt fakturan', value: 'Snösvängen Entreprenad AB', source: 'invoice', citation_index: null },
    { label: 'Belopp i citerat villkor', value: '1 250,00 SEK', source: 'document', citation_index: 0 },
  ],
  suggestion: 'À-pris för maskinell snöröjning motsvarar det citerade villkoret.',
  suggested_by: 'regelmotor',
  uncertainty: 'Jämförelsen gäller det citerade villkoret och ingenting annat.',
  citations: [CITATION],
  anchor_strength: 'exact',
  anchor_note: 'Snöröjningsavtal 2026.pdf namnger Snösvängen Entreprenad AB ordagrant.',
  alias_proposal: null,
  status: 'open',
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

/** The same numbers, tied to the supplier by nothing stronger than a name that
 *  is almost the invoice's. The engine says so and asks. */
const WEAK_FINDING = {
  ...MATCH_FINDING,
  id: 'f3',
  verdict: 'possible_deviation',
  verdict_label: 'möjlig avvikelse',
  anchor_strength: 'partial',
  anchor_note:
    'Snöröjningsavtal 2026.pdf skriver "Snösvängen AB", fakturan säger '
    + '"Snösvängen Entreprenad AB". Namnen är inte identiska; kopplingen bygger på '
    + 'att den särskiljande delen är densamma.',
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
  note: 'Samma org.nr på fakturan och i avtalets sidhuvud.',
};

const MAPPING = {
  adapter: 'fortnox',
  externalRef: '1042',
  fields: [
    { target: 'external_ref', label: 'Referens i Fortnox', sourceField: 'GivenNumber', matched: true, value: '1042', note: '' },
    { target: 'supplier_name', label: 'Leverantör', sourceField: 'SupplierName', matched: true, value: 'Snösvängen Entreprenad AB', note: '' },
    { target: 'total_amount', label: 'Totalbelopp inkl. moms', sourceField: 'Total', matched: true, value: '6250.00', note: '' },
    { target: 'due_date', label: 'Förfallodatum', sourceField: 'DueDate / FinalPayDate', matched: false, value: null, note: '' },
    {
      target: 'period_start',
      label: 'period_start',
      sourceField: '',
      matched: false,
      value: null,
      note: 'Fortnox leverantörsfaktura har inget periodfält — periodgranskning görs inte för den här källan.',
    },
  ],
  rows: [[
    { target: 'description', label: 'Radtext', sourceField: 'Description', value: 'Maskinell snöröjning med traktor' },
    { target: 'amount', label: 'Radbelopp', sourceField: 'Debit', value: '5000.00' },
  ]],
  observedNotChanged: { Booked: true, Cancelled: false },
  note: 'Fälten läses ur Fortnox och skrivs aldrig tillbaka. Bokförings- och annulleringsstatus visas men ändras inte av den här produkten.',
};

const UNVERIFIABLE_FINDING = {
  ...MATCH_FINDING,
  id: 'f2',
  finding_type: 'invoice_contract_period',
  verdict: 'cannot_be_verified',
  verdict_label: 'kan inte verifieras',
  verified_facts: [{ label: 'Fakturaperiod', value: '2026-01-01 – 2026-01-31', source: 'invoice', citation_index: null }],
  suggestion: 'Ingen avtalsperiod gick att verifiera.',
  uncertainty: 'Ingen daterad period kunde citeras ordagrant.',
  citations: [],
};

const DOCUMENTS = [
  { id: 'doc-contract', name: 'Snöröjningsavtal 2026.pdf' },
  { id: 'doc-invoice', name: 'faktura-2026-114.pdf' },
];

function mountWith({
  events = [EVENT],
  findings = [MATCH_FINDING, UNVERIFIABLE_FINDING],
  invoices = [INVOICE],
  connections = NO_CONNECTIONS,
  aliases = [],
} = {}) {
  integrationsApi.format.mockResolvedValue(FORMAT);
  integrationsApi.connections.mockResolvedValue(connections);
  integrationsApi.listSupplierAliases.mockResolvedValue(aliases);
  integrationsApi.listSourceEvents.mockResolvedValue(events);
  integrationsApi.listInvoices.mockResolvedValue(invoices);
  integrationsApi.availableInvoices.mockResolvedValue({
    adapter: 'fixture-accounting',
    source: 'fixture',
    invoices: [
      {
        external_ref: 'SI-2026-114',
        supplier_name: 'Snösvängen Entreprenad AB',
        invoice_number: '2026-114',
        invoice_date: '2026-02-03',
        due_date: '2026-03-05',
        total_amount: '6250.00',
        currency: 'SEK',
        adapter: 'fixture-accounting',
        dataset: 'gjutformen12-2026.json',
      },
    ],
  });
  integrationsApi.listFindings.mockResolvedValue(findings);
  const onOpenCitation = vi.fn();
  const onOpenDocument = vi.fn();
  render(
    <Integrations
      brfId="brf-a"
      documents={DOCUMENTS}
      onOpenDocument={onOpenDocument}
      onOpenCitation={onOpenCitation}
    />,
  );
  return { onOpenCitation, onOpenDocument };
}

beforeEach(() => {
  vi.clearAllMocks();
});

/** Findings live under their invoice, so the review pane has to be open. */
async function openInvoicePane() {
  fireEvent.click(await screen.findByRole('tab', { name: /Fakturagranskning/ }));
}

/** The verdict word sits next to an icon, so the text node is split. */
const verdictText = (word) => (content, element) =>
  element?.tagName.toLowerCase() === 'span'
  && element.className.includes('verdict')
  && element.textContent.trim() === word;

describe('the incoming queue', () => {
  it('shows provenance the operator can check the message against', async () => {
    mountWith();
    expect(await screen.findByText(/Faktura 2026-114/)).toBeInTheDocument();
    expect(screen.getByText(/Snösvängen Entreprenad AB <faktura@snosvangen.example>/)).toBeInTheDocument();
    // The content hash is shown in full: a truncated hash cannot be compared.
    expect(screen.getByText(EVENT.content_sha256)).toBeInTheDocument();
    expect(screen.getByText(EVENT.external_ref)).toBeInTheDocument();
  });

  it('keeps a proposed link visually distinct from a confirmed one', async () => {
    mountWith();
    await screen.findByText(/Faktura 2026-114/);
    const item = screen.getByText('Snöröjningsavtal 2026.pdf').closest('li');
    expect(within(item).getByText('förslag')).toBeInTheDocument();
    expect(within(item).getByRole('checkbox')).not.toBeChecked();
  });

  it('states the accepted format instead of leaving the operator to guess', async () => {
    mountWith();
    expect(await screen.findByText(/application\/pdf som bilaga/)).toBeInTheDocument();
    expect(screen.getByText(/Allt annat avvisas i sin helhet/)).toBeInTheDocument();
  });

  it('surfaces a refusal reason from the backend verbatim', async () => {
    mountWith();
    await screen.findByText(/Faktura 2026-114/);
    integrationsApi.importSourceEvent.mockRejectedValue(
      new Error("Bilagan 'underlag.csv' är text/csv. Den här versionen tar bara emot application/pdf"),
    );
    const input = document.getElementById('eml-import');
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'underlag.eml', { type: 'message/rfc822' })] },
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/underlag\.csv/);
  });
});

describe('a finding', () => {
  it('separates what is verified from what is proposed and what is uncertain', async () => {
    mountWith();
    await openInvoicePane();
    await screen.findByText(verdictText('överensstämmer'));

    expect(screen.getAllByText('Verifierat ur fakturan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Verifierat ur dokumenten').length).toBeGreaterThan(0);
    expect(screen.getByText(/À-pris för maskinell snöröjning motsvarar/)).toBeInTheDocument();
    expect(screen.getByText(/gäller det citerade villkoret och ingenting annat/)).toBeInTheDocument();
    // The proposal is attributed, not presented as fact.
    expect(screen.getAllByText('(regelmotor)').length).toBe(2);
  });

  it('shows an uncertain verdict as uncertain, with no citation to lean on', async () => {
    mountWith();
    await openInvoicePane();
    expect(await screen.findByText(verdictText('kan inte verifieras'))).toBeInTheDocument();
    expect(screen.getByText(/Ingen daterad period kunde citeras ordagrant/)).toBeInTheDocument();
  });

  it('opens the cited page through the app’s own citation navigation', async () => {
    const { onOpenCitation } = mountWith();
    await openInvoicePane();
    await screen.findByText(verdictText('överensstämmer'));
    fireEvent.click(screen.getAllByTitle('Öppna Snöröjningsavtal 2026.pdf sida 2')[0]);
    expect(onOpenCitation).toHaveBeenCalledWith(CITATION);
  });

  it('quotes the passage verbatim next to its source', async () => {
    mountWith();
    await openInvoicePane();
    await screen.findByText(verdictText('överensstämmer'));
    expect(
      screen.getAllByText('maskinell snöröjning med traktor 1 250 kronor per timme').length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/Snöröjningsavtal 2026\.pdf · s\. 2/).length).toBeGreaterThan(0);
  });

  it('refuses to record a correction without saying what is correct', async () => {
    mountWith();
    await openInvoicePane();
    await screen.findByText(verdictText('överensstämmer'));
    const finding = screen.getByText(verdictText('överensstämmer')).closest('article');
    const correct = within(finding).getByRole('button', { name: 'Korrigera' });
    expect(correct).toBeDisabled();

    fireEvent.change(within(finding).getByLabelText('Beskriv korrigeringen'), {
      target: { value: 'Timtaxan höjdes i tilläggsavtal 2026-01-15.' },
    });
    expect(correct).toBeEnabled();

    integrationsApi.decideFinding.mockResolvedValue({ ...MATCH_FINDING, status: 'corrected' });
    fireEvent.click(correct);
    await waitFor(() =>
      expect(integrationsApi.decideFinding).toHaveBeenCalledWith('brf-a', 'f1', {
        status: 'corrected',
        note: 'Timtaxan höjdes i tilläggsavtal 2026-01-15.',
      }),
    );
  });
});

describe('the invoice pane', () => {
  it('says plainly that nothing is written back', async () => {
    mountWith();
    await openInvoicePane();
    expect(
      await screen.findByText(/kan inte bokföra, kontera, attestera, betala/),
    ).toBeInTheDocument();
  });

  it('shows the invoice provenance and its normalised fields', async () => {
    mountWith();
    await openInvoicePane();
    // Once in the "available to read" table, once as the read snapshot's total.
    expect((await screen.findAllByText('6 250,00 SEK')).length).toBe(2);
    expect(screen.getByText('gjutformen12-2026.json')).toBeInTheDocument();
    expect(screen.getAllByText('SI-2026-114').length).toBeGreaterThan(0);
  });

  it('reads an invoice and runs the review in one operator action', async () => {
    mountWith();
    await openInvoicePane();
    integrationsApi.importInvoice.mockResolvedValue(INVOICE);
    integrationsApi.reviewInvoice.mockResolvedValue({ invoice: INVOICE, findings: [MATCH_FINDING] });

    fireEvent.click(await screen.findByRole('button', { name: /Läs om och granska/ }));
    // The source is named in the request, never inferred from what happens to
    // be connected: a demo read and a live read must not look alike.
    await waitFor(() => expect(integrationsApi.importInvoice).toHaveBeenCalledWith('brf-a', 'SI-2026-114', 'fixture'));
    await waitFor(() => expect(integrationsApi.reviewInvoice).toHaveBeenCalledWith('brf-a', 'inv1'));
  });
});

describe('provenance', () => {
  it('says in words how the message got here', async () => {
    mountWith({ events: [EVENT, MAILBOX_EVENT] });
    expect(await screen.findByText('Någon valde en sparad .eml-fil')).toBeInTheDocument();
    expect(screen.getByText('Hämtat ur den anslutna brevlådan, på begäran')).toBeInTheDocument();
  });
});

describe('adopting an attachment into the archive', () => {
  it('says what adoption means before offering it', async () => {
    mountWith();
    expect(await screen.findByText(/material under granskning tills någon lägger den i/))
      .toBeInTheDocument();
    expect(screen.getByText('material under granskning')).toBeInTheDocument();
  });

  it('refuses to adopt without a stated reason, before the backend is asked', async () => {
    mountWith();
    await screen.findByText(/Faktura 2026-114/);
    const adopt = screen.getByRole('button', { name: /Lägg i arkivet/ });
    expect(adopt).toBeDisabled();

    fireEvent.click(adopt);
    expect(integrationsApi.archiveAttachment).not.toHaveBeenCalled();

    fireEvent.change(
      screen.getByLabelText('Varför faktura-2026-114.pdf hör till föreningens underlag'),
      { target: { value: 'Avtalet styrelsen beslutade om på mötet 2026-01-20.' } },
    );
    expect(adopt).toBeEnabled();

    integrationsApi.archiveAttachment.mockResolvedValue(EVENT);
    fireEvent.click(adopt);
    await waitFor(() => expect(integrationsApi.archiveAttachment).toHaveBeenCalledWith(
      'brf-a', 'ev1', 'att1', 'Avtalet styrelsen beslutade om på mötet 2026-01-20.',
    ));
  });

  it('shows who adopted an attachment, when and why, and offers to undo it', async () => {
    const adopted = {
      ...EVENT,
      attachments: [{
        ...EVENT.attachments[0],
        archived: true,
        archived_by: 'user-1',
        archived_at: '2026-08-01T11:00:00+00:00',
        archive_note: 'Avtalet styrelsen beslutade om.',
      }],
    };
    mountWith({ events: [adopted] });
    expect(await screen.findByText(/Lagd i arkivet av user-1/)).toBeInTheDocument();
    expect(screen.getByText(/Avtalet styrelsen beslutade om\./)).toBeInTheDocument();
    expect(screen.getByText('i föreningens arkiv')).toBeInTheDocument();

    integrationsApi.withdrawAttachment.mockResolvedValue(EVENT);
    fireEvent.click(screen.getByRole('button', { name: 'Ta tillbaka ur arkivet' }));
    await waitFor(() => expect(integrationsApi.withdrawAttachment)
      .toHaveBeenCalledWith('brf-a', 'ev1', 'att1'));
  });
});

describe('the connected mailbox', () => {
  it('keeps the manual .eml import usable with nothing connected', async () => {
    mountWith();
    expect(await screen.findByText('Importera .eml-fil')).toBeInTheDocument();
    expect(screen.getByText(/Ingen brevlåda är ansluten/)).toBeInTheDocument();
    expect(integrationsApi.listMailboxMessages).not.toHaveBeenCalled();
  });

  it('lists the mailbox only when asked, and imports one chosen message', async () => {
    mountWith({ connections: { ...NO_CONNECTIONS, 'microsoft-graph': connected('microsoft-graph') } });
    await screen.findByText(/Faktura 2026-114/);
    expect(integrationsApi.listMailboxMessages).not.toHaveBeenCalled();

    integrationsApi.listMailboxMessages.mockResolvedValue({
      provider: 'microsoft-graph',
      messages: [{
        id: 'AAMkAGI2',
        subject: 'Faktura 2026-115',
        from: 'faktura@snosvangen.example',
        fromDisplay: 'Snösvängen Entreprenad AB',
        receivedAt: '2026-03-02T08:00:00+00:00',
        hasAttachments: true,
        internetMessageId: '<snosvangen115@fixture.invalid>',
        preview: 'Bifogat finner ni faktura 2026-115.',
      }],
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta meddelanden/ }));
    expect(await screen.findByText('Faktura 2026-115')).toBeInTheDocument();

    integrationsApi.importMailboxMessage.mockResolvedValue(MAILBOX_EVENT);
    fireEvent.click(screen.getByRole('button', { name: /Läs in/ }));
    await waitFor(() => expect(integrationsApi.importMailboxMessage)
      .toHaveBeenCalledWith('brf-a', 'AAMkAGI2'));
  });

  it('surfaces a mailbox import refusal the way the manual one is surfaced', async () => {
    mountWith({ connections: { ...NO_CONNECTIONS, 'microsoft-graph': connected('microsoft-graph') } });
    await screen.findByText(/Faktura 2026-114/);
    integrationsApi.listMailboxMessages.mockResolvedValue({
      provider: 'microsoft-graph',
      messages: [{
        id: 'AAMkAGI2', subject: 'Faktura 2026-115', from: 'f@snosvangen.example',
        fromDisplay: '', receivedAt: '2026-03-02T08:00:00+00:00', hasAttachments: true,
        internetMessageId: '<x@fixture.invalid>', preview: '',
      }],
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta meddelanden/ }));
    await screen.findByText('Faktura 2026-115');

    integrationsApi.importMailboxMessage.mockRejectedValue(
      new Error('Meddelandet finns redan i kön som ev1.'),
    );
    fireEvent.click(screen.getByRole('button', { name: /Läs in/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/finns redan i kön/);
  });
});

describe('the anchor', () => {
  it('reads a weak anchor as weak and a strong one as strong', async () => {
    mountWith({ findings: [MATCH_FINDING, WEAK_FINDING] });
    await openInvoicePane();
    await screen.findByText(verdictText('överensstämmer'));

    const strong = screen.getByText('Säker koppling till leverantören').closest('.finding-anchor');
    const weak = screen.getByText('Svag koppling till leverantören').closest('.finding-anchor');
    expect(strong.className).toContain('strong');
    expect(weak.className).toContain('weak');
    expect(strong.className).not.toContain('weak');

    expect(within(weak).getByText(/Namnen är inte identiska/)).toBeInTheDocument();
    expect(within(weak).getByText(/kan alltså gälla fel leverantör/)).toBeInTheDocument();
    expect(within(strong).queryByText(/kan alltså gälla fel leverantör/)).toBeNull();
  });

  it('asks a human to confirm the alias, and posts exactly what was proposed', async () => {
    mountWith({ findings: [WEAK_FINDING] });
    await openInvoicePane();
    await screen.findByText(verdictText('möjlig avvikelse'));
    expect(screen.getByText(/Den särskiljande delen "Snösvängen AB" står ordagrant/))
      .toBeInTheDocument();

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
    // Confirming does not rewrite the finding that has already been recorded;
    // it offers the re-run that would.
    expect(await screen.findByRole('button', { name: /Kör om granskningen/ })).toBeInTheDocument();
  });

  it('lists the confirmed names and can take one back', async () => {
    mountWith({ aliases: [ALIAS] });
    await openInvoicePane();
    expect(await screen.findByText('Snösvängen AB')).toBeInTheDocument();
    integrationsApi.deleteSupplierAlias.mockResolvedValue({ deleted: 'al1' });
    fireEvent.click(screen.getByRole('button', {
      name: 'Ta bort Snösvängen Entreprenad AB = Snösvängen AB',
    }));
    await waitFor(() => expect(integrationsApi.deleteSupplierAlias).toHaveBeenCalledWith('brf-a', 'al1'));
  });
});

describe('the mapping check', () => {
  const withFortnox = () => mountWith({
    connections: { ...NO_CONNECTIONS, fortnox: connected('fortnox') },
  });

  it('renders every field, including the ones nothing could be read into', async () => {
    withFortnox();
    integrationsApi.mappingPreview.mockResolvedValue(MAPPING);
    fireEvent.click(await screen.findByRole('tab', { name: /Fältkontroll/ }));

    fireEvent.change(screen.getByLabelText('Fakturans dokumentnummer i Fortnox'), {
      target: { value: '1042' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta fältmappning/ }));
    await waitFor(() => expect(integrationsApi.mappingPreview).toHaveBeenCalledWith('brf-a', '1042'));

    for (const field of MAPPING.fields) {
      expect(await screen.findByText(field.label)).toBeInTheDocument();
      expect(screen.getByText(field.target)).toBeInTheDocument();
    }
    // Two fields carry no value, and both are on screen rather than dropped.
    expect(screen.getAllByText('inget värde').length).toBe(2);
    expect(screen.getByText(/har inget periodfält/)).toBeInTheDocument();

    const missing = screen.getByText('Förfallodatum').closest('tr');
    expect(missing.className).toContain('unmatched');
    expect(screen.getByText('Referens i Fortnox').closest('tr').className).toContain('matched');
  });

  it('shows the bookkeeping state as read and never written', async () => {
    withFortnox();
    integrationsApi.mappingPreview.mockResolvedValue(MAPPING);
    fireEvent.click(await screen.findByRole('tab', { name: /Fältkontroll/ }));
    fireEvent.change(screen.getByLabelText('Fakturans dokumentnummer i Fortnox'), {
      target: { value: '1042' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta fältmappning/ }));

    expect(await screen.findByText('Läses och visas — ändras aldrig')).toBeInTheDocument();
    const booked = screen.getByText('Bokförd').closest('div');
    expect(within(booked).getByText('ja')).toBeInTheDocument();
    expect(screen.getByText(/skrivs aldrig tillbaka/)).toBeInTheDocument();
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

  it('never reads, stores or sends a token — in any component or any test', () => {
    const files = [
      './components/Integrations.jsx',
      './components/IntegrationConnections.jsx',
      './components/MappingPreview.jsx',
      './api.js',
      './Integrations.test.jsx',
      './IntegrationConnections.test.jsx',
    ];
    for (const file of files) {
      const source = sourceOf(file).toLowerCase();
      for (const needle of FORBIDDEN) expect(source).not.toContain(needle.toLowerCase());
    }
    // The session travels as a cookie the browser attaches by itself, on every
    // call — which is why there is nothing for these files to read.
    expect(sourceOf('./api.js')).toContain("credentials: 'include'");
  });
});
