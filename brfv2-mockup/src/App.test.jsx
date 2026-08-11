import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from './App';
import { api, desktopApi } from './api';

// PdfPane pulls in pdfjs-dist, which needs browser canvas APIs (DOMMatrix)
// jsdom doesn't provide — none of these tests open a document, so a stub
// is sufficient and keeps the suite fast and dependency-free.
vi.mock('./components/PdfPane', () => ({
  default: () => null,
}));

vi.mock('./api', () => ({
  api: {
    health: vi.fn(),
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getExtraction: vi.fn(),
    pdfUrl: vi.fn(() => '/fake.pdf'),
    ask: vi.fn(),
    getSettings: vi.fn(),
    putSettings: vi.fn(),
  },
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
  desktopApi: {
    state: vi.fn(),
    setup: vi.fn(),
    createBrf: vi.fn(),
    getModelRuntime: vi.fn(),
    putModelRuntime: vi.fn(),
    testModelRuntime: vi.fn(),
    listBackups: vi.fn(),
    createBackup: vi.fn(),
    deleteBackup: vi.fn(),
    restoreBackup: vi.fn(),
    restart: vi.fn(),
  },
}));

/** The web delivery does not serve /api/desktop/* at all. */
const notADesktop = () => {
  const error = new Error('Not Found');
  error.status = 404;
  return Promise.reject(error);
};

const DESKTOP_STATE = {
  schema: 'brfv2-desktop-state/v1',
  app: { name: 'Träff', version: '0.2.0' },
  provisioned: true,
  storage: {
    dataDir: '/home/anvandare/.local/share/se.brfdokumentai.desktop/data',
    backupDir: '/home/anvandare/.local/share/se.brfdokumentai.desktop/backups',
  },
  ocr: { available: true, language: 'swe' },
  embedding: { provider: 'model2vec:potion-multilingual-128M' },
  modelRuntime: {
    baseUrl: 'http://127.0.0.1:8000/v1',
    model: 'gemma4:e12b',
    label: 'agenntserver',
    timeoutS: 300,
    hasApiKey: false,
    configured: true,
    provider: 'selfhosted',
    ready: true,
    deploymentClass: 'loopback',
  },
  installationAdmin: true,
  modelEndpointPolicy: {
    policy: 'brfv2-model-endpoint-policy/v1',
    default: 'deny',
    authority: 'installation-administrator',
  },
  lastRestore: null,
  restartSupported: true,
};

const MAX_USER = { id: 'max-id', email: 'max@demo.se', name: 'Max Demo' };
const MAX_MEMBERSHIPS = [
  { brf_id: 'gjutformen-12', name: 'Brf Gjutformen 12', role: 'admin' },
  { brf_id: 'sjoutsikten-7', name: 'Brf Sjöutsikten 7', role: 'member' },
];

const ANNA_USER = { id: 'anna-id', email: 'anna@gjutformen12.se', name: 'Anna Andersson' };
const ANNA_MEMBERSHIPS = [{ brf_id: 'gjutformen-12', name: 'Brf Gjutformen 12', role: 'admin' }];

const GJUTFORMEN_DOCS = [
  { id: 'd1', name: 'Stadgar Gjutformen.pdf', uploaded_at: '2026-07-21T00:00:00Z', pages: 5 },
];
const SJOUTSIKTEN_DOCS = [
  { id: 'd2', name: 'Stadgar Sjöutsikten.pdf', uploaded_at: '2026-07-21T00:00:00Z', pages: 3 },
];

function docsFor(brfId) {
  return Promise.resolve(brfId === 'gjutformen-12' ? GJUTFORMEN_DOCS : SJOUTSIKTEN_DOCS);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.health.mockResolvedValue({
    llm: { provider: 'fake', model: '', display_name: '', runtime_label: '', ready: false },
  });
  api.listDocuments.mockImplementation(docsFor);
  desktopApi.state.mockImplementation(notADesktop);
});

