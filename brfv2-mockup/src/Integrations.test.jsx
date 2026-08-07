import React from 'react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Integrations from './components/Integrations';
import { intakeApi, integrationsApi } from './api';

/**
 * Inkommande — the shell around the review queue and the connections.
 *
 * The invoice review used to be a third pane here and is now its own product
 * area (Invoices.test.jsx). What this file asserts is what remains true of the
 * shell: two panes, a count that comes from the queue rather than from a guess,
 * and no token anywhere near the wire.
 */

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
  invoicesApi: {
    workspace: vi.fn(),
    case: vi.fn(),
    importInvoice: vi.fn(),
    refresh: vi.fn(),
    update: vi.fn(),
    comment: vi.fn(),
  },
  // The inbox pane is its own component with its own suite
  // (IntakeQueue.test.jsx). It is still mocked here so that the pane this
  // shell renders by default is in a working state rather than a permanently
  // failed one — an error banner nobody asserts on would mask the next real
  // regression in the shell.
  intakeApi: {
    queue: vi.fn(),
    fetch: vi.fn(),
    retriage: vi.fn(),
    confirmCategory: vi.fn(),
    resolve: vi.fn(),
    reopen: vi.fn(),
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
  attachments: [],
  import_status: 'imported',
  review_status: 'open',
  error: null,
  linked_document_ids: [],
  suggested_document_ids: [],
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

function mountWith({ events = [EVENT], connections = NO_CONNECTIONS } = {}) {
  integrationsApi.format.mockResolvedValue(FORMAT);
  integrationsApi.connections.mockResolvedValue(connections);
  integrationsApi.listSourceEvents.mockResolvedValue(events);
  intakeApi.queue.mockResolvedValue({
    threads: [],
    categoryLabels: {},
    resolutionLabels: {},
    mailbox: { hasFetched: false },
    counts: {},
  });
  const onOpenDocument = vi.fn();
  render(<Integrations brfId="brf-a" onOpenDocument={onOpenDocument} />);
  return { onOpenDocument };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the incoming shell', () => {
  it('offers the queue and the connections, and nothing else', async () => {
    mountWith();
    expect(await screen.findByRole('tab', { name: /Inkommande/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Anslutningar/ })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
  });

  it('counts what is still waiting for a decision', async () => {
    mountWith({ events: [EVENT, { ...EVENT, id: 'ev2', review_status: 'approved' }] });
    const tab = await screen.findByRole('tab', { name: /Inkommande/ });
    expect(tab.textContent).toContain('1');
  });

  it('shows the open count as quiet navigation chrome, not a loud badge', async () => {
    mountWith({ events: [EVENT, { ...EVENT, id: 'ev2' }] });
    await waitFor(() => expect(screen.getByRole('tab', { name: /Inkommande/ })).toBeInTheDocument());
    const tab = screen.getByRole('tab', { name: /Inkommande/ });
    expect(tab.querySelector('.tab-count')).toHaveTextContent('2');
    expect(tab.querySelector('.pill')).toBeNull();
  });

  /* The invoice review moved out. Asserting its absence here is what keeps the
     product from quietly growing a second invoice screen that disagrees with
     the first. */
  it('no longer reviews invoices', async () => {
    mountWith();
    await screen.findByRole('tab', { name: /Inkommande/ });
    expect(screen.queryByRole('tab', { name: /Fakturagranskning/ })).toBeNull();
    expect(screen.queryByRole('tab', { name: /Fältkontroll/ })).toBeNull();
    expect(integrationsApi.listInvoices).not.toHaveBeenCalled();
    expect(integrationsApi.listFindings).not.toHaveBeenCalled();
    expect(integrationsApi.availableInvoices).not.toHaveBeenCalled();
  });

  it('shows the connections pane on request', async () => {
    mountWith();
    fireEvent.click(await screen.findByRole('tab', { name: /Anslutningar/ }));
    expect(await screen.findByText(/Microsoft 365/i)).toBeInTheDocument();
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
