import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  ClipboardList,
  FileText,
  HelpCircle,
  History,
  Link2,
  Loader2,
  Mail,
  MessageSquare,
  Paperclip,
  RefreshCw,
  Sparkles,
  Trash2,
  User,
} from 'lucide-react';
import { integrationsApi, invoicesApi } from '../api';
import CreateTask from './CreateTask';
import { formatAmount } from './money';
import PdfPane from './PdfPane';
// The epistemic presentation — verified facts as data, the proposal as tinted
// prose, uncertainty in a warmer block that cannot be skimmed past — is one
// design and lives in one stylesheet. Findings look identical here and in
// Inkommande because they *are* the same thing being shown.
import './Integrations.css';

/**
 * One invoice as one case: the original, the analysis, and the work around it.
 *
 * Three columns, and the split is the argument. The left column is **what
 * arrived** — the original file, the fields as the source system wrote them,
 * and where each of those came from. The middle is **what the product thinks**,
 * with every claim carrying either a verbatim citation or an honest statement
 * that there is none. The right is **what people did** — a review status that
 * belongs to this association and nobody else, comments, work, and a timeline
 * that keeps machine findings and human decisions in one order while marking
 * which is which.
 *
 * Two rules run through all of it:
 *
 * 1. **The accounting system's status and ours are never the same badge.** They
 *    sit side by side, labelled, and the local one carries the sentence saying
 *    what it does not mean. There is no "Godkänn faktura" anywhere on this
 *    screen, because there is no approval to give.
 * 2. **The original is never replaced by a derivative.** The invoice PDF is
 *    opened through the app's own document viewer at the real page; the
 *    normalised fields are shown beside it as a reading, not instead of it.
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

// What the three verdicts mean in the words this workspace uses. The product
// has three and not four on purpose (docs/INTEGRATIONSDOMAN.md §5) — asserting
// a deviation as fact would claim what a contract *says*, and "överensstämmer"
// already covers both "verifierat" and "ingen avvikelse hittad".
const VERDICT_MEANING = {
  matches: 'Verifierat mot citerat underlag. Det är inte ett godkännande.',
  possible_deviation: 'Stark jämförelse, men något saknas — läs osäkerheten innan ni agerar.',
  cannot_be_verified: 'Går inte att avgöra på det underlag som finns. Underlag saknas.',
};

const STATUS_LABEL = {
  open: 'Öppen',
  approved: 'Godkänd',
  dismissed: 'Avfärdad',
  corrected: 'Korrigerad',
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

// Which findings compare the invoice against the association's *documents*, and
// which compare it against its own *invoice history*. Two different kinds of
// evidence, so two headings — a reader must not have to work out that a
// finding with no citation was never supposed to have one.
const HISTORY_FINDINGS = new Set([
  'invoice_previous_comparison',
  'invoice_possible_duplicate',
  'invoice_credit_relation',
  'invoice_new_line',
]);

const OBSERVATION_ICON = {
  accounting_snapshot: Building2,
  email: Mail,
  document: Paperclip,
};

const OBSERVATION_LABEL = {
  accounting_snapshot: 'Ekonomisystem',
  email: 'E-post',
  document: 'Originalfil',
};

const EVENT_ICON = {
  case_opened: FileText,
  observation_added: Link2,
  analysis_run: Sparkles,
  finding_recorded: Sparkles,
  status_changed: CheckCircle2,
  assigned: User,
  commented: MessageSquare,
  task_created: ClipboardList,
  source_refreshed: RefreshCw,
};

// Statuses the backend refuses without a sentence (models.REVIEW_REASON_REQUIRED).
// Checked here too so the form asks rather than sending a 422 to find out.
const NOTE_REQUIRED = new Set(['needs_investigation', 'awaiting_documentation', 'question_sent']);

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('sv-SE', {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
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
 * here can say they are the same company. The review has to be re-run before
 * the confirmation counts — nothing about an already recorded finding changes
 * retroactively.
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
        Fakturan skriver <strong>{proposal.invoice_name}</strong>, dokumentet skriver{' '}
        <strong>{proposal.document_name}</strong>. Ingen utom ni kan avgöra om det är
        samma företag.
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

function DecisionBar({ status, busy, onDecide }) {
  const [note, setNote] = useState('');
  return (
    <div className="decision-bar">
      <input
        type="text"
        className="decision-note"
        placeholder="Vad gäller i stället? (krävs för korrigering)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        aria-label="Beskriv korrigeringen"
      />
      <div className="decision-buttons">
        <button type="button" className="decision approve" disabled={busy} onClick={() => onDecide('approved', note.trim() || null)}>
          Godkänn fyndet
        </button>
        <button type="button" className="decision dismiss" disabled={busy} onClick={() => onDecide('dismissed', note.trim() || null)}>
          Avfärda
        </button>
        <button
          type="button"
          className="decision correct"
          disabled={busy || !note.trim()}
          title={note.trim() ? undefined : 'Skriv vad som gäller i stället först.'}
          onClick={() => onDecide('corrected', note.trim())}
        >
          Korrigera
        </button>
        {status !== 'open' && (
          <button type="button" className="decision reopen" disabled={busy} onClick={() => onDecide('open', null)}>
            Öppna igen
          </button>
        )}
      </div>
      <p className="muted">
        Det här är ett ställningstagande till <em>fyndet</em>, inte till fakturan.
      </p>
    </div>
  );
}

function Finding({
  finding, brfId, busy, canDecide, aliasConfirmed,
  onDecide, onOpenCitation, onConfirmAlias, onRerun, onTaskCreated,
}) {
  const tone = VERDICT_TONE[finding.verdict] || 'unknown';
  const Icon = VERDICT_ICON[finding.verdict] || HelpCircle;
  const invoiceFacts = finding.verified_facts.filter((f) => f.source === 'invoice');
  const documentFacts = finding.verified_facts.filter((f) => f.source === 'document');
  const weakAnchor = WEAK_ANCHORS.has(finding.anchor_strength);
  const fromHistory = HISTORY_FINDINGS.has(finding.finding_type);

  return (
    <article className={`finding ${tone} ${finding.status !== 'open' ? 'decided' : ''}`}>
      <header className="finding-head">
        <span className={`verdict ${tone}`}>
          <Icon size={16} /> {finding.verdict_label}
        </span>
        <span className="finding-status">{STATUS_LABEL[finding.status] || finding.status}</span>
      </header>

      <p className="verdict-meaning">{VERDICT_MEANING[finding.verdict]}</p>

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
          <h5>Verifierat ur fakturorna</h5>
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
              <div>
                <dd className="muted">
                  {fromHistory
                    ? 'Inget dokument ligger bakom det här — jämförelsen är gjord mot föreningens egna tidigare fakturor.'
                    : 'Ingenting kunde verifieras ordagrant.'}
                </dd>
              </div>
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
          onRerun={onRerun}
        />
      )}

      {finding.decision_note && (
        <p className="finding-decision-note">Anteckning: {finding.decision_note}</p>
      )}

      {canDecide && (
        <DecisionBar
          status={finding.status}
          busy={busy}
          onDecide={(status, note) => onDecide(finding.id, status, note)}
        />
      )}

      <CreateTask
        brfId={brfId}
        canCreate={canDecide}
        originKind="finding"
        originRef={finding.id}
        suggestedTitle={(finding.suggestion || finding.verdict_label || '').slice(0, 200)}
        onCreated={onTaskCreated}
      />
    </article>
  );
}

/** The original file, opened where it actually lives. */
function OriginalPane({ brfId, documents, onOpenDocument }) {
  const [active, setActive] = useState(0);
  const [page, setPage] = useState(1);
  const [numPages, setNumPages] = useState(null);
  const chosen = documents[active];

  useEffect(() => { setPage(1); setNumPages(null); }, [active]);

  if (!chosen) {
    return (
      <div className="case-original empty">
        <h4><Paperclip size={15} /> Originalhandling</h4>
        <p className="muted">
          Ingen originalfil är kopplad till ärendet. Fakturan är läst ur ekonomisystemet
          som strukturerade fält — fälten nedan är den läsningen, inte ett original.
          Kom fakturan också per mejl går PDF:en att ta in under <strong>Inkommande</strong>,
          och då hamnar den här.
        </p>
      </div>
    );
  }

  return (
    <div className="case-original">
      <h4><Paperclip size={15} /> Originalhandling</h4>
      {documents.length > 1 && (
        <div className="original-picker" role="tablist" aria-label="Handlingar">
          {documents.map((doc, i) => (
            <button
              key={doc.id}
              type="button"
              role="tab"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onClick={() => setActive(i)}
            >
              {doc.name}
            </button>
          ))}
        </div>
      )}
      <p className="original-role">
        {chosen.role} · {chosen.name}
        {chosen.basis ? ` — ${chosen.basis}` : ''}
      </p>
      <div className="original-toolbar">
        <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          Föregående
        </button>
        <span>Sida {page} av {numPages ?? chosen.pages ?? '…'}</span>
        <button
          type="button"
          disabled={(numPages ?? chosen.pages) != null && page >= (numPages ?? chosen.pages)}
          onClick={() => setPage((p) => p + 1)}
        >
          Nästa
        </button>
        <button type="button" className="link" onClick={() => onOpenDocument?.(chosen.id, page)}>
          Öppna i dokumentvyn
        </button>
      </div>
      <div className="original-canvas">
        <PdfPane
          url={`/api/brf/${brfId}/documents/${chosen.id}/pdf`}
          page={page}
          onNumPages={setNumPages}
          rects={[]}
          highlightPage={null}
          approximate={false}
        />
      </div>
    </div>
  );
}

