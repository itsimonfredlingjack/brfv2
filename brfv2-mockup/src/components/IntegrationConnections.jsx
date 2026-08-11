import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, CheckCircle2, Copy, ExternalLink, Loader2, Mail, Plug, Receipt, Unplug,
} from 'lucide-react';
import { integrationsApi } from '../api';
import Tillstand from './Tillstand';
import './IntegrationConnections.css';

/**
 * Where an installation says which mailbox and which accounting company it may
 * read, and where a named administrator signs in to them.
 *
 * The two are deliberately two steps on the screen as well as in the API:
 * pointing the installation at someone's mailbox and signing in to it are
 * different decisions, often taken by different people on different days.
 *
 * Everything here is read access. The scopes and the hosts are printed from
 * the server's own answer rather than described in prose, because a sentence
 * about least privilege is worth nothing next to the list the code actually
 * asks for.
 */

const PROVIDER_LABEL = {
  'microsoft-graph': 'Microsoft 365 — brevlådan',
  fortnox: 'Fortnox — leverantörsfakturor',
};

const PROVIDER_ICON = {
  'microsoft-graph': Mail,
  fortnox: Receipt,
};

const STATUS_LABEL = {
  configured: 'Konfigurerad, ingen är inloggad',
  connected: 'Ansluten',
  expired: 'Inloggningen har gått ut',
  revoked: 'Bortkopplad',
  error: 'Senaste anropet misslyckades',
};

// A connection's standing, in the product's one vocabulary for standing.
//
// These were coloured pills — a green one, an amber one, a red one — which is
// the two attempts Tillstand.jsx records as already failed, still running on
// the one screen the consolidation missed. Shape carries it everywhere else,
// so it carries it here: filled means it works, a solid outline means it was
// set up and does not, a dashed outline means nothing establishes it yet, and
// the one colour stays for the one thing this product paints red.
//
// `avviker` is the fifth form and it is not a new variant: a mailbox that is
// configured but has nobody signed into it is precisely "checked, and it does
// not hold" — the same reading as an invoice that disagrees with its contract.
const STATUS_FORM = {
  connected: 'belagd',
  configured: 'avviker',
  expired: 'avviker',
  revoked: 'oprovad',
  error: 'fel',
};

const NAMED_AUTHORITIES = ['consumers', 'organizations', 'common'];

const AUTHORITY_LABEL = {
  consumers: 'consumers — personliga Microsoft-konton',
  organizations: 'organizations — arbets- eller skolkonton',
  common: 'common — båda sorterna',
};

const formatMoment = (iso) => {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString('sv-SE', { dateStyle: 'medium', timeStyle: 'short' });
};

const countdown = (seconds) => {
  const left = Math.max(0, seconds);
  return `${Math.floor(left / 60)} min ${String(left % 60).padStart(2, '0')} s`;
};

function ScopesAndHosts({ scopes, hosts }) {
  return (
    <div className="ic-limits">
      <div>
        <h5>Behörigheter som begärs</h5>
        <ul>{scopes.map((scope) => <li key={scope}><code>{scope}</code></li>)}</ul>
      </div>
      <div>
        <h5>Adresser produkten får nå</h5>
        <ul>{hosts.map((host) => <li key={host}><code>{host}</code></li>)}</ul>
      </div>
    </div>
  );
}

/**
 * A device-code sign-in in progress: the code to type, where to type it, and
 * the polling that notices when it has been typed.
 *
 * The callbacks are held in a ref rather than in the effect's dependency list
 * so a parent re-render — a banner appearing, the clock ticking — cannot
 * restart the poll timer and turn one sign-in into a request storm.
 */