describe('session restore + membership rendering', () => {
  it("Max's restored session carries both memberships and renders a real selector", async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    render(<App />);

    const select = await screen.findByRole('combobox', { name: 'Byt aktiv förening' });
    const options = within(select).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['Brf Gjutformen 12', 'Brf Sjöutsikten 7']);
    expect(select.value).toBe('gjutformen-12');

    // Identity is unambiguous: Max's own name/email are on screen, not Anna's.
    expect(screen.getByText('Max Demo')).toBeInTheDocument();
    expect(screen.getByText('max@demo.se')).toBeInTheDocument();
    expect(screen.queryByText('Anna Andersson')).not.toBeInTheDocument();
  });

  it("Anna's restored session carries one membership and renders a static display, never a fake dropdown", async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    render(<App />);

    await screen.findByText('Brf Gjutformen 12');
    expect(screen.queryByRole('combobox', { name: 'Byt aktiv förening' })).not.toBeInTheDocument();
    expect(screen.getByText('Aktiv förening')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();

    // A restored single-BRF session must be visibly Anna, not confusable with Max.
    expect(screen.getByText('Anna Andersson')).toBeInTheDocument();
    expect(screen.getByText('anna@gjutformen12.se')).toBeInTheDocument();
    expect(screen.queryByText('Max Demo')).not.toBeInTheDocument();
  });
});

describe('tenant switching', () => {
  it('switching associations changes the document corpus, admin controls, and role badge — and switching back restores them', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    render(<App />);

    const docsNav = await screen.findByRole('button', { name: 'Dokument' });
    fireEvent.click(docsNav);

    await screen.findAllByText('Stadgar Gjutformen.pdf');
    expect(screen.getByRole('button', { name: 'Ladda upp dokument' })).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();

    const select = screen.getByRole('combobox', { name: 'Byt aktiv förening' });
    fireEvent.change(select, { target: { value: 'sjoutsikten-7' } });

    await screen.findAllByText('Stadgar Sjöutsikten.pdf');
    expect(screen.queryAllByText('Stadgar Gjutformen.pdf')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Ladda upp dokument' })).not.toBeInTheDocument();
    expect(screen.getByText('Medlem')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'gjutformen-12' } });

    await screen.findAllByText('Stadgar Gjutformen.pdf');
    expect(screen.queryAllByText('Stadgar Sjöutsikten.pdf')).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Ladda upp dokument' })).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  it('clears the previous document list immediately, before the new tenant finishes loading', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    let resolveSecond;
    api.listDocuments.mockImplementation((brfId) => {
      if (brfId === 'gjutformen-12') return Promise.resolve(GJUTFORMEN_DOCS);
      return new Promise((resolve) => { resolveSecond = resolve; });
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Dokument' }));
    await screen.findAllByText('Stadgar Gjutformen.pdf');

    const select = screen.getByRole('combobox', { name: 'Byt aktiv förening' });
    fireEvent.change(select, { target: { value: 'sjoutsikten-7' } });

    // The old tenant's document must disappear immediately, well before the
    // new tenant's (still-pending) request resolves — no stale data lingers
    // on screen mid-switch.
    await waitFor(() => expect(screen.queryAllByText('Stadgar Gjutformen.pdf')).toHaveLength(0));

    resolveSecond(SJOUTSIKTEN_DOCS);
    await screen.findAllByText('Stadgar Sjöutsikten.pdf');
  });

  it('clears the global AI chat conversation on tenant switch, so nothing leaks across tenants', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.ask.mockResolvedValue({
      answer: 'Hemligt Gjutformen-svar.',
      citations: [],
      provider: 'fake',
      model: '',
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    const input = await screen.findByPlaceholderText('Fråga rakt in i högen…');
    fireEvent.change(input, { target: { value: 'Hej?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka fråga' }));

    await screen.findByText('Hemligt Gjutformen-svar.');

    const select = screen.getByRole('combobox', { name: 'Byt aktiv förening' });
    fireEvent.change(select, { target: { value: 'sjoutsikten-7' } });

    await waitFor(() =>
      expect(screen.queryByText('Hemligt Gjutformen-svar.')).not.toBeInTheDocument()
    );
  });
});

describe('keyboard accessibility', () => {
  it('the active-association selector is a native, focusable <select>', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    render(<App />);

    const select = await screen.findByRole('combobox', { name: 'Byt aktiv förening' });
    expect(select.tagName).toBe('SELECT');
    select.focus();
    expect(select).toHaveFocus();
  });
});

