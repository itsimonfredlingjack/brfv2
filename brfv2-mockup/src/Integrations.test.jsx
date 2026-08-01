import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Integrations from './components/Integrations';
import { integrationsApi } from './api';

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {
    format: vi.fn(),
    listSourceEvents: vi.fn(),
    importSourceEvent: vi.fn(),
    decideSourceEvent: vi.fn(),
    deleteSourceEvent: vi.fn(),
    availableInvoices: vi.fn(),
    listInvoices: vi.fn(),
    importInvoice: vi.fn(),
    reviewInvoice: vi.fn(),
    listFindings: vi.fn(),
    decideFinding: vi.fn(),
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
};

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
  status: 'open',
  decided_by: null,
  decided_at: null,
  decision_note: null,
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

function mountWith({ events = [EVENT], findings = [MATCH_FINDING, UNVERIFIABLE_FINDING], invoices = [INVOICE] } = {}) {
  integrationsApi.format.mockResolvedValue(FORMAT);
  integrationsApi.listSourceEvents.mockResolvedValue(events);
  integrationsApi.listInvoices.mockResolvedValue(invoices);
  integrationsApi.availableInvoices.mockResolvedValue({
    adapter: 'fixture-accounting',
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
    await waitFor(() => expect(integrationsApi.importInvoice).toHaveBeenCalledWith('brf-a', 'SI-2026-114'));
    await waitFor(() => expect(integrationsApi.reviewInvoice).toHaveBeenCalledWith('brf-a', 'inv1'));
  });
});
