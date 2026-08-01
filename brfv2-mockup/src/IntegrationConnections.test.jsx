import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import IntegrationConnections from './components/IntegrationConnections';
import { integrationsApi } from './api';

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: {
    connections: vi.fn(),
    configureGraph: vi.fn(),
    configureFortnox: vi.fn(),
    beginLogin: vi.fn(),
    pollLogin: vi.fn(),
    completeLogin: vi.fn(),
    disconnect: vi.fn(),
  },
}));

const GRAPH_SCOPES = ['offline_access', 'User.Read', 'Mail.Read'];
const GRAPH_HOSTS = ['graph.microsoft.com', 'login.microsoftonline.com'];

const graphEntry = (overrides = {}) => ({
  provider: 'microsoft-graph',
  configured: false,
  connection: null,
  pendingLogin: null,
  loginKind: 'device',
  scopes: GRAPH_SCOPES,
  hosts: GRAPH_HOSTS,
  ...overrides,
});

const fortnoxEntry = (overrides = {}) => ({
  provider: 'fortnox',
  configured: false,
  connection: null,
  pendingLogin: null,
  loginKind: 'code',
  scopes: ['supplierinvoice', 'companyinformation'],
  hosts: ['api.fortnox.se', 'apps.fortnox.se'],
  ...overrides,
});

const connection = (provider, status, extra = {}) => ({
  provider,
  tenant_id: 'brf-a',
  status,
  account_label: 'styrelsen@gjutformen12.example',
  granted_scopes: status === 'connected' ? GRAPH_SCOPES : [],
  client_id: '11111111-2222-3333-4444-555555555555',
  authority: 'organizations',
  mailbox: '',
  folder: 'inbox',
  redirect_uri: '',
  read_supplier_register: false,
  configured_by: 'user-1',
  configured_at: '2026-07-01T09:00:00+00:00',
  connected_by: status === 'connected' ? 'user-1' : '',
  connected_at: status === 'connected' ? '2026-07-01T09:05:00+00:00' : null,
  access_expires_at: null,
  last_used_at: null,
  last_error: null,
  ...extra,
});

const DEVICE_PENDING = {
  id: 'p1',
  provider: 'microsoft-graph',
  kind: 'device',
  userCode: 'HJQ7-2FRD',
  verificationUri: 'https://microsoft.com/devicelogin',
  authorizeUrl: '',
  expiresInS: 900,
  intervalS: 5,
};

const CODE_PENDING = {
  id: 'p2',
  provider: 'fortnox',
  kind: 'code',
  userCode: '',
  verificationUri: '',
  authorizeUrl: 'https://apps.fortnox.se/oauth-v1/auth?client_id=abc&state=xyz',
  expiresInS: 600,
  intervalS: 5,
};

function mount({ graph = graphEntry(), fortnox = fortnoxEntry() } = {}) {
  const onChanged = vi.fn();
  render(
    <IntegrationConnections
      brfId="brf-a"
      connections={{ 'microsoft-graph': graph, fortnox }}
      mailFolders={['inbox', 'archive', 'junkemail']}
      onChanged={onChanged}
    />,
  );
  return { onChanged };
}

/** Let every promise the click started run to the end, under fake timers. */
async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