describe('model status indicator', () => {
  it('shows a loading state until /api/health resolves, then the real configured model', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    let resolveHealth;
    api.health.mockImplementation(() => new Promise((resolve) => { resolveHealth = resolve; }));
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    expect(await screen.findByText('Kontrollerar modell…')).toBeInTheDocument();

    resolveHealth({
      llm: { provider: 'selfhosted', model: 'gemma4:e12b', display_name: 'Gemma 4 12B', runtime_label: 'agenntserver', ready: true },
    });

    await screen.findByText('Gemma 4 12B');
    expect(screen.queryByText('Kontrollerar modell…')).not.toBeInTheDocument();
  });

  it('ready state shows the configured model, provider and runtime label with accessible markup', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.health.mockResolvedValue({
      llm: { provider: 'selfhosted', model: 'gemma4:e12b', display_name: 'Gemma 4 12B', runtime_label: 'agenntserver', ready: true },
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    await screen.findByText('Gemma 4 12B');
    expect(screen.getByText('Self-hosted · agenntserver')).toBeInTheDocument();

    // Accessible name/description: a screen reader gets the full status
    // even though the secondary line is visually hidden on narrow screens.
    expect(screen.getByLabelText('Modellstatus: Gemma 4 12B, Self-hosted · agenntserver')).toBeInTheDocument();
    expect(screen.getByTitle('Modellen som just nu används för att generera AI-chattens svar.')).toBeInTheDocument();
  });

  it('shows "Modellstatus ej tillgänglig" when /api/health fails outright', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.health.mockRejectedValue(new Error('network down'));
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    expect(await screen.findByText('Modellstatus ej tillgänglig.')).toBeInTheDocument();
  });

  it('shows a warning, not a false ready claim, when the configured provider has no active model', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.health.mockResolvedValue({
      llm: { provider: 'fake', model: '', display_name: '', runtime_label: '', ready: false },
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    expect(await screen.findByText('Testleverantören är inte en modell.')).toBeInTheDocument();
    expect(screen.queryByText('Modellstatus ej tillgänglig.')).not.toBeInTheDocument();
  });

  it('never fabricates a Gemma/agenntserver claim for a different provider or model', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.health.mockResolvedValue({
      llm: { provider: 'nagon-annan-leverantor', model: 'nagon-annan-modell', display_name: '', runtime_label: '', ready: true },
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    // No display_name from the backend and an unrecognized provider/model id —
    // the shared normalizer must fall back to the raw identifiers, never
    // Gemma, and never invent a friendly name for something it does not know.
    await screen.findByText('nagon-annan-modell');
    expect(screen.getByText('nagon-annan-leverantor')).toBeInTheDocument();
    expect(screen.queryByText(/Gemma/)).not.toBeInTheDocument();
    expect(screen.queryByText(/agenntserver/)).not.toBeInTheDocument();
  });
});

describe('answer-level provenance', () => {
  it('renders provider/model from the specific /ask response, and never on the user bubble or while pending', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    let resolveAsk;
    api.ask.mockImplementation(() => new Promise((resolve) => { resolveAsk = resolve; }));
    const { container } = render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    const input = await screen.findByPlaceholderText('Fråga rakt in i högen…');
    fireEvent.change(input, { target: { value: 'Vilket regelverk gäller?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka fråga' }));

    // Mid-flight: user bubble + pending AI bubble on screen, no provenance
    // anywhere yet — not on the user message, not on the pending one.
    expect(screen.getByText('Vilket regelverk gäller?')).toBeInTheDocument();
    expect(container.querySelectorAll('.chat-model-provenance')).toHaveLength(0);

    resolveAsk({
      answer: 'Bostadsrättslagen gäller.',
      citations: [],
      provider: 'selfhosted',
      model: 'gemma4:e12b',
    });

    await screen.findByText('Bostadsrättslagen gäller.');
    expect(screen.getByText('Gemma 4 12B · Self-hosted')).toBeInTheDocument();
    expect(container.querySelectorAll('.chat-model-provenance')).toHaveLength(1);
  });

  it('shows no provenance for a refusal where no model was ever invoked', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.ask.mockResolvedValue({
      answer: 'Det finns inga dokument uppladdade ännu.',
      refusal: true,
      refusal_reason: 'no_documents',
      citations: [],
      provider: 'selfhosted',
      model: 'gemma4:e12b',
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    const input = await screen.findByPlaceholderText('Fråga rakt in i högen…');
    fireEvent.change(input, { target: { value: 'Finns det dokument?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka fråga' }));

    await screen.findByText('Det finns inga dokument uppladdade ännu.');
    expect(screen.queryByText('Gemma 4 12B · Self-hosted')).not.toBeInTheDocument();
  });

  it('shows provenance for a refusal where the model WAS invoked (e.g. grounding_failed)', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    api.ask.mockResolvedValue({
      answer: 'Jag kunde inte verifiera källhänvisningarna.',
      refusal: true,
      refusal_reason: 'grounding_failed',
      citations: [],
      provider: 'selfhosted',
      model: 'gemma4:e12b',
    });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    const input = await screen.findByPlaceholderText('Fråga rakt in i högen…');
    fireEvent.change(input, { target: { value: 'Något komplext?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka fråga' }));

    await screen.findByText('Jag kunde inte verifiera källhänvisningarna.');
    expect(screen.getByText('Gemma 4 12B · Self-hosted')).toBeInTheDocument();
  });
});