function ReviewStatusForm({ caseData, labels, busy, canDecide, onSave }) {
  const [status, setStatus] = useState(caseData.review_status);
  const [note, setNote] = useState('');

  useEffect(() => { setStatus(caseData.review_status); setNote(''); }, [caseData.review_status, caseData.id]);

  const needsNote = NOTE_REQUIRED.has(status);
  const unchanged = status === caseData.review_status && !note.trim();
  const caveat = labels.reviewStatusCaveats[status];

  return (
    <div className="case-review-status">
      {/* Named differently from the summary card above on purpose: that one
          reports where the case stands, this one is where it is changed. Two
          identical headings on one screen make a reader hunt for the
          difference. */}
      <h4>Granskningsläge</h4>
      <p className="case-status-current">
        <strong>{caseData.review_status_label}</strong>
        {caseData.review_status_by && (
          <span className="muted">
            {' '}— {caseData.review_status_by}, {formatDateTime(caseData.review_status_at)}
          </span>
        )}
      </p>
      {caseData.review_status_note && (
        <p className="case-status-note">{caseData.review_status_note}</p>
      )}
      <p className="case-status-caveat">{caseData.review_status_caveat}</p>

      {canDecide && (
        <>
          <label>
            <span>Ändra till</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} disabled={busy}>
              {Object.entries(labels.reviewStatus).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </label>
          {caveat && status !== caseData.review_status && (
            <p className="case-status-preview">{caveat}</p>
          )}
          <label>
            <span>{needsNote ? 'Vad gäller? (krävs)' : 'Anteckning (valfri)'}</span>
            <input
              type="text"
              value={note}
              disabled={busy}
              placeholder={needsNote ? 'Vad ska utredas, vilket underlag saknas, vad gällde frågan?' : ''}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="case-primary"
            disabled={busy || unchanged || (needsNote && !note.trim())}
            onClick={() => onSave({ review_status: status, note: note.trim() })}
          >
            Spara granskningsläget
          </button>
        </>
      )}
    </div>
  );
}

