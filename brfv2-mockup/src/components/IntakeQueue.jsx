import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Archive,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  HelpCircle,
  Inbox,
  Link2,
  ListTodo,
  Loader2,
  Mail,
  MessageCircleQuestion,
  Paperclip,
  Quote,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import { intakeApi, integrationsApi } from '../api';
import './IntakeQueue.css';

/**
 * The review queue for incoming post.
 *
 * Not an inbox. An inbox answers "what is in the mailbox"; this answers the
 * five questions a board actually has — what arrived, why it matters, what it
 * connects to, whether anyone has to act, and what should be kept — and every
 * one of those answers is presented as what it is.
 *
 * Three rules run through the whole screen:
 *
 * 1. **A reading is never shown as a fact.** What the app believes sits under
 *    a heading that says so, next to the words it read it from. A category the
 *    engine guessed and one a person confirmed are visibly different, and the
 *    engine's guess stays visible after the correction.
 * 2. **Nothing leaves this screen without a human.** Every outcome is a button
 *    somebody presses, taking anything into the archive requires a written
 *    reason, and the screen says out loud that the mailbox is not touched by
 *    any of it.
 * 3. **What was decided is shown as where it went.** A resolved card says "det
 *    blev uppgift X" with the record it produced, not "hanterad".
 */

const CATEGORY_ICON = {
  invoice: FileText,
  contract_or_quote: FileText,
  authority_or_manager: AlertTriangle,
  decision_or_approval: CheckCircle2,
  question_awaiting_reply: MessageCircleQuestion,
  information: Inbox,
  unclear: HelpCircle,
};

const SIGNAL_LABEL = {
  date: 'Datum',
  deadline: 'Beräknat datum',
  amount: 'Belopp',
  supplier: 'Avsändare',
  decision: 'Beslut',
  question: 'Fråga',
  renewal: 'Löptid',
  reference: 'Ordval',
};

const RELATED_ICON = {
  document: FileText,
  invoice: FileText,
  source_event: Mail,
  task: ListTodo,
  watch: CalendarClock,
};

const SOURCE_LABEL = {
  subject: 'ämnesraden',
  body: 'mejltexten',
  attachment: 'en bilaga',
};

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

