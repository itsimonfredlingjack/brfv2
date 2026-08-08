import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Website from './components/website/Website';
import { api, websiteApi } from './api';

vi.mock('./api', () => ({
  api: { listDocuments: vi.fn() },
  websiteApi: {
    workspace: vi.fn(),
    vocabulary: vi.fn(),
    page: vi.fn(),
    published: vi.fn(),
    initialize: vi.fn(),
    runCommands: vi.fn(),
    ai: vi.fn(),
    undo: vi.fn(),
    publish: vi.fn(),
    unpublish: vi.fn(),
    revisions: vi.fn(),
    rollback: vi.fn(),
    blockSources: vi.fn(),
  },
}));

const VOCABULARY = {
  categories: ['innehåll'],
  components: {
    Hero: {
      label: 'Toppsektion',
      fields: { heading: { kind: 'text', label: 'Rubrik' } },
    },
  },
};

const page = (overrides = {}) => ({
  id: 'page-1',
  slug: 'start',
  title: 'Startsida',
  home: true,
  published: false,
  publication: null,
  has_unpublished_changes: true,
  revision_seq: 0,
  publish_window: { starts: '', ends: '' },
  draft: {
    title: 'Startsida',
    content: [{
      id: 'b1',
      type: 'Hero',
      props: { heading: 'Välkommen', preamble: '', variant: 'plain', image: { src: '', alt: '' }, action: { label: '', href: '' } },
      grounding: 'authored',
      grounding_label: 'Skrivet av föreningen',
      sources: [],
    }],
    based_on_revision_id: '',
  },
  published_revision: null,
  ...overrides,
});

const workspace = (overrides = {}) => ({
  settings: { name: 'Brf Gjutformen 12', accent: 'koppar' },
  pages: [{ id: 'page-1', slug: 'start', title: 'Startsida', home: true, published: false, has_unpublished_changes: true, publication: null, publish_window: { starts: '', ends: '' }, revision_seq: 0, block_count: 1 }],
  navigation: [{ page_id: 'page-1', slug: 'start', label: 'Startsida', published: false }],
  history: [],
  counts: { pages: 1, published: 0, unpublished_changes: 1 },
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  api.listDocuments.mockResolvedValue([]);
  websiteApi.vocabulary.mockResolvedValue(VOCABULARY);
  websiteApi.workspace.mockResolvedValue(workspace());
  websiteApi.page.mockResolvedValue(page());
});

