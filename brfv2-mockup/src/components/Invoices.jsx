import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  Download,
  Loader2,
  Receipt,
  RefreshCw,
  Search,
  Table2,
  User,
  X,
} from 'lucide-react';
import { integrationsApi, invoicesApi } from '../api';
import InvoiceCase from './InvoiceCase';
import { formatAmount } from './money';
import MappingPreview from './MappingPreview';
import './Invoices.css';

/**
 * Fakturor — the board's own invoice review, as an operational queue.
 *
 * This is decision support, not an accounting system. Everything on this screen
 * is read out of systems the association already has, compared against material
 * the association already owns, and settled by a person here. Two consequences
 * are visible in every row:
 *
 * 1. **Two statuses, never merged.** What the accounting system says about its
 *    own record sits in its own column, and what this association decided sits
 *    in another. Nothing in this product changes the first, and no control here
 *    is called "godkänn faktura" — there is no approval to give.
 * 2. **A signal is a reading, not a verdict.** The column says what was noticed
 *    and the case says what it was read from. A row never asserts more than the
 *    finding behind it does.
 */

const SIGNAL_ICON = {
  possible_duplicate: AlertTriangle,
  overdue: CalendarClock,
  due_soon: CalendarClock,
  price_change: AlertTriangle,
  missing_contract: AlertTriangle,
  unresolved_supplier: Building2,
  new_line: AlertTriangle,
  open_question: AlertTriangle,
  credit_relation: Receipt,
  no_deviation_found: CheckCircle2,
};

const SOURCE_LABEL = {
  fixture: 'Syntetiskt underlag',
  fortnox: 'Fortnox',
};

const OBSERVATION_SHORT = {
  accounting_snapshot: 'Ekonomisystem',
  email: 'E-post',
  document: 'Fil',
};

