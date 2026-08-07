import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
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
  Paperclip,
  RefreshCw,
  RotateCcw,
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
 *
 * The layout is master–detail, and the reason is the work rather than the
 * fashion: a board member goes through a queue item by item, and the decision
 * form is long — five outcomes, three sub-forms, a required reason. As an
 * accordion inside the list, opening one item pushed every other item off the
 * screen and the reviewer lost their place in the only thing that tells them
 * how much is left. The list stays put on the left; what is being decided
 * occupies the right.
 *
 * Reading order in the detail pane is the argument: **what arrived** first, the
 * **machine's reading of it** second (under a heading that says whose reading
 * it is), and the **decision** last. A reader should meet the message before
 * they meet the interpretation of it.
 */

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
function FetchBar({ mailbox, connected, busy, onFetch, onImportFile, format, lastResult }) {
  return (
    <div className="intake-source">
      <div className="intake-source-row">
        <span className="intake-source-state">
          <Mail size={14} />
          {connected ? (
            <span>
              Ansluten brevlåda
              {mailbox?.hasFetched
                ? ` · senast ${formatDateTime(mailbox.last_fetched_at)} · ${mailbox.last_new_count} nya`
                : ' · aldrig hämtat'}
            </span>
          ) : (
            <span>
              Ingen brevlåda är ansluten · importera <code>.eml</code> eller se Anslutningar
            </span>
          )}
        </span>

        <span className="intake-source-actions">
          <input
            type="file"
            accept=".eml,message/rfc822"
            onChange={onImportFile}
            className="hidden-file-input"
            id="intake-eml-import"
          />
          <label htmlFor="intake-eml-import" className={`import-button ${busy ? 'busy' : ''}`}>
            {busy ? <Loader2 size={14} className="spin" /> : <Upload size={14} />}
            Importera en .eml-fil
          </label>
          <button type="button" className="fetch-button" disabled={busy || !connected} onClick={onFetch}>
            {busy ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} Hämta nytt
          </button>
        </span>
      </div>

      {format?.mail && (
        <details className="intake-format-disclosure">
          <summary>Vilka bilagor tas emot</summary>
          <p className="muted intake-format-note">
            Tas emot: {format.mail.attachmentTypes.join(', ')} som bilaga, högst{' '}
            {format.mail.maxAttachments} stycken. Allt annat avvisas i sin helhet — inget
            halvimporteras.
          </p>
        </details>
      )}

      {mailbox?.last_error && (
        <p className="fetch-error">
          Senaste försöket gick inte igenom: {mailbox.last_error}. Läget är oförändrat —
          nästa hämtning börjar om från samma punkt.
        </p>
      )}

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

/** One row in the queue: enough to choose from, never enough to decide from. */
function ThreadRow({ thread, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`thread-row${selected ? ' selected' : ''}${thread.resolved ? ' resolved' : ''}`}
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelect(thread.key)}
    >
      <span className="thread-row-top">
        <span className="thread-subject">{thread.subject}</span>
        {thread.resolved
          ? <span className="thread-row-state settled"><CheckCircle2 size={12} /> Avgjord</span>
          : <span className="thread-row-state open">{thread.open_count}</span>}
      </span>
      <span className="thread-meta">
        {thread.latest_sender_display || thread.latest_sender}
        {' · '}{formatDate(thread.latest_at)}
      </span>
    </button>
  );
}

// Enough readings to judge the reading by. A message whose PDF attachment was
// parsed can produce a dozen, each quoting a paragraph, and the decision must
// not sit below a wall of them.
const SIGNALS_SHOWN = 4;