function Timeline({ events }) {
  return (
    <div className="case-timeline">
      <h4><History size={15} /> Allt som hänt</h4>
      <ol>
        {events.map((event) => {
          const Icon = EVENT_ICON[event.kind] || Sparkles;
          return (
            <li key={event.id} className={event.human ? 'human' : 'engine'}>
              <span className="event-icon"><Icon size={13} /></span>
              <span className="event-body">
                <span className="event-summary">{event.summary}</span>
                {event.note && <span className="event-note">{event.note}</span>}
                <span className="event-meta">
                  {event.kind_label} · {event.by} · {formatDateTime(event.at)}
                  {!event.human && <span className="event-engine-tag">maskinellt</span>}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function InvoiceCase({
  brfId, caseId, isAdmin = false, onBack, onOpenCitation, onOpenDocument, onOpenCase, onChanged,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [comment, setComment] = useState('');
  const [responsible, setResponsible] = useState('');
  const [aliasConfirmed, setAliasConfirmed] = useState({});

  const refresh = useCallback(async () => {
    if (!brfId || !caseId) return;
    setLoading(true);
    try {
      const body = await invoicesApi.case(brfId, caseId);
      setData(body);
      setResponsible(body.case.responsible || '');
      setError('');
    } catch (err) {
      setError(err.message || 'Ärendet kunde inte hämtas.');
    } finally {
      setLoading(false);
    }
  }, [brfId, caseId]);

  useEffect(() => { refresh(); }, [refresh]);

  const run = useCallback(async (work, done) => {
    setBusy(true);
    setError('');
    try {
      const result = await work();
      await refresh();
      onChanged?.();
      done?.(result);
    } catch (err) {
      setError(err.message || 'Åtgärden gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }, [refresh, onChanged]);

  const documentFindings = useMemo(
    () => (data?.findings || []).filter((f) => !HISTORY_FINDINGS.has(f.finding_type)),
    [data],
  );
  const historyFindings = useMemo(
    () => (data?.findings || []).filter((f) => HISTORY_FINDINGS.has(f.finding_type)),
    [data],
  );

  if (loading && !data) {
    return <p className="case-loading"><Loader2 size={16} className="spin" /> Hämtar ärendet…</p>;
  }
  if (!data) {
    return (
      <div className="case-error">
        <button type="button" className="case-back" onClick={onBack}><ArrowLeft size={15} /> Till fakturakön</button>
        <p role="alert">{error || 'Ärendet finns inte.'}</p>
      </div>
    );
  }

  const { case: kase, invoice, supplier, labels, tasks, sourceEvent, documents } = data;

  return (
    <div className="invoice-case">
      <div className="case-topbar">
        <button type="button" className="case-back" onClick={onBack}>
          <ArrowLeft size={15} /> Till fakturakön
        </button>
        {isAdmin && (
          <button
            type="button"
            className="case-refresh"
            disabled={busy}
            onClick={() => run(
              () => invoicesApi.refresh(brfId, kase.id),
              (result) => setNotice(`${result.source} Ingenting ändrades i ekonomisystemet.`),
            )}
          >
            {busy ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} Läs om och granska
          </button>
        )}
      </div>

      {error && <div className="case-banner error" role="alert">{error}</div>}
      {notice && <div className="case-banner ok" role="status">{notice}</div>}

      <header className="case-header">
        <div>
          <h2>{kase.supplier_name || 'Okänd leverantör'}</h2>
          <p className="case-identity">
            Faktura {kase.invoice_number || '—'}
            {' · '}{kase.invoice_date || 'utan datum'}
            {kase.due_date && ` · förfaller ${kase.due_date}`}
            {kase.period_start && ` · period ${kase.period_start} – ${kase.period_end}`}
          </p>
          <p className="case-identity-basis" title="Varför de här källorna är samma faktura">
            <Link2 size={12} /> {kase.identity_basis}
          </p>
        </div>
        <div className="case-amount">{formatAmount(kase.total_amount, kase.currency)}</div>
      </header>

      <div className="case-statuses">
        <div className="case-status-card source">
          <h5>I ekonomisystemet</h5>
          <strong>{kase.source_status_label || 'Ingen status läst'}</strong>
          <p className="muted">
            {kase.source_status
              ? `Läst ${formatDateTime(kase.source_status.retrieved_at)}. Den här produkten ändrar den aldrig.`
              : 'Källan har ingen bokföringsstatus att läsa. Ingenting antas i dess ställe.'}
          </p>
        </div>
        <div className="case-status-card local">
          <h5>Vår granskning</h5>
          <strong>{kase.review_status_label}</strong>
          <p className="muted">{kase.review_status_caveat}</p>
        </div>
      </div>

      {kase.signals.length > 0 && (
        <ul className="case-signals">
          {kase.signals.map((signal, i) => (
            <li key={`${signal.kind}-${i}`} className={`signal ${signal.severity}`}>
              <strong>{signal.label}</strong>
              <span>{signal.detail}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="case-columns">
        {/* ---- what arrived ---- */}
        <section className="case-column evidence">
          <OriginalPane brfId={brfId} documents={documents} onOpenDocument={onOpenDocument} />

          <div className="case-panel">
            <h4><FileText size={15} /> Fakturans fält</h4>
            <dl className="case-fields">
              <div><dt>Leverantör</dt><dd>{kase.supplier_name || '—'}</dd></div>
              <div><dt>Leverantörsreferens</dt><dd>{kase.supplier_ref || '—'}</dd></div>
              <div><dt>Fakturanummer</dt><dd>{kase.invoice_number || '—'}</dd></div>
              <div><dt>Fakturadatum</dt><dd>{kase.invoice_date || '—'}</dd></div>
              <div><dt>Förfallodatum</dt><dd>{kase.due_date || '—'}</dd></div>
              <div><dt>Totalt</dt><dd>{formatAmount(kase.total_amount, kase.currency)}</dd></div>
              <div><dt>Varav moms</dt><dd>{formatAmount(kase.vat_amount, kase.currency)}</dd></div>
            </dl>
            {invoice?.lines?.length > 0 && (
              <table className="case-lines">
                <thead>
                  <tr><th>Rad</th><th>Antal</th><th>À-pris</th><th>Belopp</th></tr>
                </thead>
                <tbody>
                  {invoice.lines.map((row, i) => (
                    <tr key={i}>
                      <td>{row.description}</td>
                      <td>{row.quantity ?? '—'}</td>
                      <td>{formatAmount(row.unit_price, kase.currency)}</td>
                      <td>{formatAmount(row.amount, kase.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="case-panel">
            <h4><Link2 size={15} /> Källor och härkomst</h4>
            <ul className="case-observations">
              {kase.observations.map((observation) => {
                const Icon = OBSERVATION_ICON[observation.kind] || FileText;
                return (
                  <li key={`${observation.kind}-${observation.ref_id}`}>
                    <span className="observation-kind"><Icon size={12} /> {OBSERVATION_LABEL[observation.kind]}</span>
                    <span className="observation-label">{observation.label}</span>
                    <span className="muted">{observation.basis}</span>
                    <span className="observation-meta">
                      {observation.adapter && `${observation.adapter} · `}
                      {observation.external_ref && `${observation.external_ref} · `}
                      läst {formatDateTime(observation.retrieved_at)}
                      {observation.content_sha256 && ` · ${observation.content_sha256.slice(0, 16)}…`}
                    </span>
                    {observation.document_id && (
                      <button type="button" className="link" onClick={() => onOpenDocument?.(observation.document_id, 1)}>
                        Öppna filen
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            {invoice && (
              <p className="muted case-provenance">
                Ögonblicksbilden lästes {formatDateTime(invoice.retrieved_at)} ur{' '}
                <code>{invoice.source_dataset}</code>, referens <code>{invoice.external_ref}</code>,
                hash <code>{invoice.content_sha256.slice(0, 24)}…</code>
              </p>
            )}
          </div>

          {sourceEvent && (
            <div className="case-panel">
              <h4><Mail size={15} /> Mejlet fakturan kom med</h4>
              <p className="case-mail-meta">
                {sourceEvent.origin_display
                  ? `${sourceEvent.origin_display} <${sourceEvent.origin}>`
                  : sourceEvent.origin}
                {' · '}{formatDateTime(sourceEvent.occurred_at || sourceEvent.received_at)}
              </p>
              <p className="case-mail-subject"><strong>{sourceEvent.subject || '(utan ämne)'}</strong></p>
              {sourceEvent.body_text && <pre className="case-mail-body">{sourceEvent.body_text}</pre>}
            </div>
          )}
        </section>

        {/* ---- what the product thinks ---- */}
        <section className="case-column analysis">
          <div className="case-panel">
            <div className="case-panel-head">
              <h4><Sparkles size={15} /> Granskning mot föreningens dokument</h4>
            </div>
            {documentFindings.length === 0 ? (
              <p className="muted">
                Ingen granskning mot dokumenten har körts för den här fakturan.
                {isAdmin && ' Använd "Läs om och granska" ovan.'}
              </p>
            ) : documentFindings.map((finding) => (
              <Finding
                key={finding.id}
                finding={finding}
                brfId={brfId}
                busy={busy}
                canDecide={isAdmin}
                aliasConfirmed={Boolean(aliasConfirmed[finding.id])}
                onDecide={(id, status, note) => run(
                  () => integrationsApi.decideFinding(brfId, id, { status, note }),
                  () => setNotice('Ställningstagandet är sparat.'),
                )}
                onOpenCitation={onOpenCitation}
                onConfirmAlias={(f, note) => run(
                  () => integrationsApi.addSupplierAlias(brfId, {
                    invoice_name: f.alias_proposal.invoice_name,
                    document_name: f.alias_proposal.document_name,
                    note,
                  }),
                  () => {
                    setAliasConfirmed((current) => ({ ...current, [finding.id]: true }));
                    setNotice('Namnen är bekräftade. Kör om granskningen för att använda dem.');
                  },
                )}
                onRerun={() => run(
                  () => invoicesApi.refresh(brfId, kase.id),
                  () => setNotice('Granskningen är omkörd.'),
                )}
                /* Taking work on changes nothing about the finding: the task
                   is its own record, and the case says where it went. */
                onTaskCreated={(task) => setNotice(
                  `Uppgift skapad: ${task.title}. Ansvarig: ${task.responsible || 'ej utsedd'}.`
                  + ' Den ligger under Uppgifter. Fyndet är oförändrat.',
                )}
              />
            ))}
          </div>

          <div className="case-panel">
            <div className="case-panel-head">
              <h4><History size={15} /> Jämfört med föreningens tidigare fakturor</h4>
            </div>
            <p className="muted case-history-note">
              De här fynden bygger på fakturor föreningen redan läst in — inte på ett
              dokument. Därför saknar de citat, och det är avsiktligt.
            </p>
            {historyFindings.length === 0 ? (
              <p className="muted">Ingen historikjämförelse har körts ännu.</p>
            ) : historyFindings.map((finding) => (
              <Finding
                key={finding.id}
                finding={finding}
                brfId={brfId}
                busy={busy}
                canDecide={isAdmin}
                aliasConfirmed={false}
                onDecide={(id, status, note) => run(
                  () => integrationsApi.decideFinding(brfId, id, { status, note }),
                  () => setNotice('Ställningstagandet är sparat.'),
                )}
                onOpenCitation={onOpenCitation}
                onConfirmAlias={() => {}}
                onRerun={() => run(
                  () => invoicesApi.refresh(brfId, kase.id),
                  () => setNotice('Granskningen är omkörd.'),
                )}
                onTaskCreated={(task) => setNotice(
                  `Uppgift skapad: ${task.title}. Fyndet är oförändrat.`,
                )}
              />
            ))}
          </div>
        </section>

        {/* ---- what people did ---- */}
        <section className="case-column work">
          <div className="case-panel">
            <ReviewStatusForm
              caseData={kase}
              labels={labels}
              busy={busy}
              canDecide={isAdmin}
              onSave={(change) => run(
                () => invoicesApi.update(brfId, kase.id, change),
                () => setNotice('Granskningsläget är sparat. Ingenting ändrades i ekonomisystemet.'),
              )}
            />
          </div>

          <div className="case-panel">
            <h4><User size={15} /> Ansvarig</h4>
            <p className="case-responsible-current">{kase.responsible || 'ej utsedd'}</p>
            {isAdmin && (
              <div className="case-responsible-form">
                <input
                  type="text"
                  value={responsible}
                  disabled={busy}
                  placeholder="Vem tittar på den här?"
                  aria-label="Ansvarig"
                  onChange={(e) => setResponsible(e.target.value)}
                />
                <button
                  type="button"
                  disabled={busy || responsible.trim() === (kase.responsible || '')}
                  onClick={() => run(
                    () => invoicesApi.update(brfId, kase.id, { responsible: responsible.trim() }),
                    () => setNotice('Ansvarig är sparad.'),
                  )}
                >
                  Spara
                </button>
              </div>
            )}
          </div>

          <div className="case-panel">
            <h4><MessageSquare size={15} /> Kommentarer och frågor</h4>
            {kase.comments.length === 0 && <p className="muted">Ingen har skrivit något ännu.</p>}
            <ul className="case-comments">
              {kase.comments.map((entry) => (
                <li key={entry.id}>
                  <p>{entry.note}</p>
                  <span className="muted">{entry.by} · {formatDateTime(entry.at)}</span>
                </li>
              ))}
            </ul>
            {isAdmin && (
              <div className="case-comment-form">
                <textarea
                  rows={2}
                  value={comment}
                  disabled={busy}
                  placeholder="Vad har ni gjort eller frågat om fakturan?"
                  aria-label="Ny kommentar"
                  onChange={(e) => setComment(e.target.value)}
                />
                <button
                  type="button"
                  disabled={busy || !comment.trim()}
                  onClick={() => run(
                    () => invoicesApi.comment(brfId, kase.id, comment.trim()),
                    () => { setComment(''); setNotice('Kommentaren är sparad.'); },
                  )}
                >
                  Kommentera
                </button>
              </div>
            )}
          </div>

          <div className="case-panel">
            <h4><ClipboardList size={15} /> Uppgifter om den här fakturan</h4>
            {tasks.length === 0 ? (
              <p className="muted">Ingen uppgift är skapad ur ärendet.</p>
            ) : (
              <ul className="case-tasks">
                {tasks.map((task) => (
                  <li key={task.id}>
                    <strong>{task.title}</strong>
                    <span className="muted">
                      {task.status_label} · {task.responsible || 'ej utsedd'}
                      {task.due_date ? ` · ${task.due_date}` : ' · inget datum'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <CreateTask
              brfId={brfId}
              canCreate={isAdmin}
              originKind="invoice_case"
              originRef={kase.id}
              suggestedTitle={`${kase.supplier_name} ${kase.invoice_number || ''}`.trim()}
              suggestedResponsible={kase.responsible}
              openLabel="Skapa uppgift ur fakturan"
              onCreated={() => run(
                async () => null,
                () => setNotice('Uppgiften är skapad och syns i ärendets historik.'),
              )}
            />
          </div>

          <div className="case-panel">
            <h4><Building2 size={15} /> Om {supplier.supplier_name || 'leverantören'}</h4>
            <dl className="case-fields">
              <div><dt>Inlästa fakturor</dt><dd>{supplier.invoice_count}</dd></div>
              <div>
                <dt>Beloppsspann</dt>
                <dd>
                  {supplier.amount_low
                    ? `${formatAmount(supplier.amount_low, supplier.currency)} – ${formatAmount(supplier.amount_high, supplier.currency)}`
                    : '—'}
                </dd>
              </div>
              <div><dt>Organisationsnummer</dt><dd>{supplier.org_numbers.join(', ') || '—'}</dd></div>
              <div><dt>Tidigare avvikelser</dt><dd>{supplier.deviation_count}</dd></div>
              <div><dt>Brukar hanteras av</dt><dd>{supplier.responsibles.join(', ') || '—'}</dd></div>
            </dl>

            {supplier.previous.length > 0 && (
              <>
                <h5>Tidigare fakturor</h5>
                <ul className="case-previous">
                  {supplier.previous.map((row) => (
                    <li key={row.id}>
                      <button type="button" className="link" onClick={() => onOpenCase?.(row.id)}>
                        {row.invoice_number || 'utan nummer'} · {row.invoice_date || 'utan datum'}
                      </button>
                      <span>{formatAmount(row.total_amount, row.currency)}</span>
                      <span className="muted">{row.review_status_label}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {supplier.documents.length > 0 && (
              <>
                <h5>Dokument granskningen har citerat</h5>
                <ul className="case-supplier-docs">
                  {supplier.documents.map((doc) => (
                    <li key={doc.id}>
                      <button type="button" className="link" onClick={() => onOpenDocument?.(doc.id, 1)}>
                        {doc.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {supplier.aliases.length > 0 && (
              <>
                <h5>Bekräftade leverantörsnamn</h5>
                <ul className="case-aliases">
                  {supplier.aliases.map((alias) => (
                    <li key={alias.id}>
                      <span>
                        <strong>{alias.invoice_name}</strong> är samma som{' '}
                        <strong>{alias.document_name}</strong>
                      </span>
                      <span className="muted">{alias.created_by} · {formatDateTime(alias.created_at)}</span>
                      {isAdmin && (
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={`Ta bort ${alias.invoice_name} = ${alias.document_name}`}
                          onClick={() => run(
                            () => integrationsApi.deleteSupplierAlias(brfId, alias.id),
                            () => setNotice('Bekräftelsen är borttagen.'),
                          )}
                        >
                          <Trash2 size={13} /> Ta bort
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="case-panel">
            <Timeline events={kase.timeline} />
          </div>
        </section>
      </div>
    </div>
  );
}