const SORTS = {
  activity: { label: 'Senaste aktivitet', compare: (a, b) => (b.last_activity_at || '').localeCompare(a.last_activity_at || '') },
  due: {
    label: 'Förfallodatum',
    compare: (a, b) => (a.due_date || '9999-12-31').localeCompare(b.due_date || '9999-12-31'),
  },
  amount: {
    label: 'Belopp',
    compare: (a, b) => Number(b.total_amount || 0) - Number(a.total_amount || 0),
  },
  supplier: { label: 'Leverantör', compare: (a, b) => (a.supplier_name || '').localeCompare(b.supplier_name || '', 'sv') },
};

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`invoices-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

function SignalChip({ signal }) {
  if (!signal) return <span className="signal-chip none">—</span>;
  const Icon = SIGNAL_ICON[signal.kind] || AlertTriangle;
  return (
    <span className={`signal-chip ${signal.severity}`} title={signal.detail}>
      <Icon size={12} /> {signal.label}
    </span>
  );
}

/**
 * Reading an invoice in.
 *
 * The source is named in the request and never inferred from what happens to be
 * connected, so a demo read and a live read cannot be confused for one another
 * in a screenshot. Looking at the list stores nothing.
 */
function ReadInPanel({
  brfId, sources, fortnoxReady, known, busy, source, onSource, onImport, onCheckFields,
}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    integrationsApi.availableInvoices(brfId, source)
      .then((body) => { if (!cancelled) { setRows(body.invoices || []); setError(''); } })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        // Kept apart from the queue: a live source that is down or signed out
        // must not blank the cases that are stored locally and readable.
        setError(err.message || 'Fakturakällan svarade inte.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [brfId, source]);

  return (
    <details className="invoices-read-in">
      <summary><Download size={14} /> Läs in fakturor</summary>
      <p className="muted">
        Fakturor läses <strong>read-only</strong>. Appen kan inte bokföra, kontera, attestera,
        betala eller ändra någon status i ett ekonomisystem — det finns ingen kodväg som
        skriver utåt.
      </p>
      <div className="source-picker" role="radiogroup" aria-label="Fakturakälla">
        {sources.map((name) => {
          const disabled = name === 'fortnox' && !fortnoxReady;
          return (
            <label key={name} className={disabled ? 'disabled' : ''}>
              <input
                type="radio"
                name="invoice-source"
                value={name}
                checked={source === name}
                disabled={disabled}
                onChange={() => onSource(name)}
              />
              {SOURCE_LABEL[name] || name}
              {disabled && <span className="muted"> (inte ansluten)</span>}
            </label>
          );
        })}
      </div>

      {error && <p className="invoices-source-error" role="alert">{error}</p>}
      {loading && <p className="muted"><Loader2 size={13} className="spin" /> Hämtar…</p>}

      {rows.length > 0 && (
        <table className="invoices-available">
          <thead>
            <tr>
              <th>Referens</th><th>Leverantör</th><th>Datum</th><th>Belopp</th>
              {source === 'fortnox' && <><th>Bokförd</th><th>Annullerad</th></>}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.external_ref}>
                <td><code>{row.external_ref}</code></td>
                <td>{row.supplier_name}</td>
                <td>{row.invoice_date || '—'}</td>
                <td>{formatAmount(row.total_amount, row.currency)}</td>
                {source === 'fortnox' && (
                  <>
                    <td>{row.booked ? 'ja' : 'nej'}</td>
                    <td>{row.cancelled ? 'ja' : 'nej'}</td>
                  </>
                )}
                <td className="available-actions">
                  <button type="button" disabled={busy} onClick={() => onImport(row.external_ref)}>
                    {known.has(row.external_ref) ? 'Läs om och granska' : 'Läs in och granska'}
                  </button>
                  {source === 'fortnox' && (
                    <button type="button" className="secondary" onClick={() => onCheckFields(row.external_ref)}>
                      Kontrollera fälten
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && rows.length === 0 && !error && (
        <p className="muted">Källan har inga fakturor att erbjuda för den här föreningen.</p>
      )}
    </details>
  );
}

export default function Invoices({ brfId, isAdmin = false, onOpenDocument, onOpenCitation }) {
  const [pane, setPane] = useState('queue');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [selected, setSelected] = useState(null);
  const [source, setSource] = useState('fixture');
  const [mappingRef, setMappingRef] = useState('');
  const [connections, setConnections] = useState(null);

  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('open');
  const [signalFilter, setSignalFilter] = useState('all');
  const [responsibleFilter, setResponsibleFilter] = useState('all');
  const [sort, setSort] = useState('activity');

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      const body = await invoicesApi.workspace(brfId);
      setData(body);
      setError('');
    } catch (err) {
      setError(err.message || 'Fakturakön kunde inte hämtas.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    integrationsApi.connections(brfId)
      .then((body) => { if (!cancelled) setConnections(body); })
      .catch(() => { if (!cancelled) setConnections(null); });
    return () => { cancelled = true; };
  }, [brfId]);

  const fortnoxReady = connections?.fortnox?.connection?.status === 'connected';

  useEffect(() => {
    // An option that always answers 409 is not a choice.
    if (source === 'fortnox' && connections && !fortnoxReady) setSource('fixture');
    if (pane === 'mapping' && connections && !fortnoxReady) setPane('queue');
  }, [source, pane, connections, fortnoxReady]);

  const cases = useMemo(() => data?.cases || [], [data]);
  const known = useMemo(
    () => new Set(
      cases.flatMap((c) => c.observations
        .filter((o) => o.kind === 'accounting_snapshot')
        .map((o) => o.external_ref)),
    ),
    [cases],
  );

  const signalKinds = useMemo(() => {
    const kinds = new Map();
    cases.forEach((c) => (c.signals || []).forEach((s) => kinds.set(s.kind, s.label)));
    return [...kinds.entries()];
  }, [cases]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = cases.filter((c) => {
      if (statusFilter === 'open' && !c.open) return false;
      if (statusFilter === 'settled' && c.open) return false;
      if (statusFilter !== 'all' && statusFilter !== 'open' && statusFilter !== 'settled'
        && c.review_status !== statusFilter) return false;
      if (signalFilter !== 'all' && !(c.signals || []).some((s) => s.kind === signalFilter)) return false;
      if (responsibleFilter === 'unassigned' && c.responsible) return false;
      if (responsibleFilter !== 'all' && responsibleFilter !== 'unassigned'
        && c.responsible !== responsibleFilter) return false;
      if (!needle) return true;
      return [c.supplier_name, c.invoice_number, c.supplier_ref, c.responsible]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle));
    });
    return [...rows].sort(SORTS[sort].compare);
  }, [cases, query, statusFilter, signalFilter, responsibleFilter, sort]);

  const counts = data?.counts || {};
  const labels = data?.labels;

  async function importInvoice(externalRef) {
    setBusy(true);
    setError('');
    try {
      const created = await invoicesApi.importInvoice(brfId, externalRef, source);
      setNotice(
        `Faktura ${created.invoice_number || externalRef} inläst och granskad. `
        + 'Ingenting ändrades i ekonomisystemet.',
      );
      await refresh();
      setSelected(created.id);
    } catch (err) {
      setError(err.message || 'Fakturan kunde inte läsas in.');
    } finally {
      setBusy(false);
    }
  }

  if (selected) {
    return (
      <div className="invoices">
        <InvoiceCase
          brfId={brfId}
          caseId={selected}
          isAdmin={isAdmin}
          onBack={() => { setSelected(null); refresh(); }}
          onOpenCitation={onOpenCitation}
          onOpenDocument={onOpenDocument}
          onOpenCase={(id) => setSelected(id)}
          onChanged={refresh}
        />
      </div>
    );
  }

  return (
    <div className="invoices">
      <div className="invoices-intro">
        <h3><Receipt size={18} /> Fakturor</h3>
        <p>
          Varje faktura är ett ärende: vad den är, vad som ändrats, vad den stämmer mot,
          vad som saknas och vem som gör något åt det. Ingenting här ändrar något i
          ekonomisystemet — det finns ingen kodväg som skriver utåt.
        </p>
      </div>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      <div className="invoices-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={pane === 'queue'}
          className={pane === 'queue' ? 'active' : ''}
          onClick={() => setPane('queue')}
        >
          <Receipt size={15} /> Granskningskö
          {counts.open > 0 && <span className="pill">{counts.open}</span>}
        </button>
        {fortnoxReady && (
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'mapping'}
            className={pane === 'mapping' ? 'active' : ''}
            onClick={() => setPane('mapping')}
          >
            <Table2 size={15} /> Fältkontroll
          </button>
        )}
        <button type="button" className="invoices-refresh" onClick={refresh} disabled={loading || busy}>
          <RefreshCw size={14} /> Uppdatera
        </button>
      </div>

      {pane === 'mapping' && fortnoxReady && (
        <MappingPreview brfId={brfId} initialRef={mappingRef} key={mappingRef} />
      )}

      {pane === 'queue' && (
        <>
          <dl className="invoices-counts">
            <div><dt>Att granska</dt><dd>{counts.open ?? 0}</dd></div>
            <div><dt>Med signal</dt><dd>{counts.withSignal ?? 0}</dd></div>
            <div><dt>Förfallna</dt><dd>{counts.overdue ?? 0}</dd></div>
            <div><dt>Utan ansvarig</dt><dd>{counts.unassigned ?? 0}</dd></div>
            <div>
              <dt>Öppet belopp</dt>
              <dd>{formatAmount(counts.amountOpen, 'SEK')}</dd>
            </div>
          </dl>

          {isAdmin && (
            <ReadInPanel
              brfId={brfId}
              sources={data?.sources || ['fixture']}
              fortnoxReady={fortnoxReady}
              known={known}
              busy={busy}
              source={source}
              onSource={setSource}
              onImport={importInvoice}
              onCheckFields={(ref) => { setMappingRef(ref); setPane('mapping'); }}
            />
          )}

          <div className="invoices-filters">
            <label className="invoices-search">
              <Search size={14} aria-hidden="true" />
              <input
                type="search"
                value={query}
                placeholder="Sök leverantör, fakturanummer, ansvarig…"
                aria-label="Sök i fakturakön"
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <label>
              <span>Läge</span>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filtrera på granskningsläge">
                <option value="open">Att granska</option>
                <option value="settled">Avslutade</option>
                <option value="all">Alla</option>
                {labels && Object.entries(labels.reviewStatus).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Signal</span>
              <select value={signalFilter} onChange={(e) => setSignalFilter(e.target.value)} aria-label="Filtrera på signal">
                <option value="all">Alla signaler</option>
                {signalKinds.map(([kind, label]) => (
                  <option key={kind} value={kind}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Ansvarig</span>
              <select value={responsibleFilter} onChange={(e) => setResponsibleFilter(e.target.value)} aria-label="Filtrera på ansvarig">
                <option value="all">Alla</option>
                <option value="unassigned">Ingen utsedd</option>
                {(data?.responsibles || []).map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Sortera</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sortera fakturakön">
                {Object.entries(SORTS).map(([key, value]) => (
                  <option key={key} value={key}>{value.label}</option>
                ))}
              </select>
            </label>
          </div>

          {loading && <p className="invoices-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>}

          {!loading && visible.length === 0 && (
            <p className="empty">
              {cases.length === 0
                ? 'Ingen faktura är inläst ännu. Läs in en ovan för att börja.'
                : 'Ingen faktura matchar filtret.'}
            </p>
          )}

          {!loading && visible.length > 0 && (
            <table className="invoices-queue">
              <thead>
                <tr>
                  <th>Faktura</th>
                  <th>Belopp</th>
                  <th>Förfaller</th>
                  <th>Källa</th>
                  <th>I ekonomisystemet</th>
                  <th>Vår granskning</th>
                  <th>Signal</th>
                  <th>Ansvarig</th>
                  <th>Senaste aktivitet</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.id} className={row.overdue ? 'overdue' : ''}>
                    <td>
                      <button type="button" className="case-link" onClick={() => setSelected(row.id)}>
                        <strong>{row.supplier_name || 'Okänd leverantör'}</strong>
                        <span className="muted">{row.invoice_number || row.case_key}</span>
                      </button>
                    </td>
                    <td className="numeric">{formatAmount(row.total_amount, row.currency)}</td>
                    <td>
                      {row.due_date || '—'}
                      {row.overdue && <span className="overdue-flag">förfallen</span>}
                    </td>
                    <td>
                      {row.observation_kinds.map((kind) => (
                        <span key={kind} className="source-badge">{OBSERVATION_SHORT[kind] || kind}</span>
                      ))}
                    </td>
                    <td className="muted">{row.source_status_label || 'ingen status'}</td>
                    <td><span className="review-badge">{row.review_status_label}</span></td>
                    <td><SignalChip signal={row.top_signal} /></td>
                    <td>
                      {row.responsible
                        ? <span className="responsible"><User size={12} /> {row.responsible}</span>
                        : <span className="muted">ej utsedd</span>}
                    </td>
                    <td className="muted">{(row.last_activity_at || '').slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