describe('Hemsidan — arbetsytan', () => {
  it('erbjuder att skapa webbplatsen innan den finns, utan att skapa den vid läsning', async () => {
    websiteApi.workspace.mockResolvedValue(workspace({ pages: [], navigation: [], counts: { pages: 0, published: 0, unpublished_changes: 0 } }));
    render(<Website brfId="brf-1" isAdmin />);

    expect(await screen.findByRole('button', { name: /Skapa startsidan/ })).toBeInTheDocument();
    // A read must never have written anything.
    expect(websiteApi.initialize).not.toHaveBeenCalled();
  });

  it('säger till en medlem att en administratör måste börja', async () => {
    websiteApi.workspace.mockResolvedValue(workspace({ pages: [], navigation: [] }));
    render(<Website brfId="brf-1" isAdmin={false} />);

    expect(await screen.findByText(/administratör behöver komma igång/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Skapa startsidan/ })).not.toBeInTheDocument();
  });

  it('visar sidväljaren, publiceringsläget och visningsbredderna', async () => {
    render(<Website brfId="brf-1" isAdmin />);

    expect(await screen.findByLabelText('Välj sida')).toBeInTheDocument();
    expect(screen.getByText('Utkast · aldrig publicerad')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mobil/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dator/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publicera' })).toBeInTheDocument();
  });

  it('växlar canvasbredd när en annan vy väljs', async () => {
    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');

    const canvas = screen.getByTestId('site-canvas');
    expect(canvas).toHaveStyle({ width: '100%' });

    fireEvent.click(screen.getByRole('button', { name: /Mobil/ }));
    expect(screen.getByTestId('site-canvas')).toHaveStyle({ width: '390px' });
  });

  it('säger att en publicerad sida utan ändringar inte har något att publicera', async () => {
    const published = page({
      published: true,
      has_unpublished_changes: false,
      publication: { revision_id: 'rev-1', seq: 2, published_at: '2026-08-01T10:00:00+00:00', published_by: 'u1', rollback: false, note: '' },
    });
    websiteApi.page.mockResolvedValue(published);
    render(<Website brfId="brf-1" isAdmin />);

    await screen.findByLabelText('Välj sida');
    expect(screen.getByText('Publicerad · version 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publicera' })).toBeDisabled();
  });

  it('döljer redigeringsknapparna för en medlem', async () => {
    render(<Website brfId="brf-1" isAdmin={false} />);
    await screen.findByLabelText('Välj sida');

    expect(screen.queryByRole('button', { name: /Lägg till block/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publicera' })).not.toBeInTheDocument();
    // Reading is still allowed — the workspace is not hidden, it is read-only.
    expect(screen.getByRole('button', { name: /Versioner/ })).toBeInTheDocument();
  });
});

describe('Hemsidan — AI-partnern', () => {
  it('tillämpar en ändring direkt och erbjuder att ångra hela den', async () => {
    websiteApi.ai.mockResolvedValue({
      applied: true,
      refusal: '',
      message: 'Jag la till sidan och en menypost.',
      transaction: { id: 'tx-1', summary: 'Ny sida för nya boende', operation_count: 6, actor: 'ai', actor_label: 'AI-ändring', undone_by: '', undoes: '' },
      sources: [],
      workspace: workspace(),
    });
    websiteApi.undo.mockResolvedValue({ workspace: workspace() });

    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');

    fireEvent.change(screen.getByLabelText('Instruktion till AI-partnern'), {
      target: { value: 'Skapa en sida för nya boende' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka' }));

    expect(await screen.findByText('Ny sida för nya boende')).toBeInTheDocument();
    expect(screen.getByText('6 operationer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Ångra allt/ }));
    await waitFor(() => expect(websiteApi.undo).toHaveBeenCalledWith('brf-1', 'tx-1'));
    expect(await screen.findByText('Ångrad')).toBeInTheDocument();
  });

  it('visar en vägran som ett besked om att ingenting skrevs', async () => {
    websiteApi.ai.mockResolvedValue({
      applied: false,
      refusal: 'AI:n ville skriva 4,5 på sidan, men det finns inte i föreningens dokument.',
      message: '',
      workspace: workspace(),
    });

    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');

    fireEvent.change(screen.getByLabelText('Instruktion till AI-partnern'), {
      target: { value: 'Skriv om avgiften' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka' }));

    expect(await screen.findByText('Ingenting skrevs')).toBeInTheDocument();
    expect(screen.getByText(/finns inte i föreningens dokument/)).toBeInTheDocument();
  });

  it('visar källan till en AI-ändring och öppnar den via den vanliga källvägen', async () => {
    const citation = {
      document_id: 'doc-1', document_name: 'Stadgar.pdf', page: 4, quote: 'Citatet',
    };
    websiteApi.ai.mockResolvedValue({
      applied: true,
      message: 'Jag skrev från stadgarna.',
      transaction: { id: 'tx-source', summary: 'Ur stadgarna', operation_count: 1 },
      sources: [citation],
      workspace: workspace(),
    });
    const onOpenCitation = vi.fn();
    render(<Website brfId="brf-1" isAdmin onOpenCitation={onOpenCitation} />);
    await screen.findByLabelText('Välj sida');

    fireEvent.change(screen.getByLabelText('Instruktion till AI-partnern'), {
      target: { value: 'Skriv utifrån stadgarna' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka' }));

    const source = await screen.findByRole('button', { name: /Stadgar\.pdf, s\. 4/ });
    fireEvent.click(source);
    expect(onOpenCitation).toHaveBeenCalledWith(citation);
  });

  it('skickar med vad som är markerat så att "detta" går att tolka', async () => {
    websiteApi.ai.mockResolvedValue({ applied: false, refusal: '', message: 'Klart.', workspace: workspace() });
    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');

    fireEvent.change(screen.getByLabelText('Instruktion till AI-partnern'), {
      target: { value: 'Korta den markerade texten' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Skicka' }));

    await waitFor(() => expect(websiteApi.ai).toHaveBeenCalled());
    const payload = websiteApi.ai.mock.calls[0][1];
    expect(payload).toMatchObject({
      instruction: 'Korta den markerade texten',
      page_id: 'page-1',
    });
    expect(payload).toHaveProperty('block_id');
    expect(payload).toHaveProperty('field');
    expect(payload).toHaveProperty('selected_text');
  });

  it('låter inte en medlem skriva instruktioner', async () => {
    render(<Website brfId="brf-1" isAdmin={false} />);
    await screen.findByLabelText('Välj sida');
    expect(screen.getByLabelText('Instruktion till AI-partnern')).toBeDisabled();
  });

  it('går att fälla ihop för att ge webbplatsen hela fönstret', async () => {
    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');

    fireEvent.click(screen.getByTitle('Dölj AI-partner'));
    expect(await screen.findByTitle('Visa AI-partner')).toBeInTheDocument();
    expect(screen.queryByLabelText('Instruktion till AI-partnern')).not.toBeInTheDocument();
  });
});

describe('Hemsidan — versioner', () => {
  it('listar tidigare versioner och erbjuder återställning av en annan än den publicerade', async () => {
    websiteApi.revisions.mockResolvedValue({
      page_id: 'page-1',
      current: 'rev-2',
      revisions: [
        { id: 'rev-2', page_id: 'page-1', seq: 2, title: 'Startsida', created_at: '2026-08-02T09:00:00+00:00', created_by: 'u1', note: '', block_count: 3, from_transaction: '' },
        { id: 'rev-1', page_id: 'page-1', seq: 1, title: 'Startsida', created_at: '2026-08-01T09:00:00+00:00', created_by: 'u1', note: 'Första', block_count: 2, from_transaction: '' },
      ],
    });

    render(<Website brfId="brf-1" isAdmin />);
    await screen.findByLabelText('Välj sida');
    fireEvent.click(screen.getByRole('button', { name: /Versioner/ }));

    expect(await screen.findByText('Tidigare versioner')).toBeInTheDocument();
    expect(screen.getByText(/Version 2/)).toBeInTheDocument();
    // The published one offers no rollback to itself.
    expect(screen.getAllByRole('button', { name: /Återställ/ })).toHaveLength(1);
  });
});