const graphPanel = () => screen.getByText('Microsoft 365 — brevlådan').closest('.ic-provider');
const fortnoxPanel = () => screen.getByText('Fortnox — leverantörsfakturor').closest('.ic-provider');

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('what the connection will be allowed to do', () => {
  it('prints the scopes and the hosts from the server’s own answer', () => {
    mount();
    const graph = graphPanel();
    GRAPH_SCOPES.forEach((scope) => expect(within(graph).getByText(scope)).toBeInTheDocument());
    GRAPH_HOSTS.forEach((host) => expect(within(graph).getByText(host)).toBeInTheDocument());
    expect(within(graph).getByText('Behörigheter som begärs')).toBeInTheDocument();
    expect(within(graph).getByText('Adresser produkten får nå')).toBeInTheDocument();
  });

  it('names the supplier register as a trade-off rather than switching it on quietly', async () => {
    mount();
    const fortnox = fortnoxPanel();
    expect(within(fortnox).getByText('Läs även leverantörsregistret')).toBeInTheDocument();
    expect(within(fortnox).getByText(/hela leverantörsregistret/)).toBeInTheDocument();
    expect(within(fortnox).getByText(/organisationsnummer, som är entydigt/)).toBeInTheDocument();

    fireEvent.change(within(fortnox).getByLabelText('Klient-id'), { target: { value: 'fx-1' } });
    fireEvent.change(within(fortnox).getByLabelText(/^Klienthemlighet/), { target: { value: 's3cret' } });
    fireEvent.change(within(fortnox).getByLabelText(/^Återanropsadress/), {
      target: { value: 'https://localhost/fortnox/callback' },
    });
    fireEvent.click(within(fortnox).getByRole('checkbox'));

    integrationsApi.configureFortnox.mockResolvedValue(connection('fortnox', 'configured'));
    fireEvent.click(within(fortnox).getByRole('button', { name: 'Spara konfigurationen' }));
    await waitFor(() => expect(integrationsApi.configureFortnox).toHaveBeenCalledWith('brf-a', {
      client_id: 'fx-1',
      client_secret: 's3cret',
      redirect_uri: 'https://localhost/fortnox/callback',
      read_supplier_register: true,
    }));
  });
});

describe('configuring and signing in are two steps', () => {
  it('will not offer a sign-in before there is anything to sign in to', () => {
    mount();
    const graph = graphPanel();
    expect(within(graph).getByText('Steg 1 — konfigurera')).toBeInTheDocument();
    expect(within(graph).getByText('Steg 2 — logga in')).toBeInTheDocument();
    expect(within(graph).getByText(/Konfigurera först/)).toBeInTheDocument();
    expect(within(graph).queryByRole('button', { name: /Logga in/ })).toBeNull();
  });

  it('saves where to read without asking anyone to sign in', async () => {
    mount();
    const graph = graphPanel();
    fireEvent.change(within(graph).getByLabelText(/App-id/), { target: { value: 'app-1' } });
    fireEvent.change(within(graph).getByLabelText('Vilka konton som får logga in'), {
      target: { value: 'organizations' },
    });
    fireEvent.change(within(graph).getByLabelText(/^Brevlåda/), {
      target: { value: 'styrelsen@gjutformen12.example' },
    });
    fireEvent.change(within(graph).getByLabelText('Mapp'), { target: { value: 'archive' } });

    integrationsApi.configureGraph.mockResolvedValue(connection('microsoft-graph', 'configured'));
    fireEvent.click(within(graph).getByRole('button', { name: 'Spara konfigurationen' }));

    await waitFor(() => expect(integrationsApi.configureGraph).toHaveBeenCalledWith('brf-a', {
      client_id: 'app-1',
      authority: 'organizations',
      mailbox: 'styrelsen@gjutformen12.example',
      folder: 'archive',
    }));
    expect(integrationsApi.beginLogin).not.toHaveBeenCalled();
  });
});

