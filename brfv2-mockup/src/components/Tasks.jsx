import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react';
import { tasksApi } from '../api';
import CreateTask from './CreateTask';
import EmptyState from './EmptyState';
import Instrument from './Instrument';
import './Tasks.css';
import { datum, datumTid } from './datum';

/**
 * Uppgifter: the work, who owns it, by when, and everything that happened to it.
 *
 * The rest of the product reads and proposes. This screen is the one place
 * where a finding, a watch or a piece of incoming post becomes work with a name
 * on it, and two rules shape everything on it:
 *
 * **No engine creates a task.** There is no scan here and nothing arrives as a
 * "förslag" waiting to be approved, because creating a task *is* the decision.
 * Borrowing Bevakningar's proposal framing would suggest something else already
 * decided what the board should do.
 *
 * **A task is never deleted.** There is no delete route and no control here
 * that implies one. Work that turned out to be unnecessary is *avbruten* with a
 * stated reason and stays visible, because a task that existed is a record of
 * what the board decided to do.
 *
 * The activity trail is not a detail view: it is the feature. "Who moved the
 * deadline, and when" is the question that gets asked afterwards, so the trail
 * is on the card, open, unless it has grown long enough that the recent lines
 * would be pushed off the screen.
 */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

// The same two the route refuses without a note. Checked here so the form asks
// for the sentence instead of sending a 422 to find out it was needed.
const REASON_REQUIRED = ['blocked', 'cancelled'];

// Above this many events the oldest fold away and the three most recent stay
// out — a card whose history is a year long must not bury the change that
// happened yesterday.
const ACTIVITY_FOLD = 6;

const CHANGE_KINDS = new Set(['status_changed', 'assigned', 'due_changed']);

// An empty value in a trail means something specific, and the trail says which.
const ABSENT_VALUE = {
  assigned: 'ej utsedd',
  due_changed: 'inget datum',
};

function daysLeftText(days) {
  if (days === null || days === undefined) return '';
  if (days === 0) return 'i dag';
  if (days > 0) return `om ${days} ${days === 1 ? 'dag' : 'dagar'}`;
  const late = Math.abs(days);
  return `${late} ${late === 1 ? 'dag' : 'dagar'} försenat`;
}


// An undated task is not urgent, it is unscheduled — and the card says so
// rather than leaving the field blank.
const dueText = (task) => (task.due_date
  ? `${task.due_date} · ${daysLeftText(task.days_left)}`
  : 'inget datum satt');

const originText = (task) => (task.origin.label
  ? `${task.origin.kind_label} — ${task.origin.label}`
  : task.origin.kind_label);