/** What the app believes, with the words it believes it from. */
function ReadingPanel({ thread, categories, busy, onConfirm }) {
  const [open, setOpen] = useState(false);
  const [allSignals, setAllSignals] = useState(false);
  const [chosen, setChosen] = useState(thread.category);
  const [note, setNote] = useState('');

  useEffect(() => { setChosen(thread.category); }, [thread.category]);

  const latest = thread.events[thread.events.length - 1];
  const confirmation = latest?.triage_confirmation;

  return (
    <section className="detail-section reading">
      <div className="detail-section-head">
        <h4>Vad det ser ut att gälla</h4>
        {/* Who produced the reading, always — "regelmotor" and "regelmotor +
            språkmodell" are different assurances a reader is entitled to. */}
        <span className="reading-by">
          {thread.suggested_by ? `bedömt av ${thread.suggested_by}` : 'ingen bedömning'}
        </span>
      </div>

      {thread.headline && <p className="reading-headline">{thread.headline}</p>}
      {thread.why_it_matters && <p className="reading-why">{thread.why_it_matters}</p>}
      {thread.action_hint && (
        <p className="reading-action"><Clock size={13} /> {thread.action_hint}</p>
      )}
      {thread.uncertainty && (
        <p className="reading-uncertainty"><HelpCircle size={13} /> {thread.uncertainty}</p>
      )}

      {thread.signals?.length > 0 && (
        <div className="reading-signals">
          <h6>
            <span>Läst ur meddelandet</span>
            {thread.signals.length > SIGNALS_SHOWN && (
              <span className="h6-count">{thread.signals.length}</span>
            )}
          </h6>
          <ul>
            {(allSignals ? thread.signals : thread.signals.slice(0, SIGNALS_SHOWN)).map((signal, i) => (
              <li key={`${signal.kind}-${signal.value}-${i}`}>
                <span className="signal-kind">
                  {SIGNAL_LABEL[signal.kind] || signal.kind}
                </span>
                <span className="signal-value">{signal.value}</span>
                <span className="muted"> ur {SOURCE_LABEL[signal.source] || signal.source}</span>
                <q className="signal-quote">{signal.quote}</q>
              </li>
            ))}
          </ul>
          {thread.signals.length > SIGNALS_SHOWN && (
            <button type="button" className="signals-more" onClick={() => setAllSignals(!allSignals)}>
              {allSignals
                ? <><ChevronDown size={13} /> Visa färre avläsningar</>
                : <><ChevronRight size={13} /> Visa alla {thread.signals.length} avläsningar</>}
            </button>
          )}
        </div>
      )}

      {thread.related?.length > 0 && (
        <div className="reading-related">
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

      <div className="reading-category">
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
                <label>
                  Anteckning (valfri)
                  <input
                    type="text"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    aria-label="Anteckning om kategorin"
                  />
                </label>
                <button
                  type="button"
                  className="category-save"
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
    </section>
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
      <div className="resolution-foot">
        <button type="button" className="reopen" disabled={busy} onClick={() => onReopen(event.id)}>
          <RotateCcw size={13} /> Öppna i kön igen
        </button>
        <span className="muted">
          Det som redan skapats står kvar — en uppgift som gjorts av posten är ett beslut i sig.
        </span>
      </div>
    </div>
  );
}

/** One message: the thing that actually arrived. */
function Message({ event, busy, onRetriage, onOpenDocument }) {
  return (
    <article className={`message ${event.resolution ? 'settled' : ''}`}>
      <header className="message-head">
        <h5>{event.subject || '(utan ämne)'}</h5>
        <span className="message-from">
          {event.origin_display ? `${event.origin_display} <${event.origin}>` : event.origin}
          {' · '}{formatDateTime(event.occurred_at || event.received_at)}
          {event.attachments.length > 0 && ` · ${event.attachments.length} bilaga(or)`}
        </span>
      </header>

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

      <div className="message-foot">
        {/* Provenance is what makes the message checkable against the mailbox
            it came from. Present, and out of the way until it is wanted. */}
        <details className="message-provenance-toggle">
          <summary>Härkomst</summary>
          <dl className="message-provenance">
            <div><dt>Mottaget av föreningen</dt><dd>{formatDateTime(event.received_at)}</dd></div>
            <div><dt>Hur det kom hit</dt><dd>{event.provenance.method} / {event.provenance.adapter}</dd></div>
            <div><dt>Importerat av</dt><dd>{event.provenance.imported_by}</dd></div>
            <div><dt>Innehållshash</dt><dd><code>{event.content_sha256.slice(0, 24)}…</code></dd></div>
          </dl>
        </details>
        <button
          type="button"
          className="retriage"
          disabled={busy}
          onClick={() => onRetriage(event.id)}
        >
          <RefreshCw size={12} /> Läs om meddelandet
        </button>
      </div>
    </article>
  );
}

/** The selected thread, in full: what arrived, what was read, what to do. */
function ThreadDetail({
  thread, categories, resolutions, busy,
  onConfirm, onResolve, onReopen, onRetriage, onOpenDocument,
}) {
  return (
    <div className="thread-detail">
      <header className="detail-head">
        {/* Subject once. Dates, sender, category and open-count live on the
            list row or the message — restating them here is two panes saying
            one thing before any new information appears. */}
        <h3>{thread.subject}</h3>
      </header>

      <section className="detail-section messages">
        <div className="detail-section-head">
          <h4>Meddelanden i tråden</h4>
        </div>
        {thread.events.map((event) => (
          <Message
            key={event.id}
            event={event}
            busy={busy}
            onRetriage={onRetriage}
            onOpenDocument={onOpenDocument}
          />
        ))}
      </section>

      <ReadingPanel
        thread={thread}
        categories={categories}
        busy={busy}
        onConfirm={onConfirm}
      />

      {thread.events.map((event) => (
        <section className="detail-section decision" key={`decision-${event.id}`}>
          {thread.events.length > 1 && (
            <p className="decision-for">Gäller: {event.subject || '(utan ämne)'}</p>
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
        </section>
      ))}
    </div>
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
  const [selectedKey, setSelectedKey] = useState(null);

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

  // The selection follows the list rather than being stored against it: a
  // refresh, a filter change or a decision that empties the queue must never
  // leave the detail pane showing a thread the list no longer contains.
  const selected = threads.find((t) => t.key === selectedKey) || threads[0] || null;

  const counts = queue?.counts || {};

  return (
    <div className="intake">
      {/* The mailbox promise lives beside Spara beslutet — not as a page
          manifesto that burns the first viewport every session. */}
      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {isAdmin && (
        <FetchBar
          mailbox={queue?.mailbox}
          connected={mailboxConnected}
          busy={busy}
          onFetch={handleFetch}
          onImportFile={handleImportFile}
          format={format}
          lastResult={lastFetch}
        />
      )}

      <div className="intake-toolbar">
        <div className="ui-tabs intake-counts" role="group" aria-label="Filtrera kön">
          <button
            type="button"
            className={filter === 'open' ? 'active' : ''}
            aria-pressed={filter === 'open'}
            onClick={() => setFilter('open')}
          >
            Att ta ställning till <span className="ui-count">{counts.openThreads || 0}</span>
          </button>
          <button
            type="button"
            className={filter === 'awaiting' ? 'active' : ''}
            aria-pressed={filter === 'awaiting'}
            onClick={() => setFilter('awaiting')}
          >
            Väntar svar <span className="ui-count">{counts.awaitingReply || 0}</span>
          </button>
          <button
            type="button"
            className={filter === 'all' ? 'active' : ''}
            aria-pressed={filter === 'all'}
            onClick={() => setFilter('all')}
          >
            Alla trådar <span className="ui-count">{counts.threads || 0}</span>
          </button>
        </div>
        <button type="button" className="ui-btn ui-btn--ghost ui-btn--sm refresh" onClick={refresh} disabled={loading || busy}>
          <RefreshCw size={14} /> Uppdatera
        </button>
      </div>

      {loading && <p className="ui-loading intake-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>}

      {/* Nothing in the queue is one state, not two: splitting the screen to
          say "empty" on the left and "nothing selected" on the right would be
          the layout insisting on itself. */}
      {!loading && threads.length === 0 && (
        <div className="intake-empty">
          <div className="ui-empty">
            <div className="ui-empty-media"><Inbox size={20} /></div>
            <h3>{filter === 'open' ? 'Kön är tom' : 'Inga träffar'}</h3>
            <p className="empty">
              {filter === 'open'
                ? 'Ingenting väntar på ett beslut.'
                : 'Inga trådar matchar filtret.'}
            </p>
          </div>
        </div>
      )}

      {!loading && threads.length > 0 && (
        <div className="intake-layout">
          <div className="intake-list" role="list" aria-label="Trådar i kön">
            {threads.map((thread) => (
              <ThreadRow
                key={thread.key}
                thread={thread}
                selected={selected?.key === thread.key}
                onSelect={setSelectedKey}
              />
            ))}
          </div>

          <div className="intake-detail">
            {selected && (
              <ThreadDetail
                thread={selected}
                categories={queue.categoryLabels}
                resolutions={queue.resolutionLabels}
                busy={busy || !isAdmin}
                onConfirm={handleConfirm}
                onResolve={handleResolve}
                onReopen={handleReopen}
                onRetriage={handleRetriage}
                onOpenDocument={onOpenDocument}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