function DeviceLogin({ brfId, provider, pending, onConnected, onFailed, onExpired }) {
  const [remaining, setRemaining] = useState(pending.expiresInS);
  const [copied, setCopied] = useState(false);
  const handlers = useRef({ onConnected, onFailed, onExpired });
  handlers.current = { onConnected, onFailed, onExpired };

  useEffect(() => {
    const deadline = Date.now() + pending.expiresInS * 1000;
    const id = setInterval(() => {
      const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setRemaining(left);
      if (left <= 0) handlers.current.onExpired();
    }, 1000);
    return () => clearInterval(id);
  }, [pending.id, pending.expiresInS]);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    // The interval the authority asked for, never faster: polling a device-code
    // endpoint too eagerly is answered with slow_down, not with a token.
    const wait = Math.max(3, pending.intervalS || 5) * 1000;
    const tick = async () => {
      try {
        const result = await integrationsApi.pollLogin(brfId, provider);
        if (cancelled) return;
        if (result?.status === 'connected') {
          handlers.current.onConnected(result.connection);
          return;
        }
      } catch (err) {
        if (!cancelled) handlers.current.onFailed(err);
        return;
      }
      if (!cancelled) timer = setTimeout(tick, wait);
    };
    timer = setTimeout(tick, wait);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [brfId, provider, pending.id, pending.intervalS]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(pending.userCode);
      setCopied(true);
    } catch {
      // A clipboard the browser will not give us is not worth a banner — the
      // code is on screen in full and can be typed. Saying "Kopierad" anyway
      // would be the one thing that could actually cost the operator a sign-in.
      setCopied(false);
    }
  };

  return (
    <div className="ic-device" role="status">
      <p>
        Öppna{' '}
        <a href={pending.verificationUri} target="_blank" rel="noreferrer">
          {pending.verificationUri} <ExternalLink size={13} />
        </a>{' '}
        i webbläsaren, logga in med det konto som äger brevlådan och skriv koden:
      </p>
      <p className="ic-usercode">
        <code>{pending.userCode}</code>
        <button type="button" onClick={copy}>
          <Copy size={14} /> {copied ? 'Kopierad' : 'Kopiera'}
        </button>
      </p>
      <p className="ic-hint">
        Koden gäller i {countdown(remaining)}. Den här sidan frågar själv om du
        blivit klar — lämna den öppen.
      </p>
    </div>
  );
}

/** A redirect-code sign-in: the operator brings the code back by hand. */
function CodeLogin({ pending, busy, onComplete }) {
  const [pasted, setPasted] = useState('');
  return (
    <div className="ic-device" role="status">
      <p>
        Öppna{' '}
        <a href={pending.authorizeUrl} target="_blank" rel="noreferrer">
          godkännandesidan hos Fortnox <ExternalLink size={13} />
        </a>{' '}
        och godkänn läsningen. Du skickas sedan vidare till en adress som inte
        finns — det är väntat.
      </p>
      <label className="ic-field">
        <span>Klistra in koden, eller hela adressen du hamnade på</span>
        <input
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="https://…/callback?code=…&state=…"
        />
      </label>
      <div className="ic-actions">
        <button
          type="button"
          className="ic-primary"
          disabled={busy || !pasted.trim()}
          onClick={() => onComplete(pasted.trim())}
        >
          {busy ? <><Loader2 size={15} className="spin" /> Slutför…</> : 'Slutför inloggningen'}
        </button>
      </div>
    </div>
  );
}