/** The last event that put the task in the state it is in now. */
function closingEvent(task) {
  const events = task.activity || [];
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].kind === 'status_changed' && events[i].to_value === task.status) {
      return events[i];
    }
  }
  return null;
}

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`tasks-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="tasks-banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

/**
 * The passage the work came out of.
 *
 * Copied onto the task when it was created and routed through the app's own
 * citation navigation, so a task made from a finding opens the same document at
 * the same page months later — after the invoice has been re-read and the
 * finding itself re-run.
 */
function Citation({ citation, onOpen }) {
  return (
    <button
      type="button"
      className="task-citation"
      onClick={() => onOpen(citation)}
      title={`Öppna ${citation.document_name} sida ${citation.page}`}
    >
      <FileText size={14} />
      <span className="task-citation-source">
        {citation.document_name} · s. {citation.page}
        {citation.approximate && <em className="task-citation-approx"> (markering ungefärlig)</em>}
      </span>
      <q className="task-citation-quote">{citation.quote}</q>
    </button>
  );
}

function Citations({ citations, onOpen }) {
  if (!citations || citations.length === 0) return null;
  return (
    <div className="task-citations">
      {citations.map((citation, i) => (
        <Citation key={i} citation={citation} onOpen={onOpen} />
      ))}
    </div>
  );
}

function eventValue(kind, value, statusLabels) {
  if (kind === 'status_changed') return statusLabels[value] || value || '—';
  return value || ABSENT_VALUE[kind] || '—';
}

/** One line of history, readable without diffing two snapshots. */
function describeEvent(event, statusLabels) {
  if (!CHANGE_KINDS.has(event.kind)) return event.kind_label;
  return `${event.kind_label} från ${eventValue(event.kind, event.from_value, statusLabels)}`
    + ` till ${eventValue(event.kind, event.to_value, statusLabels)}`;
}

function EventList({ events, statusLabels }) {
  return (
    <ol className="task-events">
      {events.map((event) => (
        <li key={event.id} className={`task-event ${event.kind}`}>
          <span className="task-event-when">{datumTid(event.at)}</span>
          <span className="task-event-who">{event.by}</span>
          <span className="task-event-what">{describeEvent(event, statusLabels)}</span>
          {event.note && <span className="task-event-note">{event.note}</span>}
        </li>
      ))}
    </ol>
  );
}

/** The whole trail, newest last, open unless it has grown long. */
function Activity({ task, statusLabels }) {
  const events = task.activity || [];
  const folded = events.length > ACTIVITY_FOLD;
  const earlier = folded ? events.slice(0, events.length - 3) : [];
  const recent = folded ? events.slice(-3) : events;

  return (
    <div className="task-history">
      <h5>Händelser</h5>
      {events.length === 0 ? (
        <p className="muted">Ingen historik finns för den här uppgiften.</p>
      ) : (
        <>
          {folded && (
            <details className="task-history-earlier">
              <summary>Tidigare händelser ({earlier.length})</summary>
              <EventList events={earlier} statusLabels={statusLabels} />
            </details>
          )}
          <EventList events={recent} statusLabels={statusLabels} />
        </>
      )}
    </div>
  );
}

/**
 * Changing a task.
 *
 * Only what a person actually changed is sent: the route answers 422 "Inget att
 * ändra" to a write that says nothing happened, and it is right to — the
 * history would otherwise fill with lines nobody wrote. Blocking and cancelling
 * are held back until a reason is written, for the same reason the route holds
 * them back.
 */
function TaskChange({ task, statusLabels, busy, onSave, onComment }) {
  const [status, setStatus] = useState(task.status);
  const [responsible, setResponsible] = useState(task.responsible || '');
  const [due, setDue] = useState(task.due_date || '');
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || '');
  const [note, setNote] = useState('');
  const [comment, setComment] = useState('');

  const trimmedTitle = title.trim();
  const noteText = note.trim();
  const dueValid = due === '' || ISO_DATE.test(due);

  const change = {};
  if (status !== task.status) change.status = status;
  if (responsible.trim() !== task.responsible) change.responsible = responsible.trim();
  if (due !== (task.due_date || '')) change.due_date = due;
  if (trimmedTitle && trimmedTitle !== task.title) change.title = trimmedTitle;
  if (description.trim() !== (task.description || '')) change.description = description.trim();

  const needsNote = status !== task.status && REASON_REQUIRED.includes(status);
  const changed = Object.keys(change).length > 0;
  const canSave = !busy && dueValid && Boolean(trimmedTitle)
    && (changed || Boolean(noteText)) && (!needsNote || Boolean(noteText));

  function save() {
    if (!canSave) return;
    onSave(task, noteText ? { ...change, note: noteText } : change);
  }

  return (
    /* On demand, not always open: the card is the record, and a permanently
       expanded mutation form outweighed the work it was about. The trail
       above stays open — it is the feature; changing is the exception. */
    <details className="task-change">
      <summary><h5>Ändra eller kommentera</h5></summary>
      <div className="task-change-fields">
        <label>
          <span>Status</span>
          <select value={status} disabled={busy} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Ansvarig</span>
          <input
            type="text"
            value={responsible}
            placeholder="ej utsedd"
            disabled={busy}
            onChange={(e) => setResponsible(e.target.value)}
          />
        </label>
        <label>
          <span>Datum</span>
          <input
            type="date"
            value={due}
            disabled={busy}
            onChange={(e) => setDue(e.target.value)}
          />
        </label>
      </div>

      <details className="task-change-text">
        <summary>Ändra rubrik och beskrivning</summary>
        <label>
          <span>Rubrik</span>
          <input
            type="text"
            value={title}
            disabled={busy}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          <span>Beskrivning</span>
          <textarea
            rows={2}
            value={description}
            disabled={busy}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
      </details>

      <label className="task-change-note">
        <span>Anteckning (krävs för blockerad och avbruten)</span>
        <input
          type="text"
          value={note}
          disabled={busy}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>

      {!trimmedTitle && <p className="task-invalid">Uppgiften behöver en rubrik.</p>}
      {!dueValid && <p className="task-invalid">Datum ska skrivas ÅÅÅÅ-MM-DD.</p>}
      {needsNote && !noteText && (
        <p className="task-invalid">
          Skriv varför uppgiften blockeras eller avbryts. Uppgiften tas aldrig
          bort — den står kvar med anledningen du skriver.
        </p>
      )}
      {!changed && !noteText && (
        <p className="muted">Inget är ändrat än.</p>
      )}

      <div className="task-change-actions">
        <button
          type="button"
          className="task-action save"
          disabled={!canSave}
          title={needsNote && !noteText
            ? 'Skriv först varför uppgiften blockeras eller avbryts.'
            : undefined}
          onClick={save}
        >
          Spara ändring
        </button>
      </div>

      <div className="task-comment">
        <label>
          <span>Kommentar</span>
          <input
            type="text"
            value={comment}
            disabled={busy}
            onChange={(e) => setComment(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="task-action comment"
          disabled={busy || !comment.trim()}
          onClick={() => onComment(task, comment.trim())}
        >
          Kommentera
        </button>
      </div>
    </details>
  );
}

/** Initials for the ownership rail. Presentation only — the name stands beside. */
const initialsFor = (name) => (name || '')
  .split(' ')
  .filter(Boolean)
  .map((word) => word[0].toUpperCase())
  .slice(0, 2)
  .join('');

/** One piece of work the association has taken on. */
function TaskCard({ task, statusLabels, busy, canDecide, onSave, onComment, onOpenCitation }) {
  return (
    <article className={`task ${task.status}${task.overdue ? ' overdue' : ''}`}>
      {/* Responsibility is this workspace's axis: who owns the work stands on
          a rail of its own, before the work itself — and nobody named is said
          in Vägran, because unowned work is work without support. The date
          under the name is the next measurement a board asks for. */}
      <div className="task-who">
        <span className={`task-avatar${task.responsible ? '' : ' empty'}`} aria-hidden="true">
          {initialsFor(task.responsible) || '?'}
        </span>
        <span className="task-owner">
          {task.responsible
            ? task.responsible
            : <span className="task-unassigned">ej utsedd</span>}
        </span>
        <span className={`task-due${task.overdue ? ' late' : ''}`}>{dueText(task)}</span>
      </div>

      <div className="task-body">
      <header className="task-head">
        <span className="task-origin-kind">{task.origin.kind_label}</span>
        <span className="task-badges">
          {/* Late is said in words as well as in weight: the two people who
              need this card most are the one who cannot see the border and the
              one reading it in a printout. */}
          {task.overdue && <span className="task-badge late">försenad</span>}
          <span className={`task-badge ${task.status}`}>{task.status_label}</span>
        </span>
      </header>

      <h4 className="task-title">{task.title}</h4>
      {task.description && <p className="task-description">{task.description}</p>}

      <dl className="task-facts">
        <div>
          <dt>Ursprung</dt>
          <dd>{originText(task)}</dd>
        </div>
        {task.source_document_name && (
          <div>
            <dt>Läst ur</dt>
            <dd>{task.source_document_name}</dd>
          </div>
        )}
        <div>
          <dt>Skapad</dt>
          <dd>{task.created_by} · {datumTid(task.created_at)}</dd>
        </div>
      </dl>

      <Citations citations={task.citations} onOpen={onOpenCitation} />

      <Activity task={task} statusLabels={statusLabels} />

      {canDecide && (
        <TaskChange
          // Remounts after every write, so the fields hold what the server now
          // says rather than what somebody typed two changes ago.
          key={task.last_activity_at}
          task={task}
          statusLabels={statusLabels}
          busy={busy}
          onSave={onSave}
          onComment={onComment}
        />
      )}
      </div>
    </article>
  );
}

/** Work that is finished or was called off. Out of the way, still readable. */
function ClosedTask({ task, statusLabels, onOpenCitation }) {
  const closed = closingEvent(task);
  return (
    <li className="task-closed">
      <span className="task-closed-title">{task.title}</span>
      <span className="task-closed-meta">
        {task.status_label} · {closed ? closed.by : task.created_by}
        {' · '}{datumTid(closed ? closed.at : task.created_at)}
        {' · '}{task.responsible || 'ej utsedd'}
      </span>
      {closed?.note && <span className="task-closed-note">Anledning: {closed.note}</span>}
      <span className="task-closed-origin">{originText(task)}</span>
      <Citations citations={task.citations} onOpen={onOpenCitation} />
      <details className="task-closed-history">
        <summary>Händelser ({(task.activity || []).length})</summary>
        <EventList events={task.activity || []} statusLabels={statusLabels} />
      </details>
    </li>
  );
}

export default function Tasks({ brfId, isAdmin = false, onOpenCitation }) {
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const newSectionRef = useRef(null);

  // The empty state's action presses the section's own "Ny uppgift" button,
  // so the panel that opens is the same one the toolbar offers.
  const openCreate = () => {
    newSectionRef.current?.querySelector('.task-create-open')?.click();
  };

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      setBoard(await tasksApi.list(brfId));
      setError('');
    } catch (err) {
      setError(err.message || 'Kunde inte hämta uppgifterna.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  const openCitation = useCallback(
    (citation) => onOpenCitation?.(citation),
    [onOpenCitation],
  );

  async function save(task, change) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await tasksApi.update(brfId, task.id, change);
      setNotice(
        `Sparat. ${updated.title}: ${updated.status_label}, ansvarig `
        + `${updated.responsible || 'ej utsedd'}, `
        + `${updated.due_date || 'inget datum'}.`,
      );
      await refresh();
    } catch (err) {
      // 422 for a change that changes nothing, and for blocking or cancelling
      // without a reason. The route's own sentence is the clearest thing to
      // show, so it is shown as it came.
      setError(err.message || 'Ändringen kunde inte sparas.');
    } finally {
      setBusy(false);
    }
  }

  async function comment(task, note) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await tasksApi.comment(brfId, task.id, note);
      setNotice('Kommentaren är sparad i historiken.');
      await refresh();
    } catch (err) {
      setError(err.message || 'Kommentaren kunde inte sparas.');
    } finally {
      setBusy(false);
    }
  }

  const statusLabels = board?.statusLabels || {};
  const active = board?.active || [];
  const done = board?.done || [];
  const cancelled = board?.cancelled || [];
  const counts = board?.counts || { active: 0, overdue: 0, unassigned: 0 };

  return (
    <div className={`tasks${!loading && board && active.length === 0 ? ' has-no-active' : ''}`}>
      <header className="tasks-header page-header">
        <div className="page-header-text">
          <h2 className="page-title">Uppgifter</h2>
          <p className="page-header-sub">
            Arbete någon tagit på sig — vem, till när, och vad som hänt sedan.
          </p>
        </div>

        <div className="page-header-actions">
          <button type="button" className="tasks-refresh" disabled={loading || busy} onClick={refresh}>
            <RefreshCw size={15} /> Uppdatera
          </button>
        </div>

        {/* Uppgifter's instrument is people: not money, not time, but how much
            work is owned and how much of it has slipped. Three numerals in mono
            on ink — the screen's own composition, and the same three whether
            they read 0 or 40. */}
        <Instrument
          readings={[
            { label: 'Pågående', value: counts.active },
            { label: 'Försenade', value: counts.overdue, flagged: counts.overdue > 0 },
            { label: 'Utan ansvarig', value: counts.unassigned, flagged: counts.unassigned > 0 },
          ]}
        />
      </header>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {loading && (
        <p className="tasks-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>
      )}

      {!loading && board && (
        <>
          <p className="tasks-summary">
            {counts.unassigned > 0 && `${counts.unassigned} av ${counts.active} `
              + 'pågående uppgifter har ingen namngiven ansvarig.'}
            {!isAdmin && ' Bara administratörer kan skapa och ändra uppgifter.'}
          </p>

          {/* Nothing here for a member who cannot create one: the summary above
              already says why the section is missing. */}
          {/* The heading and its paragraph said in five lines what the button
              says in two words. A task that belongs to a finding is created
              from that finding's own card, so this section only ever had one
              job: start a task that begins in a meeting. */}
          {isAdmin && (
            <section className="tasks-new" aria-label="Ny uppgift" ref={newSectionRef}>
              <CreateTask
                brfId={brfId}
                canCreate={isAdmin}
                openLabel="Ny uppgift"
                onCreated={async (task) => {
                  setNotice(`Uppgift skapad: ${task.title}.`);
                  await refresh();
                }}
              />
            </section>
          )}

          <section className="tasks-active" aria-label="Pågående">
            <h3>Pågående</h3>
            {active.length === 0 ? (
              <EmptyState
                title="Inga uppgifter på gång."
                actions={isAdmin ? (
                  <button type="button" className="ui-btn ui-btn--primary" onClick={openCreate}>
                    <Plus size={15} /> Skapa första uppgiften
                  </button>
                ) : null}
              >
                Skapa den första så syns vem som gör vad, till när.
              </EmptyState>
            ) : active.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                statusLabels={statusLabels}
                busy={busy}
                canDecide={isAdmin}
                onSave={save}
                onComment={comment}
                onOpenCitation={openCitation}
              />
            ))}
          </section>

          <details className="tasks-closed">
            <summary>Klara uppgifter ({done.length})</summary>
            {done.length === 0 ? (
              <p className="empty">Inget är avklarat ännu.</p>
            ) : (
              <ul>
                {done.map((task) => (
                  <ClosedTask
                    key={task.id}
                    task={task}
                    statusLabels={statusLabels}
                    onOpenCitation={openCitation}
                  />
                ))}
              </ul>
            )}
          </details>

          <details className="tasks-closed">
            <summary>Avbrutna uppgifter ({cancelled.length})</summary>
            <p className="muted">
              Avbrutet arbete tas inte bort. Det står kvar med den som avbröt
              det och varför.
            </p>
            {cancelled.length === 0 ? (
              <p className="empty">Ingen uppgift är avbruten.</p>
            ) : (
              <ul>
                {cancelled.map((task) => (
                  <ClosedTask
                    key={task.id}
                    task={task}
                    statusLabels={statusLabels}
                    onOpenCitation={openCitation}
                  />
                ))}
              </ul>
            )}
          </details>
        </>
      )}

      {!loading && !board && !error && (
        <p className="empty"><AlertTriangle size={15} /> Inga uppgiftsdata kunde läsas.</p>
      )}
    </div>
  );
}
