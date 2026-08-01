import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileText,
  HelpCircle,
  Inbox,
  Link2,
  Loader2,
  Mail,
  Paperclip,
  Plug,
  Receipt,
  RefreshCw,
  Table2,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { integrationsApi } from '../api';
import IntegrationConnections from './IntegrationConnections';
import MappingPreview from './MappingPreview';
import './Integrations.css';

/**
 * The board's incoming queue and the read-only invoice review.
 *
 * Four panes, one rule across them: nothing on this screen presents a system
 * proposal as an established fact. Verified facts, the proposal and the stated
 * uncertainty are three separate blocks with three different visual weights,
 * and a citation is always clickable through to the page it came from — a
 * finding whose evidence cannot be opened is an assertion, not a finding.
 *
 * The live connections widen where material may come from and change nothing
 * about that rule: a message read out of a connected mailbox goes through the
 * same format check, the same hash, the same duplicate rule and the same queue
 * as a file someone picked by hand, and neither is evidence until a person
 * says so.
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

// How the event got here, in words. The stored value is a stable code and is
// shown next to the sentence, because the two are read by different people.
const METHOD_LABEL = {
  'manual-file-import': 'Någon valde en sparad .eml-fil',
  'graph-mailbox-import': 'Hämtat ur den anslutna brevlådan, på begäran',
};

const ANCHOR_LABEL = {
  org_number: 'organisationsnummer',
  exact: 'leverantörens namn ordagrant',
  alias: 'ett namn en person här har bekräftat',
  legal_form: 'samma namn, annan bolagsform',
  partial: 'delvis namnlikhet',
};

// Only "partial" is weak, and the backend says so too (supplier.WEAK_STRENGTHS).
const WEAK_ANCHORS = new Set(['partial']);

const SOURCE_LABEL = {
  fixture: 'Syntetiskt underlag',
  fortnox: 'Fortnox',
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

/**
 * The alias a weak anchor would like confirmed.
 *
 * The engine may notice that two names share a distinctive head; only a person
 * here can say they are the same company. Confirming is therefore a statement
 * by a named human, and the review has to be re-run before it counts — nothing
 * about an already recorded finding changes retroactively.
 */
function AliasProposal({ proposal, busy, confirmed, onConfirm, onRerun }) {
  const [note, setNote] = useState('');

  if (confirmed) {
    return (
      <div className="alias-proposal confirmed">
        <p>
          Sparat. Namnen räknas som samma leverantör från och med nu — det gäller
          granskningar som körs härefter.
        </p>
        <button type="button" className="alias-rerun" disabled={busy} onClick={onRerun}>
          <RefreshCw size={14} /> Kör om granskningen
        </button>
      </div>
    );
  }

  return (
    <div className="alias-proposal">
      <h5>Är det samma leverantör?</h5>
      <p>{proposal.basis}</p>
      <p>
        Fakturan skriver <strong>{proposal.invoice_name}</strong>, dokumentet
        skriver <strong>{proposal.document_name}</strong>. Ingen utom ni kan avgöra
        om det är samma företag.
      </p>
      <div className="alias-actions">
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Anteckning (valfri)"
          aria-label="Anteckning om leverantörsnamnen"
        />
        <button
          type="button"
          className="alias-confirm"
          disabled={busy}
          onClick={() => onConfirm(note.trim() || null)}
        >
          Ja, samma leverantör
        </button>
      </div>
      <p className="muted">
        Säger ni ingenting står kopplingen kvar som svag, och fyndet läses därefter.
      </p>
    </div>
  );
}

