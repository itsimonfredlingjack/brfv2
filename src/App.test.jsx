import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from './App';
import { api } from './api';

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
}));

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

    fireEvent.click(await screen.findByRole('button', { name: 'AI-chatt' }));
    const input = await screen.findByPlaceholderText('Ställ en generell fråga till AI:n...');
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