function GraphForm({ connection, mailFolders, busy, onSave }) {
  const initialAuthority = connection?.authority || 'consumers';
  const [clientId, setClientId] = useState(connection?.client_id || '');
  const [authorityKind, setAuthorityKind] = useState(
    NAMED_AUTHORITIES.includes(initialAuthority) ? initialAuthority : 'tenant',
  );
  const [tenantId, setTenantId] = useState(
    NAMED_AUTHORITIES.includes(initialAuthority) ? '' : initialAuthority,
  );
  const [mailbox, setMailbox] = useState(connection?.mailbox || '');
  const [folder, setFolder] = useState(connection?.folder || 'inbox');

  const authority = authorityKind === 'tenant' ? tenantId.trim() : authorityKind;
  const folders = mailFolders?.length ? mailFolders : ['inbox'];

  return (
    <div className="ic-form">
      <div className="ic-grid">
        <label className="ic-field ic-span">
          <span>App-id (klient-id) för appregistreringen</span>
          <input
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            disabled={busy}
          />
          <small>
            Registreringen görs i Azure av den som förvaltar föreningens
            Microsoft-konto. Produkten är en publik klient utan hemlighet.
          </small>
        </label>
        <label className="ic-field">
          <span>Vilka konton som får logga in</span>
          <select
            value={authorityKind}
            onChange={(e) => setAuthorityKind(e.target.value)}
            disabled={busy}
          >
            {NAMED_AUTHORITIES.map((value) => (
              <option key={value} value={value}>{AUTHORITY_LABEL[value]}</option>
            ))}
            <option value="tenant">en bestämd katalog (GUID)</option>
          </select>
        </label>
        {authorityKind === 'tenant' && (
          <label className="ic-field">
            <span>Katalogens id</span>
            <input
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              disabled={busy}
            />
          </label>
        )}
        <label className="ic-field">
          <span>Brevlåda</span>
          <input
            value={mailbox}
            onChange={(e) => setMailbox(e.target.value)}
            placeholder="styrelsen@forening.se"
            disabled={busy}
          />
          <small>
            Lämnas fältet tomt läses det inloggade kontots egen brevlåda. Anges
            en adress läses den delade brevlådan, och behörigheten
            <code>Mail.Read.Shared</code> begärs — fortfarande bara läsning.
          </small>
        </label>
        <label className="ic-field">
          <span>Mapp</span>
          <select value={folder} onChange={(e) => setFolder(e.target.value)} disabled={busy}>
            {folders.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      <div className="ic-actions">
        <button
          type="button"
          className="ic-primary"
          disabled={busy || !clientId.trim() || !authority}
          onClick={() => onSave({
            client_id: clientId.trim(),
            authority,
            mailbox: mailbox.trim(),
            folder,
          })}
        >
          {busy ? <><Loader2 size={15} className="spin" /> Sparar…</> : 'Spara konfigurationen'}
        </button>
      </div>
    </div>
  );
}

function FortnoxForm({ connection, busy, onSave }) {
  const [clientId, setClientId] = useState(connection?.client_id || '');
  const [clientSecret, setClientSecret] = useState('');
  const [redirectUri, setRedirectUri] = useState(connection?.redirect_uri || '');
  const [readRegister, setReadRegister] = useState(Boolean(connection?.read_supplier_register));

  return (
    <div className="ic-form">
      <div className="ic-grid">
        <label className="ic-field">
          <span>Klient-id</span>
          <input value={clientId} onChange={(e) => setClientId(e.target.value)} disabled={busy} />
        </label>
        <label className="ic-field">
          <span>Klienthemlighet</span>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={connection?.client_id ? '•••••••• (sparad)' : 'Från integrationen i Fortnox'}
            disabled={busy}
          />
          <small>Sparas bara på den här datorn och visas aldrig igen.</small>
        </label>
        <label className="ic-field ic-span">
          <span>Återanropsadress (redirect URI)</span>
          <input
            value={redirectUri}
            onChange={(e) => setRedirectUri(e.target.value)}
            placeholder="https://localhost/fortnox/callback"
            disabled={busy}
          />
          <small>Exakt samma adress som står i integrationen hos Fortnox.</small>
        </label>
      </div>

      <label className="ic-check">
        <input
          type="checkbox"
          checked={readRegister}
          onChange={(e) => setReadRegister(e.target.checked)}
          disabled={busy}
        />
        <span>
          <strong>Läs även leverantörsregistret</strong>
          <small>
            Ger läsrätt till hela leverantörsregistret, inte bara fakturorna. Det
            köper en säkrare koppling: granskningen kan ankras på
            organisationsnummer, som är entydigt där ett namn inte är det. Lämnas
            rutan tom läses bara leverantörsfakturorna, och kopplingen görs på
            namn.
          </small>
        </span>
      </label>

      <div className="ic-actions">
        <button
          type="button"
          className="ic-primary"
          disabled={busy || !clientId.trim() || !redirectUri.trim()}
          onClick={() => onSave({
            client_id: clientId.trim(),
            client_secret: clientSecret,
            redirect_uri: redirectUri.trim(),
            read_supplier_register: readRegister,
          })}
        >
          {busy ? <><Loader2 size={15} className="spin" /> Sparar…</> : 'Spara konfigurationen'}
        </button>
      </div>
    </div>
  );
}

export default function IntegrationConnections({ brfId, connections, mailFolders, onChanged }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [started, setStarted] = useState({});
  const [confirming, setConfirming] = useState('');

  const run = async (key, action, success) => {
    setBusy(key);
    setError('');
    setNotice('');
    try {
      const result = await action();
      if (success) setNotice(success);
      await onChanged();
      return result;
    } catch (err) {
      setError(err.message || 'Anropet gick inte igenom.');
      return null;
    } finally {
      setBusy('');
    }
  };

  const beginLogin = (provider) => run(`login:${provider}`, async () => {
    const pending = await integrationsApi.beginLogin(brfId, provider);
    setStarted((current) => ({ ...current, [provider]: pending }));
    return pending;
  });

  const completeLogin = (provider, pasted) => run(
    `complete:${provider}`,
    async () => {
      const result = await integrationsApi.completeLogin(brfId, provider, pasted);
      setStarted((current) => ({ ...current, [provider]: null }));
      return result;
    },
    'Anslutningen är klar.',
  );

  const disconnect = (provider) => run(
    `disconnect:${provider}`,
    async () => {
      const result = await integrationsApi.disconnect(brfId, provider);
      setStarted((current) => ({ ...current, [provider]: null }));
      setConfirming('');
      return result;
    },
    'Inloggningen är glömd. Allt som redan importerats ligger kvar.',
  );

  const onConnected = useCallback((provider) => async () => {
    setStarted((current) => ({ ...current, [provider]: null }));
    setNotice(`${PROVIDER_LABEL[provider]} är ansluten.`);
    await onChanged();
  }, [onChanged]);

  const onFailed = useCallback((provider) => (err) => {
    setStarted((current) => ({ ...current, [provider]: null }));
    setError(err.message || 'Inloggningen gick inte igenom.');
  }, []);

  const onExpired = useCallback((provider) => () => {
    setStarted((current) => ({ ...current, [provider]: null }));
    setError('Koden hann gå ut. Starta inloggningen igen.');
  }, []);

  const providers = Object.keys(connections || {});

  return (
    <section className="ic">
      <div className="pane-intro">
        <p>
          Här bestäms vad den här installationen får läsa, och vem som har loggat
          in för att den ska få det. Båda stegen är egna beslut: att peka ut en
          brevlåda är inte samma sak som att logga in i den.
        </p>
        <p>
          Allt som går att göra härifrån är läsning. Produkten kan inte skicka,
          svara, vidarebefordra, flytta, markera eller radera något i de system
          den läser — det finns ingen kodväg som skriver utåt.
        </p>
      </div>

      {error && <div className="ic-banner bad" role="alert"><AlertCircle size={15} /> {error}</div>}
      {notice && <div className="ic-banner ok" role="status"><CheckCircle2 size={15} /> {notice}</div>}

      {providers.map((provider) => {
        const entry = connections[provider];
        const connection = entry.connection;
        const pending = started[provider] || entry.pendingLogin;
        const status = connection?.status || null;
        const Icon = PROVIDER_ICON[provider] || Plug;
        return (
          <article key={provider} className="ic-provider">
            <header className="ic-head">
              <h4><Icon size={16} /> {PROVIDER_LABEL[provider] || provider}</h4>
              <Tillstand form={status ? STATUS_FORM[status] : 'oprovad'}>
                {status ? STATUS_LABEL[status] || status : 'Inte konfigurerad'}
              </Tillstand>
            </header>

            <div className="ic-step">
              <h5>Steg 1 — konfigurera</h5>
              {provider === 'microsoft-graph' ? (
                <GraphForm
                  connection={connection}
                  mailFolders={mailFolders}
                  busy={busy === 'config:microsoft-graph'}
                  onSave={(config) => run(
                    'config:microsoft-graph',
                    () => integrationsApi.configureGraph(brfId, config),
                    'Konfigurationen är sparad. Nästa steg är att logga in.',
                  )}
                />
              ) : (
                <FortnoxForm
                  connection={connection}
                  busy={busy === 'config:fortnox'}
                  onSave={(config) => run(
                    'config:fortnox',
                    () => integrationsApi.configureFortnox(brfId, config),
                    'Konfigurationen är sparad. Nästa steg är att logga in.',
                  )}
                />
              )}
            </div>

            <div className="ic-step">
              <h5>Steg 2 — logga in</h5>
              {!entry.configured && (
                <p className="ic-hint">Konfigurera först — det finns ingenting att logga in mot ännu.</p>
              )}

              {entry.configured && status === 'connected' && (
                <dl className="ic-facts">
                  <div>
                    <dt>Konto</dt>
                    <dd>{connection.account_label || '—'}</dd>
                  </div>
                  <div>
                    <dt>Ansluten av</dt>
                    <dd>{connection.connected_by || '—'} · {formatMoment(connection.connected_at)}</dd>
                  </div>
                  <div>
                    <dt>Beviljade behörigheter</dt>
                    <dd>
                      {connection.granted_scopes?.length
                        ? connection.granted_scopes.map((s) => <code key={s}>{s}</code>)
                        : 'Ingen lista lämnades av leverantören.'}
                    </dd>
                  </div>
                  <div>
                    <dt>Senast använd</dt>
                    <dd>{formatMoment(connection.last_used_at)}</dd>
                  </div>
                </dl>
              )}

              {connection?.last_error && (
                <p className="ic-lasterror">Senaste felet: {connection.last_error}</p>
              )}

              {entry.configured && pending && entry.loginKind === 'device' && (
                <DeviceLogin
                  brfId={brfId}
                  provider={provider}
                  pending={pending}
                  onConnected={onConnected(provider)}
                  onFailed={onFailed(provider)}
                  onExpired={onExpired(provider)}
                />
              )}

              {entry.configured && pending && entry.loginKind === 'code' && (
                <CodeLogin
                  pending={pending}
                  busy={busy === `complete:${provider}`}
                  onComplete={(pasted) => completeLogin(provider, pasted)}
                />
              )}

              {entry.configured && !pending && (
                <div className="ic-actions">
                  <button
                    type="button"
                    className="ic-primary"
                    disabled={busy === `login:${provider}`}
                    onClick={() => beginLogin(provider)}
                  >
                    {busy === `login:${provider}`
                      ? <><Loader2 size={15} className="spin" /> Startar…</>
                      : <><Plug size={15} /> {status === 'connected' ? 'Logga in igen' : 'Logga in'}</>}
                  </button>
                  {status === 'connected' && (
                    <button
                      type="button"
                      className="ic-secondary danger"
                      onClick={() => setConfirming(provider)}
                    >
                      <Unplug size={15} /> Koppla bort
                    </button>
                  )}
                </div>
              )}

              {confirming === provider && (
                <div className="ic-confirm" role="alertdialog" aria-label="Bekräfta bortkoppling">
                  <p>
                    Koppla bort {PROVIDER_LABEL[provider]}? Inloggningen glöms och
                    produkten läser ingenting mer därifrån.{' '}
                    <strong>
                      Allt som redan importerats — meddelanden, bilagor, fakturor
                      och fynd — ligger kvar oförändrat.
                    </strong>
                  </p>
                  <div className="ic-actions">
                    <button type="button" className="ic-secondary" onClick={() => setConfirming('')}>
                      Avbryt
                    </button>
                    <button
                      type="button"
                      className="ic-primary danger"
                      disabled={busy === `disconnect:${provider}`}
                      onClick={() => disconnect(provider)}
                    >
                      Ja, koppla bort
                    </button>
                  </div>
                </div>
              )}
            </div>

            <ScopesAndHosts scopes={entry.scopes || []} hosts={entry.hosts || []} />
          </article>
        );
      })}
    </section>
  );
}