describe('desktop delivery', () => {
  it('an unprovisioned installation opens first-run setup, never a login form for accounts that do not exist', async () => {
    desktopApi.state.mockResolvedValue({ ...DESKTOP_STATE, provisioned: false });
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Välkommen' })).toBeInTheDocument();
    expect(screen.getByLabelText(/Föreningens namn/i, { selector: 'input' })).toBeInTheDocument();
    // No credentials to type, so no login form and no session probe at all.
    expect(screen.queryByRole('button', { name: 'Logga in' })).not.toBeInTheDocument();
    expect(api.me).not.toHaveBeenCalled();
    // The user is told where their data will live before they commit to it.
    expect(screen.getByText(DESKTOP_STATE.storage.dataDir)).toBeInTheDocument();
  });

  it('setup creates the owner and association, then offers the model runtime before entering the app', async () => {
    desktopApi.state.mockResolvedValue({ ...DESKTOP_STATE, provisioned: false });
    desktopApi.setup.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    render(<App />);

    await screen.findByRole('heading', { name: 'Välkommen' });
    fireEvent.change(screen.getByLabelText(/Föreningens namn/i, { selector: 'input' }), {
      target: { value: 'Brf Gjutformen 12' },
    });
    fireEvent.change(screen.getByLabelText(/E-postadress/i, { selector: 'input' }), {
      target: { value: 'anna@gjutformen12.se' },
    });
    fireEvent.change(screen.getByLabelText(/^Lösenord/i, { selector: 'input' }), {
      target: { value: 'ett-langt-nog-losenord' },
    });
    fireEvent.change(screen.getByLabelText(/Upprepa lösenord/i, { selector: 'input' }), {
      target: { value: 'ett-langt-nog-losenord' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Skapa förening' }));

    await waitFor(() => expect(desktopApi.setup).toHaveBeenCalledWith({
      name: '',
      email: 'anna@gjutformen12.se',
      password: 'ett-langt-nog-losenord',
      brfName: 'Brf Gjutformen 12',
    }));

    // Step two is optional and honest about what is lost by skipping it.
    expect(await screen.findByRole('heading', { name: 'Föreningen är skapad' })).toBeInTheDocument();
    expect(screen.getByText(/AI-chatten kan inte generera svar/i)).toBeInTheDocument();

    desktopApi.state.mockResolvedValue(DESKTOP_STATE);
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    fireEvent.click(screen.getByRole('button', { name: 'Hoppa över' }));

    await screen.findByText('Anna Andersson');
    expect(desktopApi.putModelRuntime).not.toHaveBeenCalled();
  });

  it('exposes the desktop-only settings, and the web delivery does not', async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    const { unmount } = render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    expect(screen.queryByText('Appinställningar')).not.toBeInTheDocument();
    unmount();

    desktopApi.state.mockResolvedValue(DESKTOP_STATE);
    desktopApi.listBackups.mockResolvedValue({ backupDir: DESKTOP_STATE.storage.backupDir, backups: [] });
    render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    fireEvent.click(screen.getByText('Appinställningar'));

    const dialog = await screen.findByRole('dialog', { name: 'Appinställningar' });
    expect(within(dialog).getByText(DESKTOP_STATE.storage.dataDir)).toBeInTheDocument();
    expect(within(dialog).getByText('Inga säkerhetskopior ännu.')).toBeInTheDocument();
    expect(within(dialog).getByText('Konfigurerad')).toBeInTheDocument();
  });

  it('keeps a stored model token when the field is untouched and re-reads the model badge after saving', async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    desktopApi.state.mockResolvedValue({
      ...DESKTOP_STATE,
      modelRuntime: { ...DESKTOP_STATE.modelRuntime, hasApiKey: true },
    });
    desktopApi.listBackups.mockResolvedValue({ backupDir: '/tmp/backups', backups: [] });
    desktopApi.putModelRuntime.mockResolvedValue({});
    desktopApi.testModelRuntime.mockResolvedValue({ ok: true, detail: 'Modelltjänsten svarar.', served: ['gemma-4-12b'] });
    render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    fireEvent.click(screen.getByText('Appinställningar'));
    const dialog = await screen.findByRole('dialog', { name: 'Appinställningar' });

    api.health.mockClear();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Spara och testa' }));

    await waitFor(() => expect(desktopApi.putModelRuntime).toHaveBeenCalledWith({
      baseUrl: 'http://127.0.0.1:8000/v1',
      model: 'gemma4:e12b',
      label: 'agenntserver',
      apiKey: null,
      timeoutS: 300,
    }));
    expect(await within(dialog).findByText(/Modelltjänsten svarar/)).toBeInTheDocument();
    await waitFor(() => expect(api.health).toHaveBeenCalled());
  });

  it('lets an ordinary account read the model service but never change it', async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    desktopApi.state.mockResolvedValue({ ...DESKTOP_STATE, installationAdmin: false });
    desktopApi.listBackups.mockResolvedValue({ backupDir: '/tmp/backups', backups: [] });
    render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    fireEvent.click(screen.getByText('Appinställningar'));
    const dialog = await screen.findByRole('dialog', { name: 'Appinställningar' });

    // The address stays readable — it is the provenance behind every answer.
    expect(within(dialog).getByDisplayValue('http://127.0.0.1:8000/v1')).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Spara och testa' })).toBeDisabled();
    expect(
      within(dialog).getByText(/ändras bara av installationsadministratören/i),
    ).toBeInTheDocument();
    expect(desktopApi.putModelRuntime).not.toHaveBeenCalled();
  });

  it('states which endpoints the installation will accept at all', async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    desktopApi.state.mockResolvedValue(DESKTOP_STATE);
    desktopApi.listBackups.mockResolvedValue({ backupDir: '/tmp/backups', backups: [] });
    render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    fireEvent.click(screen.getByText('Appinställningar'));
    const dialog = await screen.findByRole('dialog', { name: 'Appinställningar' });

    expect(within(dialog).getByText('127.0.0.0/8')).toBeInTheDocument();
    expect(within(dialog).getByText('192.168.0.0/16')).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Domännamn och publika adresser avvisas/i),
    ).toBeInTheDocument();
  });

  it('stages a restore instead of swapping the data underneath a running backend', async () => {
    api.me.mockResolvedValue({ user: ANNA_USER, memberships: ANNA_MEMBERSHIPS });
    desktopApi.state.mockResolvedValue(DESKTOP_STATE);
    desktopApi.listBackups.mockResolvedValue({
      backupDir: '/tmp/backups',
      backups: [{ name: 'brfv2-backup-20260728-101500-ab12.zip', bytes: 4096, createdAt: '2026-07-28T10:15:00+00:00' }],
    });
    desktopApi.restoreBackup.mockResolvedValue({ staged: 'x', restartRequired: true });
    render(<App />);

    await screen.findByText('Anna Andersson');
    fireEvent.click(screen.getByText('Anna Andersson'));
    fireEvent.click(screen.getByText('Appinställningar'));
    const dialog = await screen.findByRole('dialog', { name: 'Appinställningar' });

    fireEvent.click(await within(dialog).findByRole('button', { name: /Återställ/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ja, återställ' }));

    await waitFor(() => expect(desktopApi.restoreBackup)
      .toHaveBeenCalledWith('brfv2-backup-20260728-101500-ab12.zip'));
    expect(await within(dialog).findByText(/genomförs vid nästa start/i)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /Starta om nu/ })).toBeInTheDocument();
  });
});

describe('the keyboard flow', () => {
  it('"/" focuses the document search on the Dokument tab', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    render(<App />);

    const input = await screen.findByLabelText('Sök dokument');
    fireEvent.keyDown(window, { key: '/' });
    expect(document.activeElement).toBe(input);
  });

  it('"/" stays inert on tabs where the field is not on screen', async () => {
    api.me.mockResolvedValue({ user: MAX_USER, memberships: MAX_MEMBERSHIPS });
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Fråga dokumenten' }));
    await screen.findByPlaceholderText('Fråga rakt in i högen…');
    fireEvent.keyDown(window, { key: '/' });
    expect(document.activeElement).toBe(document.body);
  });
});