describe('the device-code sign-in', () => {
  const configured = () => mount({
    graph: graphEntry({
      configured: true,
      connection: connection('microsoft-graph', 'configured'),
    }),
  });

  it('shows the code, links where to type it, and stops polling once connected', async () => {
    vi.useFakeTimers();
    const { onChanged } = configured();

    integrationsApi.beginLogin.mockResolvedValue(DEVICE_PENDING);
    fireEvent.click(within(graphPanel()).getByRole('button', { name: 'Logga in' }));
    await settle();

    expect(screen.getByText('HJQ7-2FRD')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /devicelogin/ }))
      .toHaveAttribute('href', 'https://microsoft.com/devicelogin');
    expect(screen.getByText(/Koden gäller i 15 min/)).toBeInTheDocument();

    integrationsApi.pollLogin
      .mockResolvedValueOnce({ status: 'pending' })
      .mockResolvedValueOnce({
        status: 'connected',
        connection: connection('microsoft-graph', 'connected'),
      });

    // Nothing is asked before the interval the authority asked for.
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(integrationsApi.pollLogin).not.toHaveBeenCalled();

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(integrationsApi.pollLogin).toHaveBeenCalledTimes(1);
    expect(integrationsApi.pollLogin).toHaveBeenCalledWith('brf-a', 'microsoft-graph');
    expect(screen.getByText('HJQ7-2FRD')).toBeInTheDocument();

    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(integrationsApi.pollLogin).toHaveBeenCalledTimes(2);
    expect(onChanged).toHaveBeenCalled();
    expect(screen.queryByText('HJQ7-2FRD')).toBeNull();

    // The loop is over, not merely quiet: two minutes later it is still two.
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); });
    expect(integrationsApi.pollLogin).toHaveBeenCalledTimes(2);
  });

  it('gives up when the code expires instead of polling a dead login', async () => {
    vi.useFakeTimers();
    configured();
    integrationsApi.beginLogin.mockResolvedValue({ ...DEVICE_PENDING, expiresInS: 10 });
    integrationsApi.pollLogin.mockResolvedValue({ status: 'pending' });
    fireEvent.click(within(graphPanel()).getByRole('button', { name: 'Logga in' }));
    await settle();

    await act(async () => { await vi.advanceTimersByTimeAsync(11000); });
    expect(screen.queryByText('HJQ7-2FRD')).toBeNull();
    expect(screen.getByRole('alert')).toHaveTextContent(/Koden hann gå ut/);

    const polls = integrationsApi.pollLogin.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(integrationsApi.pollLogin).toHaveBeenCalledTimes(polls);
  });
});

describe('the pasted-code sign-in', () => {
  it('takes the whole redirect address as readily as the bare code', async () => {
    mount({
      fortnox: fortnoxEntry({
        configured: true,
        connection: connection('fortnox', 'configured'),
        pendingLogin: CODE_PENDING,
      }),
    });

    const fortnox = fortnoxPanel();
    expect(within(fortnox).getByRole('link', { name: /godkännandesidan/ }))
      .toHaveAttribute('href', CODE_PENDING.authorizeUrl);

    fireEvent.change(
      within(fortnox).getByLabelText('Klistra in koden, eller hela adressen du hamnade på'),
      { target: { value: 'https://localhost/fortnox/callback?code=abc123&state=xyz' } },
    );
    integrationsApi.completeLogin.mockResolvedValue({
      status: 'connected',
      connection: connection('fortnox', 'connected'),
    });
    fireEvent.click(within(fortnox).getByRole('button', { name: 'Slutför inloggningen' }));

    await waitFor(() => expect(integrationsApi.completeLogin).toHaveBeenCalledWith(
      'brf-a', 'fortnox', 'https://localhost/fortnox/callback?code=abc123&state=xyz',
    ));
  });
});

describe('disconnecting', () => {
  const connected = () => mount({
    graph: graphEntry({
      configured: true,
      connection: connection('microsoft-graph', 'connected'),
    }),
  });

  it('asks first, and says plainly that imported material stays', async () => {
    connected();
    fireEvent.click(screen.getByRole('button', { name: /Koppla bort/ }));
    expect(integrationsApi.disconnect).not.toHaveBeenCalled();

    const dialog = screen.getByRole('alertdialog', { name: 'Bekräfta bortkoppling' });
    expect(within(dialog).getByText(/ligger kvar oförändrat/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Avbryt' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(integrationsApi.disconnect).not.toHaveBeenCalled();
  });

  it('disconnects only after the confirmation is given', async () => {
    const { onChanged } = connected();
    fireEvent.click(screen.getByRole('button', { name: /Koppla bort/ }));
    integrationsApi.disconnect.mockResolvedValue({
      disconnected: 'microsoft-graph',
      hadCredentials: true,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ja, koppla bort' }));

    await waitFor(() => expect(integrationsApi.disconnect)
      .toHaveBeenCalledWith('brf-a', 'microsoft-graph'));
    expect(onChanged).toHaveBeenCalled();
    expect(await screen.findByText(/Allt som redan importerats ligger kvar/)).toBeInTheDocument();
  });
});
