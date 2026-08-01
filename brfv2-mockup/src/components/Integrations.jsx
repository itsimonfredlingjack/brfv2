import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  HelpCircle,
  Inbox,
  Loader2,
  Paperclip,
  Receipt,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { integrationsApi } from '../api';
import './Integrations.css';

/**
 * The board's incoming queue and the read-only invoice review.
 *
 * Two panes, one rule between them: nothing on this screen presents a system
 * proposal as an established fact. Verified facts, the proposal and the stated
 * uncertainty are three separate blocks with three different visual weights,
 * and a citation is always clickable through to the page it came from — a
 * finding whose evidence cannot be opened is an assertion, not a finding.
 */

const VERDICT_TONE = {
  matches: 'ok',
  possible_deviation: 'warn',
  cannot_be_verified: 'unknown',
};

const VERDICT_ICON = {
  matches: CheckCircle2,
  possible_deviation: AlertTriangle,
  cannot_be_verified: HelpCircle,
};

const STATUS_LABEL = {
  open: 'Öppen',
  approved: 'Godkänd',
  dismissed: 'Avfärdad',
  corrected: 'Korrigerad',
};

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('sv-SE', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatAmount(value, currency = 'SEK') {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (Number.isNaN(number)) return `${value} ${currency}`;
  return `${number.toLocaleString('sv-SE', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })} ${currency}`;
}

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`integrations-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

function DecisionBar({ status, busy, onDecide, requireNoteFor = [] }) {
  const [note, setNote] = useState('');
  const needsNote = requireNoteFor.length > 0;
  return (
    <div className="decision-bar">
      {needsNote && (
        <input
          type="text"
          className="decision-note"
          placeholder="Vad gäller i stället? (krävs för korrigering)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          aria-label="Beskriv korrigeringen"
        />
      )}
      <div className="decision-buttons">
        <button
          type="button"
          className="decision approve"
          disabled={busy}
          onClick={() => onDecide('approved', note.trim() || null)}
        >
          Godkänn
        </button>
        <button
          type="button"
          className="decision dismiss"
          disabled={busy}
          onClick={() => onDecide('dismissed', note.trim() || null)}
        >
          Avfärda
        </button>
        {needsNote && (
          <button
            type="button"
            className="decision correct"
            disabled={busy || !note.trim()}
            title={note.trim() ? undefined : 'Skriv vad som gäller i stället först.'}
            onClick={() => onDecide('corrected', note.trim())}
          >
            Korrigera
          </button>
        )}
        {status !== 'open' && (
          <button type="button" className="decision reopen" disabled={busy} onClick={() => onDecide('open', null)}>
            Öppna igen
          </button>
        )}
      </div>
    </div>
  );
}

function Citation({ citation, onOpen }) {
  return (
    <button
      type="button"
      className="finding-citation"
      onClick={() => onOpen(citation)}
      title={`Öppna ${citation.document_name} sida ${citation.page}`}
    >
      <FileText size={14} />
      <span className="citation-source">
        {citation.document_name} · s. {citation.page}
        {citation.approximate && <em className="citation-approx"> (markering ungefärlig)</em>}
      </span>
      <q className="citation-quote">{citation.quote}</q>
    </button>
  );
}

function Finding({ finding, busy, onDecide, onOpenCitation }) {
  const tone = VERDICT_TONE[finding.verdict] || 'unknown';
  const Icon = VERDICT_ICON[finding.verdict] || HelpCircle;
  const invoiceFacts = finding.verified_facts.filter((f) => f.source === 'invoice');
  const documentFacts = finding.verified_facts.filter((f) => f.source === 'document');

  return (
    <article className={`finding ${tone} ${finding.status !== 'open' ? 'decided' : ''}`}>
      <header className="finding-head">
        <span className={`verdict ${tone}`}>
          <Icon size={16} /> {finding.verdict_label}
        </span>
        <span className="finding-status">{STATUS_LABEL[finding.status] || finding.status}</span>
      </header>

      <div className="finding-facts">
        <div>
          <h5>Verifierat ur fakturan</h5>
          <dl>
            {invoiceFacts.map((fact, i) => (
              <div key={`i${i}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
            ))}
            {invoiceFacts.length === 0 && <div><dd className="muted">—</dd></div>}
          </dl>
        </div>
        <div>
          <h5>Verifierat ur dokumenten</h5>
          <dl>
            {documentFacts.map((fact, i) => (
              <div key={`d${i}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
            ))}
            {documentFacts.length === 0 && (
              <div><dd className="muted">Ingenting kunde verifieras ordagrant.</dd></div>
            )}
          </dl>
        </div>
      </div>

      {finding.citations.length > 0 && (
        <div className="finding-citations">
          <h5>Exakta citat</h5>
          {finding.citations.map((citation, i) => (
            <Citation key={i} citation={citation} onOpen={onOpenCitation} />
          ))}
        </div>
      )}

      <div className="finding-suggestion">
        <h5>Förslag <span className="suggested-by">({finding.suggested_by})</span></h5>
        <p>{finding.suggestion}</p>
      </div>

      {finding.uncertainty && (
        <div className="finding-uncertainty">
          <h5>Osäkerhet</h5>
          <p>{finding.uncertainty}</p>
        </div>
      )}

      {finding.decision_note && (
        <p className="finding-decision-note">Anteckning: {finding.decision_note}</p>
      )}

      <DecisionBar
        status={finding.status}
        busy={busy}
        onDecide={(status, note) => onDecide(finding.id, status, note)}
        requireNoteFor={['corrected']}
      />
    </article>
  );
}

export default function Integrations({ brfId, documents, onOpenDocument, onOpenCitation }) {
  const [pane, setPane] = useState('inbox');

  const [events, setEvents] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [available, setAvailable] = useState([]);
  const [findings, setFindings] = useState([]);
  const [format, setFormat] = useState(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const fileInput = useRef(null);

  const documentName = useCallback(
    (id) => documents.find((d) => d.id === id)?.name || id,
    [documents],
  );

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      const [e, i, a, f, fmt] = await Promise.all([
        integrationsApi.listSourceEvents(brfId),
        integrationsApi.listInvoices(brfId),
        integrationsApi.availableInvoices(brfId),
        integrationsApi.listFindings(brfId),
        integrationsApi.format(brfId),
      ]);
      setEvents(e);
      setInvoices(i);
      setAvailable(a.invoices || []);
      setFindings(f);
      setFormat(fmt);
      setError('');
    } catch (err) {
      setError(err.message || 'Kunde inte hämta integrationsdata.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  const findingsByInvoice = useMemo(() => {
    const map = new Map();
    findings.forEach((finding) => {
      const key = finding.invoice_id || 'utan-faktura';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(finding);
    });
    return map;
  }, [findings]);

  // The app's own citation navigation: it opens the document, jumps to the
  // page AND paints the rects. A finding's evidence therefore lands exactly
  // where an answer's citation does — same machinery, same highlight, no
  // second viewer that could disagree with the first.
  const openCitation = useCallback(
    (citation) => onOpenCitation?.(citation),
    [onOpenCitation],
  );

  async function handleImport(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const created = await integrationsApi.importSourceEvent(brfId, file);
      setNotice(`Importerat: ${created.subject || file.name}`);
      await refresh();
    } catch (err) {
      // 409 carries the id of the message this already is; 422 carries the
      // stable rejection code. Both are shown as the operator's own words.
      setError(err.message || 'Importen gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }

  async function decideEvent(eventId, status, note) {
    setBusy(true);
    try {
      await integrationsApi.decideSourceEvent(brfId, eventId, { status, note });
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte spara beslutet.');
    } finally {
      setBusy(false);
    }
  }

  async function linkDocument(eventId, current, documentId) {
    const next = current.includes(documentId)
      ? current.filter((id) => id !== documentId)
      : [...current, documentId];
    setBusy(true);
    try {
      await integrationsApi.decideSourceEvent(brfId, eventId, {
        status: 'open',
        linked_document_ids: next,
      });
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte koppla dokumentet.');
    } finally {
      setBusy(false);
    }
  }

  async function removeEvent(eventId) {
    setBusy(true);
    try {
      await integrationsApi.deleteSourceEvent(brfId, eventId);
      setNotice('Köposten togs bort. Inlästa dokument ligger kvar under Dokument.');
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte ta bort posten.');
    } finally {
      setBusy(false);
    }
  }

  async function readInvoice(externalRef) {
    setBusy(true);
    setError('');
    try {
      const snapshot = await integrationsApi.importInvoice(brfId, externalRef);
      await integrationsApi.reviewInvoice(brfId, snapshot.id);
      setNotice(`Faktura ${snapshot.invoice_number || snapshot.external_ref} inläst och granskad.`);
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte läsa in fakturan.');
    } finally {
      setBusy(false);
    }
  }

  async function rerunReview(invoiceId) {
    setBusy(true);
    try {
      await integrationsApi.reviewInvoice(brfId, invoiceId);
      await refresh();
    } catch (err) {
      setError(err.message || 'Granskningen kunde inte köras.');
    } finally {
      setBusy(false);
    }
  }

  async function decideFinding(findingId, status, note) {
    setBusy(true);
    try {
      await integrationsApi.decideFinding(brfId, findingId, { status, note });
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte spara beslutet.');
    } finally {
      setBusy(false);
    }
  }

  const openEvents = events.filter((e) => e.review_status === 'open').length;
  const openFindings = findings.filter((f) => f.status === 'open').length;

  return (
    <div className="integrations">
      <div className="integrations-header">
        <div className="integrations-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'inbox'}
            className={pane === 'inbox' ? 'active' : ''}
            onClick={() => setPane('inbox')}
          >
            <Inbox size={16} /> Inkommande
            {openEvents > 0 && <span className="pill">{openEvents}</span>}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'invoices'}
            className={pane === 'invoices' ? 'active' : ''}
            onClick={() => setPane('invoices')}
          >
            <Receipt size={16} /> Fakturagranskning
            {openFindings > 0 && <span className="pill">{openFindings}</span>}
          </button>
        </div>
        <button type="button" className="refresh" onClick={refresh} disabled={loading || busy}>
          <RefreshCw size={15} /> Uppdatera
        </button>
      </div>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {loading && (
        <p className="integrations-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>
      )}

      {pane === 'inbox' && !loading && (
        <section className="pane">
          <div className="pane-intro">
            <p>
              Välj en sparad <code>.eml</code>-fil. Filen läses en gång, på din begäran —
              appen kopplar sig aldrig till en brevlåda, hämtar ingenting löpande och
              skickar aldrig något.
            </p>
            {format && (
              <p className="format-note">
                Tas emot: {format.mail.attachmentTypes.join(', ')} som bilaga, högst{' '}
                {format.mail.maxAttachments} stycken och{' '}
                {Math.round(format.mail.maxMessageBytes / (1024 * 1024))} MB per meddelande.
                Allt annat avvisas i sin helhet — inget halvimporteras.
              </p>
            )}
            <input
              ref={fileInput}
              type="file"
              accept=".eml,message/rfc822"
              onChange={handleImport}
              className="hidden-file-input"
              id="eml-import"
            />
            <label htmlFor="eml-import" className={`import-button ${busy ? 'busy' : ''}`}>
              {busy ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
              Importera .eml-fil
            </label>
          </div>

          {events.length === 0 && <p className="empty">Inget har importerats ännu.</p>}

          {events.map((event) => (
            <article key={event.id} className={`event ${event.review_status}`}>
              <header className="event-head">
                <div>
                  <h4>{event.subject || '(utan ämne)'}</h4>
                  <p className="event-meta">
                    Från {event.origin_display ? `${event.origin_display} <${event.origin}>` : event.origin}
                    {' · '}avsänt {formatDateTime(event.occurred_at)}
                    {' · '}mottaget {formatDateTime(event.received_at)}
                  </p>
                </div>
                <span className="event-status">{STATUS_LABEL[event.review_status]}</span>
              </header>

              <details className="event-provenance">
                <summary>Proveniens</summary>
                <dl>
                  <div><dt>Originalfil</dt><dd>{event.provenance.origin_filename} ({event.provenance.origin_bytes} byte)</dd></div>
                  <div><dt>Innehållshash</dt><dd><code>{event.content_sha256}</code></dd></div>
                  <div><dt>Extern referens</dt><dd><code>{event.external_ref || '—'}</code></dd></div>
                  <div><dt>Importerat av</dt><dd>{event.provenance.imported_by}</dd></div>
                  <div><dt>Metod</dt><dd>{event.provenance.method} / {event.provenance.adapter}</dd></div>
                </dl>
              </details>

              {event.body_text && <pre className="event-body">{event.body_text}</pre>}

              {event.attachments.length > 0 && (
                <div className="event-attachments">
                  <h5><Paperclip size={14} /> Bilagor</h5>
                  <ul>
                    {event.attachments.map((attachment) => (
                      <li key={attachment.id}>
                        <button
                          type="button"
                          className="link"
                          onClick={() => onOpenDocument?.(attachment.document_id, 1)}
                        >
                          {attachment.filename}
                        </button>
                        <span className="muted"> · {attachment.bytes} byte · sha256 {attachment.sha256.slice(0, 16)}…</span>
                        {attachment.reused_existing_document && (
                          <span className="badge dedup">samma fil fanns redan — länkad, inte inläst igen</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="event-links">
                <h5>Koppling till föreningens dokument</h5>
                {event.suggested_document_ids.length === 0 && event.linked_document_ids.length === 0 && (
                  <p className="muted">Inga förslag.</p>
                )}
                <ul className="link-list">
                  {[...new Set([...event.linked_document_ids, ...event.suggested_document_ids])].map((docId) => {
                    const linked = event.linked_document_ids.includes(docId);
                    return (
                      <li key={docId}>
                        <label>
                          <input
                            type="checkbox"
                            checked={linked}
                            disabled={busy}
                            onChange={() => linkDocument(event.id, event.linked_document_ids, docId)}
                          />
                          {documentName(docId)}
                        </label>
                        <span className={`badge ${linked ? 'confirmed' : 'proposed'}`}>
                          {linked ? 'bekräftad av människa' : 'förslag'}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {event.decision_note && <p className="event-note">Anteckning: {event.decision_note}</p>}

              <div className="event-actions">
                <DecisionBar
                  status={event.review_status}
                  busy={busy}
                  onDecide={(status, note) => decideEvent(event.id, status, note)}
                />
                <button type="button" className="event-delete" disabled={busy} onClick={() => removeEvent(event.id)}>
                  <Trash2 size={14} /> Ta bort ur kön
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      {pane === 'invoices' && !loading && (
        <section className="pane">
          <div className="pane-intro">
            <p>
              Fakturor läses <strong>read-only</strong> från ett avgränsat underlag.
              Appen kan inte bokföra, kontera, attestera, betala eller ändra någon
              status i ett ekonomisystem — det finns ingen kodväg som skriver utåt.
            </p>
          </div>

          {available.length > 0 && (
            <div className="available-invoices">
              <h4>Tillgängliga att läsa in</h4>
              <table>
                <thead>
                  <tr>
                    <th>Referens</th><th>Leverantör</th><th>Datum</th><th>Belopp</th><th />
                  </tr>
                </thead>
                <tbody>
                  {available.map((row) => {
                    const alreadyRead = invoices.some((i) => i.external_ref === row.external_ref);
                    return (
                      <tr key={row.external_ref}>
                        <td><code>{row.external_ref}</code></td>
                        <td>{row.supplier_name}</td>
                        <td>{row.invoice_date || '—'}</td>
                        <td>{formatAmount(row.total_amount, row.currency)}</td>
                        <td>
                          <button type="button" disabled={busy} onClick={() => readInvoice(row.external_ref)}>
                            {alreadyRead ? 'Läs om och granska' : 'Läs in och granska'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {invoices.length === 0 && <p className="empty">Ingen faktura är inläst ännu.</p>}

          {invoices.map((invoice) => (
            <article key={invoice.id} className="invoice">
              <header className="invoice-head">
                <div>
                  <h4>{invoice.supplier_name}</h4>
                  <p className="invoice-meta">
                    Faktura {invoice.invoice_number || invoice.external_ref}
                    {' · '}{invoice.invoice_date || 'utan datum'}
                    {invoice.period_start && ` · period ${invoice.period_start} – ${invoice.period_end}`}
                  </p>
                </div>
                <div className="invoice-total">{formatAmount(invoice.total_amount, invoice.currency)}</div>
              </header>

              <details className="invoice-provenance">
                <summary>Originalkälla</summary>
                <dl>
                  <div><dt>Adapter</dt><dd>{invoice.adapter}</dd></div>
                  <div><dt>Underlag</dt><dd>{invoice.source_dataset}</dd></div>
                  <div><dt>Referens i källan</dt><dd><code>{invoice.external_ref}</code></dd></div>
                  <div><dt>Läst</dt><dd>{formatDateTime(invoice.retrieved_at)}</dd></div>
                  <div><dt>Hash</dt><dd><code>{invoice.content_sha256}</code></dd></div>
                  <div><dt>Moms</dt><dd>{formatAmount(invoice.vat_amount, invoice.currency)}</dd></div>
                </dl>
              </details>

              {invoice.lines.length > 0 && (
                <table className="invoice-lines">
                  <thead>
                    <tr><th>Rad</th><th>Antal</th><th>À-pris</th><th>Belopp</th></tr>
                  </thead>
                  <tbody>
                    {invoice.lines.map((line, i) => (
                      <tr key={i}>
                        <td>{line.description}</td>
                        <td>{line.quantity ?? '—'}</td>
                        <td>{formatAmount(line.unit_price, invoice.currency)}</td>
                        <td>{formatAmount(line.amount, invoice.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div className="invoice-findings">
                <div className="invoice-findings-head">
                  <h5>Granskning mot föreningens dokument</h5>
                  <button type="button" disabled={busy} onClick={() => rerunReview(invoice.id)}>
                    <RefreshCw size={14} /> Kör om
                  </button>
                </div>
                {(findingsByInvoice.get(invoice.id) || []).map((finding) => (
                  <Finding
                    key={finding.id}
                    finding={finding}
                    busy={busy}
                    onDecide={decideFinding}
                    onOpenCitation={openCitation}
                  />
                ))}
                {!findingsByInvoice.get(invoice.id) && (
                  <p className="muted">Ingen granskning har körts för den här fakturan.</p>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