function formatDate(iso) {
  if (!iso) return '—';
  return String(iso).slice(0, 10);
}

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`intake-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

/**
 * The fetch bar: when we last looked, what came in, and what could not.
 *
 * The skipped list is not an error display. The `.eml` format refuses a whole
 * message rather than dropping one attachment, and a queue that stayed silent
 * about those would let an operator believe the queue is the mailbox.
 */
function FetchBar({ mailbox, connected, busy, onFetch, lastResult }) {
  return (
    <div className="intake-fetch">
      <div className="fetch-state">
        <h4><Mail size={15} /> Ansluten brevlåda</h4>
        {connected ? (
          <p className="muted">
            {mailbox?.hasFetched
              ? `Senast hämtat ${formatDateTime(mailbox.last_fetched_at)} — ${mailbox.last_new_count} nya.`
              : 'Aldrig hämtat. Första hämtningen tar in det som finns i mappen.'}
            {' '}Hämtningen frågar efter det som kommit sedan förra gången. Inget markeras,
            flyttas eller raderas i brevlådan.
          </p>
        ) : (
          <p className="muted">
            Ingen brevlåda är ansluten. Det behövs inte — en <code>.eml</code>-fil kan
            importeras för hand, och kön fungerar likadant. Se <strong>Anslutningar</strong>.
          </p>
        )}
        {mailbox?.last_error && (
          <p className="fetch-error">
            Senaste försöket gick inte igenom: {mailbox.last_error}. Läget är oförändrat —
            nästa hämtning börjar om från samma punkt.
          </p>
        )}
      </div>
      <button type="button" className="fetch-button" disabled={busy || !connected} onClick={onFetch}>
        {busy ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Hämta nytt
      </button>

      {lastResult && (
        <div className="fetch-result">
          <p>
            <strong>{lastResult.new}</strong> nya meddelanden togs in
            {lastResult.alreadyKnown > 0 && `, ${lastResult.alreadyKnown} fanns redan i kön`}
            {lastResult.seen === 0 && ' — inget nytt sedan förra hämtningen'}.
          </p>
          {lastResult.skipped?.length > 0 && (
            <details className="fetch-skipped">
              <summary>
                {lastResult.skipped.length} meddelande(n) kunde inte tas in — de ligger kvar i brevlådan
              </summary>
              <ul>
                {lastResult.skipped.map((row) => (
                  <li key={row.external_ref}>
                    <strong>{row.subject || '(utan ämne)'}</strong> från {row.sender}
                    <span className="muted"> — {row.reason}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

/** What the app believes, with the words it believes it from. */
function TriagePanel({ thread, categories, busy, onConfirm }) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState(thread.category);
  const [note, setNote] = useState('');

  useEffect(() => { setChosen(thread.category); }, [thread.category]);

  const latest = thread.events[thread.events.length - 1];
  const confirmation = latest?.triage_confirmation;

  return (
    <div className="triage">
      <div className="triage-head">
        <h5><Sparkles size={14} /> Vad det ser ut att gälla</h5>
        <span className="triage-by">
          {thread.suggested_by ? `bedömt av ${thread.suggested_by}` : 'ingen bedömning'}
        </span>
      </div>

      {thread.headline && <p className="triage-headline">{thread.headline}</p>}
      {thread.why_it_matters && <p className="triage-why">{thread.why_it_matters}</p>}
      {thread.action_hint && (
        <p className="triage-action"><Clock size={13} /> {thread.action_hint}</p>
      )}
      {thread.uncertainty && (
        <p className="triage-uncertainty"><HelpCircle size={13} /> {thread.uncertainty}</p>
      )}

      {thread.signals?.length > 0 && (
        <div className="triage-signals">
          <h6>Läst ur meddelandet</h6>
          <ul>
            {thread.signals.map((signal, i) => (
              <li key={`${signal.kind}-${signal.value}-${i}`}>
                <span className={`signal-kind ${signal.kind}`}>
                  {SIGNAL_LABEL[signal.kind] || signal.kind}
                </span>
                <span className="signal-value">{signal.value}</span>
                <span className="muted"> ur {SOURCE_LABEL[signal.source] || signal.source}</span>
                <q className="signal-quote"><Quote size={11} /> {signal.quote}</q>
              </li>
            ))}
          </ul>
        </div>
      )}

      {thread.related?.length > 0 && (
        <div className="triage-related">
          <h6><Link2 size={13} /> Kan höra ihop med</h6>
          <ul>
            {thread.related.map((record, i) => {
              const Icon = RELATED_ICON[record.kind] || FileText;
              return (
                <li key={`${record.kind}-${record.ref_id}-${i}`}>
                  <Icon size={13} /> <strong>{record.label}</strong>
                  <span className="muted"> — {record.basis}</span>
                  <span className="badge proposed">förslag</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="triage-category">
        {confirmation ? (
          <p className="category-confirmed">
            <CheckCircle2 size={13} /> {confirmation.confirmed_by} har satt kategorin till{' '}
            <strong>{categories[confirmation.category] || confirmation.category}</strong>
            {confirmation.note ? ` — ${confirmation.note}` : ''}.
            {' '}Förslaget var <em>{categories[thread.category] || thread.category}</em> och står kvar.
          </p>
        ) : (
          <>
            <button type="button" className="category-toggle" onClick={() => setOpen(!open)}>
              {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Rätta kategorin
            </button>
            {open && (
              <div className="category-form">
                <label>
                  Kategori
                  <select value={chosen} onChange={(e) => setChosen(e.target.value)}>
                    {Object.entries(categories).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </label>
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Anteckning (valfri)"
                  aria-label="Anteckning om kategorin"
                />
                <button
                  type="button"
                  disabled={busy || !latest}
                  onClick={() => onConfirm(latest.id, chosen, note.trim())}
                >
                  Spara kategorin
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * The five outcomes, and the combinations the product model allows.
 *
 * "Redan hanterat" and "Inte relevant" are exclusive and the form enforces it
 * here as well as in the backend — a record that says both "inte relevant" and
 * "här är uppgiften jag gjorde av den" is one nobody can act on.
 */
function ResolveForm({ event, resolutions, busy, onResolve }) {
  const [chosen, setChosen] = useState([]);
  const [note, setNote] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [task, setTask] = useState({ title: '', responsible: '', due_date: '' });
  const [watch, setWatch] = useState({ due_date: '', kind: 'stated_deadline', responsible: '' });

  const exclusive = ['already_handled', 'not_relevant'];
  const suggestedDates = (event.triage?.signals || [])
    .filter((s) => s.kind === 'date' || s.kind === 'deadline')
    .map((s) => s.value);

  function toggle(kind) {
    setChosen((current) => {
      if (current.includes(kind)) return current.filter((k) => k !== kind);
      if (exclusive.includes(kind)) return [kind];
      return [...current.filter((k) => !exclusive.includes(k)), kind];
    });
  }

  function toggleAttachment(id) {
    setAttachments((current) => (
      current.includes(id) ? current.filter((a) => a !== id) : [...current, id]
    ));
  }

  const needsNote = chosen.includes('take_in');
  const canSubmit = chosen.length > 0 && (!needsNote || note.trim().length > 0) && !busy;

  return (
    <div className="resolve">
      <h5>Vad ska hända med den här posten?</h5>
      <div className="resolve-options">
        {Object.entries(resolutions).map(([kind, label]) => (
          <label key={kind} className={chosen.includes(kind) ? 'chosen' : ''}>
            <input
              type="checkbox"
              checked={chosen.includes(kind)}
              onChange={() => toggle(kind)}
              disabled={busy}
            />
            {label}
          </label>
        ))}
      </div>

      {chosen.includes('take_in') && (
        <div className="resolve-section">
          <p className="muted">
            Meddelandets text bevaras som ett dokument i föreningens arkiv — sökbart, och
            citerbart tillbaka till avsändare och datum. Bilagor följer inte med automatiskt:
            kryssa för de som hör till underlaget.
          </p>
          {event.attachments.length > 0 && (
            <ul className="resolve-attachments">
              {event.attachments.map((attachment) => (
                <li key={attachment.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={attachments.includes(attachment.id)}
                      disabled={busy || attachment.archived}
                      onChange={() => toggleAttachment(attachment.id)}
                    />
                    <Paperclip size={12} /> {attachment.filename}
                  </label>
                  {attachment.archived && <span className="badge confirmed">redan i arkivet</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {chosen.includes('create_task') && (
        <div className="resolve-section">
          <label>
            Rubrik
            <input
              type="text"
              value={task.title}
              onChange={(e) => setTask({ ...task, title: e.target.value })}
              placeholder={event.subject || 'Vad ska göras?'}
            />
          </label>
          <label>
            Ansvarig
            <input
              type="text"
              value={task.responsible}
              onChange={(e) => setTask({ ...task, responsible: e.target.value })}
              placeholder="ej utsedd"
            />
          </label>
          <label>
            Klart senast
            <input
              type="date"
              value={task.due_date}
              onChange={(e) => setTask({ ...task, due_date: e.target.value })}
            />
          </label>
        </div>
      )}

      {chosen.includes('monitor') && (
        <div className="resolve-section">
          <label>
            Vad bevakas
            <select value={watch.kind} onChange={(e) => setWatch({ ...watch, kind: e.target.value })}>
              <option value="stated_deadline">Ett datum ur posten</option>
              <option value="expected_reply">Ett svar vi väntar på</option>
            </select>
          </label>
          <label>
            Datum
            <input
              type="date"
              value={watch.due_date}
              onChange={(e) => setWatch({ ...watch, due_date: e.target.value })}
            />
          </label>
          {suggestedDates.length > 0 && (
            <p className="date-suggestions">
              Lästa ur meddelandet:{' '}
              {[...new Set(suggestedDates)].map((iso) => (
                <button
                  key={iso}
                  type="button"
                  className="date-chip"
                  onClick={() => setWatch({ ...watch, due_date: iso })}
                >
                  {iso}
                </button>
              ))}
            </p>
          )}
        </div>
      )}

      <label className="resolve-note">
        {needsNote ? 'Varför ska posten bevaras? (krävs)' : 'Anteckning (valfri)'}
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={needsNote ? 'Vad gör den till föreningens underlag?' : ''}
        />
      </label>

      <div className="resolve-actions">
        <button
          type="button"
          className="resolve-submit"
          disabled={!canSubmit}
          title={needsNote && !note.trim() ? 'Skriv först varför posten ska bevaras.' : undefined}
          onClick={() => onResolve(event.id, {
            outcomes: chosen,
            note: note.trim(),
            attachment_ids: attachments,
            task: chosen.includes('create_task') ? task : null,
            watch: chosen.includes('monitor') ? watch : null,
          })}
        >
          Spara beslutet
        </button>
        <span className="muted">
          Ingenting ändras i brevlådan. Meddelandet ligger kvar där det är.
        </span>
      </div>
    </div>
  );
}

/** One resolved card: what was decided, and which records it produced. */
function ResolutionSummary({ event, busy, onReopen, onOpenDocument }) {
  const { resolution } = event;
  if (!resolution) return null;
  return (
    <div className="resolution">
      <h5><CheckCircle2 size={14} /> Beslutat {formatDateTime(resolution.decided_at)} av {resolution.decided_by}</h5>
      <ul>
        {resolution.outcomes.map((outcome, i) => (
          <li key={`${outcome.kind}-${i}`}>
            <strong>{outcome.label}</strong>
            {outcome.ref_label && <span> — {outcome.ref_label}</span>}
            {outcome.kind === 'take_in' && outcome.ref_id && (
              <button type="button" className="link" onClick={() => onOpenDocument?.(outcome.ref_id, 1)}>
                Öppna dokumentet
              </button>
            )}
          </li>
        ))}
      </ul>
      {resolution.note && <p className="resolution-note">Anteckning: {resolution.note}</p>}
      <button type="button" className="reopen" disabled={busy} onClick={() => onReopen(event.id)}>
        <RotateCcw size={13} /> Öppna i kön igen
      </button>
      <p className="muted">
        Det som redan skapats står kvar — en uppgift som gjorts av posten är ett beslut i sig.
      </p>
    </div>
  );
}

function ThreadCard({
  thread, categories, resolutions, busy,
  onConfirm, onResolve, onReopen, onRetriage, onOpenDocument,
}) {
  const [expanded, setExpanded] = useState(!thread.resolved);
  const Icon = CATEGORY_ICON[thread.category] || Inbox;

  return (
    <article className={`thread ${thread.resolved ? 'resolved' : 'open'}`}>
      <button
        type="button"
        className="thread-head"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        <span className="thread-chevron">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <span className="thread-main">
          <span className="thread-subject">{thread.subject}</span>
          <span className="thread-meta">
            Senast från {thread.latest_sender_display || thread.latest_sender}
            {' · '}{formatDate(thread.first_at)} – {formatDate(thread.latest_at)}
            {' · '}{thread.message_count} meddelande{thread.message_count === 1 ? '' : 'n'}
            {' · '}{thread.attachment_count} bilag{thread.attachment_count === 1 ? 'a' : 'or'}
          </span>
        </span>
        <span className="thread-badges">
          <span className={`badge category ${thread.category}`}>
            <Icon size={12} /> {thread.category_label}
            {thread.category_confirmed && <CheckCircle2 size={11} aria-label="bekräftad av människa" />}
          </span>
          {thread.awaiting_reply && (
            <span className="badge awaiting">
              <MessageCircleQuestion size={12} /> ser ut att vänta svar
            </span>
          )}
          {thread.resolved
            ? <span className="badge done">avgjord</span>
            : <span className="badge open">{thread.open_count} att ta ställning till</span>}
        </span>
      </button>

      {expanded && (
        <div className="thread-body">
          <TriagePanel
            thread={thread}
            categories={categories}
            busy={busy}
            onConfirm={onConfirm}
          />

          <div className="thread-messages">
            <h5>Meddelanden i tråden</h5>
            {thread.events.map((event) => (
              <details key={event.id} className={`message ${event.resolution ? 'settled' : ''}`}>
                <summary>
                  <strong>{event.subject || '(utan ämne)'}</strong>
                  <span className="muted">
                    {' '}{event.origin_display ? `${event.origin_display} <${event.origin}>` : event.origin}
                    {' · '}{formatDateTime(event.occurred_at || event.received_at)}
                    {event.attachments.length > 0 && ` · ${event.attachments.length} bilaga(or)`}
                  </span>
                </summary>

                <dl className="message-provenance">
                  <div><dt>Mottaget av föreningen</dt><dd>{formatDateTime(event.received_at)}</dd></div>
                  <div><dt>Hur det kom hit</dt><dd>{event.provenance.method} / {event.provenance.adapter}</dd></div>
                  <div><dt>Importerat av</dt><dd>{event.provenance.imported_by}</dd></div>
                  <div><dt>Innehållshash</dt><dd><code>{event.content_sha256.slice(0, 24)}…</code></dd></div>
                </dl>

                {event.body_text && <pre className="message-body">{event.body_text}</pre>}

                {event.attachments.length > 0 && (
                  <ul className="message-attachments">
                    {event.attachments.map((attachment) => (
                      <li key={attachment.id}>
                        <button
                          type="button"
                          className="link"
                          disabled={!attachment.document_id}
                          onClick={() => onOpenDocument?.(attachment.document_id, 1)}
                        >
                          <Paperclip size={12} /> {attachment.filename}
                        </button>
                        <span className={`badge ${attachment.archived ? 'confirmed' : 'proposed'}`}>
                          {attachment.archived ? 'i föreningens arkiv' : 'material under granskning'}
                        </span>
                        {attachment.reused_existing_document && (
                          <span className="badge dedup">samma fil fanns redan — länkad</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}

                {event.preserved_document_id && (
                  <p className="message-preserved">
                    <Archive size={13} /> Texten är bevarad som dokument
                    {' '}({event.preserved_by}, {formatDateTime(event.preserved_at)})
                    {event.preservation_note ? ` — ${event.preservation_note}` : ''}.
                    <button
                      type="button"
                      className="link"
                      onClick={() => onOpenDocument?.(event.preserved_document_id, 1)}
                    >
                      Öppna
                    </button>
                  </p>
                )}

                {event.resolution ? (
                  <ResolutionSummary
                    event={event}
                    busy={busy}
                    onReopen={onReopen}
                    onOpenDocument={onOpenDocument}
                  />
                ) : (
                  <ResolveForm
                    event={event}
                    resolutions={resolutions}
                    busy={busy}
                    onResolve={onResolve}
                  />
                )}

                <button
                  type="button"
                  className="retriage"
                  disabled={busy}
                  onClick={() => onRetriage(event.id)}
                >
                  <RefreshCw size={12} /> Läs om meddelandet
                </button>
              </details>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

export default function IntakeQueue({
  brfId, isAdmin = false, mailboxConnected = false, format, onOpenDocument, onChanged,
}) {
  const [queue, setQueue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [lastFetch, setLastFetch] = useState(null);
  const [filter, setFilter] = useState('open');

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      setQueue(await intakeApi.queue(brfId));
      setError('');
    } catch (err) {
      setError(err.message || 'Kön kunde inte hämtas.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  const run = useCallback(async (work, onDone) => {
    setBusy(true);
    setError('');
    try {
      const result = await work();
      await refresh();
      onChanged?.();
      onDone?.(result);
    } catch (err) {
      setError(err.message || 'Åtgärden gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }, [refresh, onChanged]);

  const handleFetch = () => run(
    () => intakeApi.fetch(brfId),
    (result) => {
      setLastFetch(result);
      setNotice(
        result.new > 0
          ? `${result.new} nya meddelanden i kön.`
          : 'Inget nytt sedan förra hämtningen.',
      );
    },
  );

  const handleImportFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await run(
      () => integrationsApi.importSourceEvent(brfId, file),
      (created) => setNotice(`Importerat: ${created.subject || file.name}`),
    );
  };

  const handleResolve = (eventId, decision) => run(
    () => intakeApi.resolve(brfId, eventId, decision),
    (settled) => setNotice(
      `Beslut sparat: ${settled.resolution.outcomes.map((o) => o.label).join(', ')}.`,
    ),
  );

  const handleConfirm = (eventId, category, note) => run(
    () => intakeApi.confirmCategory(brfId, eventId, category, note),
    () => setNotice('Kategorin är satt. Förslaget står kvar bredvid.'),
  );

  const handleReopen = (eventId) => run(
    () => intakeApi.reopen(brfId, eventId),
    () => setNotice('Posten ligger i kön igen. Det som skapats står kvar.'),
  );

  const handleRetriage = (eventId) => run(
    () => intakeApi.retriage(brfId, eventId),
    () => setNotice('Meddelandet är omläst mot arkivet som det ser ut nu.'),
  );

  const threads = useMemo(() => {
    const all = queue?.threads || [];
    if (filter === 'open') return all.filter((t) => !t.resolved);
    if (filter === 'awaiting') return all.filter((t) => t.awaiting_reply);
    return all;
  }, [queue, filter]);

  const counts = queue?.counts || {};

  return (
    <div className="intake">
      <div className="intake-intro">
        <h3><Inbox size={18} /> Inkommande post</h3>
        <p>
          Brevlådan är råmaterial. Det här är en granskningskö: ingenting blir en del av
          föreningens arkiv, en uppgift eller en bevakning förrän någon här bestämmer det —
          och ingenting ändras i brevlådan när ni gör det.
        </p>
      </div>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {isAdmin && (
        <>
          <FetchBar
            mailbox={queue?.mailbox}
            connected={mailboxConnected}
            busy={busy}
            onFetch={handleFetch}
            lastResult={lastFetch}
          />
          <div className="intake-manual">
            <input
              type="file"
              accept=".eml,message/rfc822"
              onChange={handleImportFile}
              className="hidden-file-input"
              id="intake-eml-import"
            />
            <label htmlFor="intake-eml-import" className={`import-button ${busy ? 'busy' : ''}`}>
              {busy ? <Loader2 size={15} className="spin" /> : <Upload size={15} />}
              Importera en .eml-fil
            </label>
            {format?.mail && (
              <span className="muted">
                Tas emot: {format.mail.attachmentTypes.join(', ')} som bilaga, högst{' '}
                {format.mail.maxAttachments} stycken. Allt annat avvisas i sin helhet — inget
                halvimporteras.
              </span>
            )}
          </div>
        </>
      )}

      <div className="intake-counts" role="group" aria-label="Filtrera kön">
        <button
          type="button"
          className={filter === 'open' ? 'active' : ''}
          aria-pressed={filter === 'open'}
          onClick={() => setFilter('open')}
        >
          Att ta ställning till <span className="pill">{counts.openThreads || 0}</span>
        </button>
        <button
          type="button"
          className={filter === 'awaiting' ? 'active' : ''}
          aria-pressed={filter === 'awaiting'}
          onClick={() => setFilter('awaiting')}
        >
          Väntar svar <span className="pill">{counts.awaitingReply || 0}</span>
        </button>
        <button
          type="button"
          className={filter === 'all' ? 'active' : ''}
          aria-pressed={filter === 'all'}
          onClick={() => setFilter('all')}
        >
          Alla trådar <span className="pill">{counts.threads || 0}</span>
        </button>
        <button type="button" className="refresh" onClick={refresh} disabled={loading || busy}>
          <RefreshCw size={14} /> Uppdatera
        </button>
      </div>

      {loading && <p className="intake-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>}

      {!loading && threads.length === 0 && (
        <p className="empty">
          {filter === 'open'
            ? 'Ingenting väntar på ett beslut.'
            : 'Inga trådar matchar filtret.'}
        </p>
      )}

      {!loading && threads.map((thread) => (
        <ThreadCard
          key={thread.key}
          thread={thread}
          categories={queue.categoryLabels}
          resolutions={queue.resolutionLabels}
          busy={busy || !isAdmin}
          onConfirm={handleConfirm}
          onResolve={handleResolve}
          onReopen={handleReopen}
          onRetriage={handleRetriage}
          onOpenDocument={onOpenDocument}
        />
      ))}
    </div>
  );
}