function Finding({ finding, busy, aliasConfirmed, onDecide, onOpenCitation, onConfirmAlias, onRerun }) {
  const tone = VERDICT_TONE[finding.verdict] || 'unknown';
  const Icon = VERDICT_ICON[finding.verdict] || HelpCircle;
  const invoiceFacts = finding.verified_facts.filter((f) => f.source === 'invoice');
  const documentFacts = finding.verified_facts.filter((f) => f.source === 'document');
  const weakAnchor = WEAK_ANCHORS.has(finding.anchor_strength);

  return (
    <article className={`finding ${tone} ${finding.status !== 'open' ? 'decided' : ''}`}>
      <header className="finding-head">
        <span className={`verdict ${tone}`}>
          <Icon size={16} /> {finding.verdict_label}
        </span>
        <span className="finding-status">{STATUS_LABEL[finding.status] || finding.status}</span>
      </header>

      {finding.anchor_strength && (
        <div className={`finding-anchor ${weakAnchor ? 'weak' : 'strong'}`}>
          <h5>
            <Link2 size={13} />
            {weakAnchor ? 'Svag koppling till leverantören' : 'Säker koppling till leverantören'}
            <span className="anchor-basis">{ANCHOR_LABEL[finding.anchor_strength] || finding.anchor_strength}</span>
          </h5>
          {finding.anchor_note && <p>{finding.anchor_note}</p>}
          {weakAnchor && (
            <p className="anchor-warning">
              Jämförelsen kan alltså gälla fel leverantör. Läs fyndet med det i minnet.
            </p>
          )}
        </div>
      )}

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

      {finding.alias_proposal && (
        <AliasProposal
          proposal={finding.alias_proposal}
          busy={busy}
          confirmed={aliasConfirmed}
          onConfirm={(note) => onConfirmAlias(finding, note)}
          onRerun={() => onRerun(finding.invoice_id)}
        />
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

/**
 * One attachment, and the decision whether it belongs in the association's own
 * archive. The note is required here as well as in the backend — a form that
 * sent something invented to satisfy the route would defeat the point of
 * requiring it.
 */
function AttachmentItem({ attachment, busy, onOpen, onAdopt, onWithdraw }) {
  const [note, setNote] = useState('');
  const canAdopt = Boolean(attachment.document_id) && !busy && note.trim().length > 0;

  return (
    <li className={attachment.archived ? 'adopted' : ''}>
      <div className="attachment-line">
        <button type="button" className="link" onClick={onOpen}>
          {attachment.filename}
        </button>
        <span className="muted"> · {attachment.bytes} byte · sha256 {attachment.sha256.slice(0, 16)}…</span>
        {attachment.reused_existing_document && (
          <span className="badge dedup">samma fil fanns redan — länkad, inte inläst igen</span>
        )}
        <span className={`badge ${attachment.archived ? 'confirmed' : 'proposed'}`}>
          {attachment.archived ? 'i föreningens arkiv' : 'material under granskning'}
        </span>
      </div>

      {attachment.archived ? (
        <div className="attachment-adoption">
          <p className="muted">
            Lagd i arkivet av {attachment.archived_by} {formatDateTime(attachment.archived_at)}
            {attachment.archive_note ? ` — ${attachment.archive_note}` : ''}
          </p>
          <button type="button" className="attachment-withdraw" disabled={busy} onClick={onWithdraw}>
            Ta tillbaka ur arkivet
          </button>
        </div>
      ) : (
        <div className="attachment-adoption">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Varför hör den till föreningens underlag? (krävs)"
            aria-label={`Varför ${attachment.filename} hör till föreningens underlag`}
            disabled={busy}
          />
          <button
            type="button"
            className="attachment-adopt"
            disabled={!canAdopt}
            title={attachment.document_id
              ? (note.trim() ? undefined : 'Skriv först varför bilagan hör till arkivet.')
              : 'Bilagan lästes aldrig in som dokument och kan inte läggas i arkivet.'}
            onClick={() => onAdopt(note.trim())}
          >
            <Archive size={14} /> Lägg i arkivet
          </button>
        </div>
      )}
    </li>
  );
}

/**
 * The connected mailbox, listed on request.
 *
 * Nothing is fetched by itself: there is no sync, no polling and no watcher —
 * every read here happened because someone pressed something. Reading a message
 * does not mark, move or delete it, so the mailbox looks the same afterwards as
 * it did before.
 */
function MailboxBrowser({ brfId, connection, onImported, onError }) {
  const [messages, setMessages] = useState(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState('');
  const [onlyWithAttachments, setOnlyWithAttachments] = useState(true);

  async function load(withAttachmentsOnly = onlyWithAttachments) {
    setLoading(true);
    try {
      const result = await integrationsApi.listMailboxMessages(brfId, {
        limit: 25,
        onlyWithAttachments: withAttachmentsOnly,
      });
      setMessages(result.messages || []);
    } catch (err) {
      setMessages(null);
      onError(err.message || 'Brevlådan kunde inte läsas.');
    } finally {
      setLoading(false);
    }
  }

  async function importMessage(message) {
    setImporting(message.id);
    try {
      await integrationsApi.importMailboxMessage(brfId, message.id);
      await onImported(message);
    } catch (err) {
      // Same two refusals as the manual import: 409 when these exact bytes are
      // already in the queue, 422 when the message is outside the format.
      onError(err.message || 'Meddelandet kunde inte läsas in.');
    } finally {
      setImporting('');
    }
  }

  return (
    <div className="mailbox">
      <h4><Mail size={15} /> Ansluten brevlåda</h4>
      <p className="muted">
        {connection.mailbox
          ? `Delad brevlåda ${connection.mailbox}, mappen ${connection.folder}.`
          : `Det inloggade kontots egen brevlåda (${connection.account_label || 'okänt konto'}), mappen ${connection.folder}.`}
        {' '}Listan hämtas när du ber om den. Meddelanden markeras, flyttas eller
        raderas aldrig — brevlådan ser likadan ut efteråt.
      </p>

      <div className="mailbox-controls">
        <label>
          <input
            type="checkbox"
            checked={onlyWithAttachments}
            onChange={(e) => { setOnlyWithAttachments(e.target.checked); load(e.target.checked); }}
          />
          Bara meddelanden med bilagor
        </label>
        <button type="button" disabled={loading} onClick={() => load()}>
          {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
          {messages === null ? ' Hämta meddelanden' : ' Hämta igen'}
        </button>
      </div>

      {messages !== null && messages.length === 0 && (
        <p className="empty">Inga meddelanden i mappen som matchar.</p>
      )}

      {messages !== null && messages.length > 0 && (
        <ul className="mailbox-list">
          {messages.map((message) => (
            <li key={message.id}>
              <div className="mailbox-message">
                <strong>{message.subject || '(utan ämne)'}</strong>
                <span className="muted">
                  {message.fromDisplay ? `${message.fromDisplay} <${message.from}>` : message.from}
                  {' · '}{formatDateTime(message.receivedAt)}
                  {message.hasAttachments ? ' · med bilaga' : ' · utan bilaga'}
                </span>
                {message.preview && <span className="mailbox-preview">{message.preview}</span>}
              </div>
              <button
                type="button"
                disabled={Boolean(importing)}
                onClick={() => importMessage(message)}
              >
                {importing === message.id ? <Loader2 size={14} className="spin" /> : <Upload size={14} />}
                {' '}Läs in
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Integrations({ brfId, documents, onOpenDocument, onOpenCitation }) {
  const [pane, setPane] = useState('inbox');

  const [events, setEvents] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [available, setAvailable] = useState([]);
  const [availableError, setAvailableError] = useState('');
  const [findings, setFindings] = useState([]);
  const [format, setFormat] = useState(null);
  const [connections, setConnections] = useState(null);
  const [aliases, setAliases] = useState([]);
  const [source, setSource] = useState('fixture');
  const [mappingRef, setMappingRef] = useState('');
  const [aliasConfirmed, setAliasConfirmed] = useState({});

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
      const [e, i, f, fmt, conns, als] = await Promise.all([
        integrationsApi.listSourceEvents(brfId),
        integrationsApi.listInvoices(brfId),
        integrationsApi.listFindings(brfId),
        integrationsApi.format(brfId),
        integrationsApi.connections(brfId),
        integrationsApi.listSupplierAliases(brfId),
      ]);
      setEvents(e);
      setInvoices(i);
      setFindings(f);
      setFormat(fmt);
      setConnections(conns);
      setAliases(als);
      setError('');
      // Kept apart from the rest: a live accounting source that is down or
      // signed out must not blank the queue, the findings and the archive that
      // are all stored locally and perfectly readable.
      try {
        const a = await integrationsApi.availableInvoices(brfId, source);
        setAvailable(a.invoices || []);
        setAvailableError('');
      } catch (err) {
        setAvailable([]);
        setAvailableError(err.message || 'Fakturakällan svarade inte.');
      }
    } catch (err) {
      setError(err.message || 'Kunde inte hämta integrationsdata.');
    } finally {
      setLoading(false);
    }
  }, [brfId, source]);

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

  const graph = connections?.['microsoft-graph'];
  const fortnox = connections?.fortnox;
  const mailboxReady = graph?.connection?.status === 'connected';
  const fortnoxReady = fortnox?.connection?.status === 'connected';
  const invoiceSources = format?.invoiceSources || ['fixture'];

  // The engine may not read from a source that is not connected, so neither may
  // the picker: an option that always answers 409 is not a choice.
  useEffect(() => {
    if (source === 'fortnox' && connections && !fortnoxReady) setSource('fixture');
  }, [source, connections, fortnoxReady]);

  useEffect(() => {
    if (pane === 'mapping' && connections && !fortnoxReady) setPane('invoices');
  }, [pane, connections, fortnoxReady]);

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

  async function adoptAttachment(eventId, attachment, note) {
    setBusy(true);
    setError('');
    try {
      await integrationsApi.archiveAttachment(brfId, eventId, attachment.id, note);
      setNotice(`${attachment.filename} ingår nu i föreningens arkiv och kan citeras som bevis.`);
      await refresh();
    } catch (err) {
      setError(err.message || 'Bilagan kunde inte läggas i arkivet.');
    } finally {
      setBusy(false);
    }
  }

  async function withdrawAttachment(eventId, attachment) {
    setBusy(true);
    try {
      await integrationsApi.withdrawAttachment(brfId, eventId, attachment.id);
      setNotice(`${attachment.filename} räknas åter som material under granskning. Dokumentet ligger kvar.`);
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte ta tillbaka bilagan.');
    } finally {
      setBusy(false);
    }
  }

  async function readInvoice(externalRef) {
    setBusy(true);
    setError('');
    try {
      const snapshot = await integrationsApi.importInvoice(brfId, externalRef, source);
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

  async function confirmAlias(finding, note) {
    setBusy(true);
    setError('');
    try {
      await integrationsApi.addSupplierAlias(brfId, {
        invoice_name: finding.alias_proposal.invoice_name,
        document_name: finding.alias_proposal.document_name,
        note,
      });
      setAliasConfirmed((current) => ({ ...current, [finding.id]: true }));
      setNotice('Namnen är bekräftade. Kör om granskningen för att använda dem.');
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte spara leverantörsnamnet.');
    } finally {
      setBusy(false);
    }
  }

  async function removeAlias(aliasId) {
    setBusy(true);
    try {
      await integrationsApi.deleteSupplierAlias(brfId, aliasId);
      await refresh();
    } catch (err) {
      setError(err.message || 'Kunde inte ta bort posten.');
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
          {fortnoxReady && (
            <button
              type="button"
              role="tab"
              aria-selected={pane === 'mapping'}
              className={pane === 'mapping' ? 'active' : ''}
              onClick={() => setPane('mapping')}
            >
              <Table2 size={16} /> Fältkontroll
            </button>
          )}
          <button
            type="button"
            role="tab"
            aria-selected={pane === 'connections'}
            className={pane === 'connections' ? 'active' : ''}
            onClick={() => setPane('connections')}
          >
            <Plug size={16} /> Anslutningar
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
              Välj en sparad <code>.eml</code>-fil. Filen läses en gång, på din
              begäran, och fungerar utan någon anslutning alls.
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

          {mailboxReady ? (
            <MailboxBrowser
              brfId={brfId}
              connection={graph.connection}
              onImported={async (message) => {
                setNotice(`Inläst ur brevlådan: ${message.subject || message.id}`);
                setError('');
                await refresh();
              }}
              onError={(message) => { setNotice(''); setError(message); }}
            />
          ) : (
            <p className="mailbox-absent muted">
              Ingen brevlåda är ansluten. Det behövs inte för att importera en
              fil — en anslutning gör bara att meddelanden kan väljas ur en lista
              i stället för att exporteras för hand. Se <strong>Anslutningar</strong>.
            </p>
          )}

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

              <p className="event-method">
                {METHOD_LABEL[event.provenance.method] || event.provenance.method}
              </p>

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
                  <p className="adoption-explainer">
                    En bilaga är material under granskning tills någon lägger den i
                    föreningens arkiv: dessförinnan citerar granskningen den inte,
                    därefter är den en del av arkivet och kan användas som bevis —
                    och det går att ta tillbaka.
                  </p>
                  <ul>
                    {event.attachments.map((attachment) => (
                      <AttachmentItem
                        key={attachment.id}
                        attachment={attachment}
                        busy={busy}
                        onOpen={() => onOpenDocument?.(attachment.document_id, 1)}
                        onAdopt={(note) => adoptAttachment(event.id, attachment, note)}
                        onWithdraw={() => withdrawAttachment(event.id, attachment)}
                      />
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
            <div className="source-picker" role="radiogroup" aria-label="Fakturakälla">
              {invoiceSources.map((name) => {
                const disabled = name === 'fortnox' && !fortnoxReady;
                return (
                  <label key={name} className={disabled ? 'disabled' : ''}>
                    <input
                      type="radio"
                      name="invoice-source"
                      value={name}
                      checked={source === name}
                      disabled={disabled}
                      onChange={() => setSource(name)}
                    />
                    {SOURCE_LABEL[name] || name}
                    {disabled && <span className="muted"> (inte ansluten)</span>}
                  </label>
                );
              })}
            </div>
          </div>

          {availableError && (
            <Banner tone="error" onDismiss={() => setAvailableError('')}>{availableError}</Banner>
          )}

          {available.length > 0 && (
            <div className="available-invoices">
              <h4>Tillgängliga att läsa in — {SOURCE_LABEL[source] || source}</h4>
              {source === 'fortnox' && (
                <p className="muted">
                  Bokförd och annullerad läses ur ekonomisystemet och ändras aldrig
                  av den här produkten.
                </p>
              )}
              <table>
                <thead>
                  <tr>
                    <th>Referens</th><th>Leverantör</th><th>Datum</th><th>Belopp</th>
                    {source === 'fortnox' && <><th>Bokförd</th><th>Annullerad</th></>}
                    <th />
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
                        {source === 'fortnox' && (
                          <>
                            <td>{row.booked ? 'ja' : 'nej'}</td>
                            <td>{row.cancelled ? 'ja' : 'nej'}</td>
                          </>
                        )}
                        <td className="available-actions">
                          <button type="button" disabled={busy} onClick={() => readInvoice(row.external_ref)}>
                            {alreadyRead ? 'Läs om och granska' : 'Läs in och granska'}
                          </button>
                          {source === 'fortnox' && (
                            <button
                              type="button"
                              className="secondary"
                              onClick={() => { setMappingRef(row.external_ref); setPane('mapping'); }}
                            >
                              Kontrollera fälten
                            </button>
                          )}
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
                    aliasConfirmed={Boolean(aliasConfirmed[finding.id])}
                    onDecide={decideFinding}
                    onOpenCitation={openCitation}
                    onConfirmAlias={confirmAlias}
                    onRerun={rerunReview}
                  />
                ))}
                {!findingsByInvoice.get(invoice.id) && (
                  <p className="muted">Ingen granskning har körts för den här fakturan.</p>
                )}
              </div>
            </article>
          ))}

          <div className="alias-list">
            <h4>Bekräftade leverantörsnamn</h4>
            <p className="muted">
              Namn som en person här har sagt hör till samma leverantör. De gör
              kopplingen mellan faktura och avtal säker i stället för trolig.
            </p>
            {aliases.length === 0 ? (
              <p className="empty">Inga bekräftade namn ännu.</p>
            ) : (
              <ul>
                {aliases.map((alias) => (
                  <li key={alias.id}>
                    <span>
                      <strong>{alias.invoice_name}</strong> är samma som{' '}
                      <strong>{alias.document_name}</strong>
                    </span>
                    <span className="muted">
                      {alias.note ? `${alias.note} · ` : ''}
                      {alias.created_by} · {formatDateTime(alias.created_at)}
                    </span>
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`Ta bort ${alias.invoice_name} = ${alias.document_name}`}
                      onClick={() => removeAlias(alias.id)}
                    >
                      <Trash2 size={14} /> Ta bort
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {pane === 'mapping' && !loading && fortnoxReady && (
        <section className="pane">
          <MappingPreview brfId={brfId} initialRef={mappingRef} key={mappingRef} />
        </section>
      )}

      {pane === 'connections' && !loading && connections && (
        <section className="pane">
          <IntegrationConnections
            brfId={brfId}
            connections={connections}
            mailFolders={format?.mailFolders}
            onChanged={refresh}
          />
        </section>
      )}
    </div>
  );
}
