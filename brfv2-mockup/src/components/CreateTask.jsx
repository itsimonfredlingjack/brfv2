import React, { useState } from 'react';
import { ClipboardList, Loader2 } from 'lucide-react';
import { tasksApi } from '../api';
import { datum } from './datum';
import './CreateTask.css';

/**
 * Turning something the product read into work with a name on it.
 *
 * The same panel serves the Uppgifter view and the cards in Fakturagranskning
 * and Bevakningar, because it is the same act everywhere: no engine creates a
 * task, so this is always a person deciding. Nothing here says "förslag" and
 * nothing arrives pre-decided — the fields are filled in from what the origin
 * said, and a human presses the button.
 *
 * Before the form is shown, the existing work for that origin is fetched and
 * listed. Two people creating the same task a week apart is the failure a
 * shared queue is supposed to prevent, not cause; when there is already one,
 * the button says "Skapa ändå" so a second is a conscious act rather than an
 * accident.
 */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
// The route's own limit, checked here so the form asks a person to shorten the
// line instead of sending a 422 to find out.
const MAX_TITLE = 200;

// What travels with the task, said plainly. The evidence is the reason a task
// is worth more than a line in a notebook, so the form says what it carries.
const EVIDENCE_NOTE = {
  finding: 'Fyndets citat följer med uppgiften, så passagen går att öppna långt efteråt.',
  watch: 'Bevakningens citat följer med uppgiften, så passagen går att öppna långt efteråt.',
  source_event: 'Köposten följer med som ursprung.',
  manual: 'Ingen källa: uppgiften säger själv att den är skapad för hand.',
};

export default function CreateTask({
  brfId,
  originKind = 'manual',
  originRef = '',
  suggestedTitle = '',
  suggestedResponsible = '',
  suggestedDue = '',
  openLabel = 'Skapa uppgift',
  canCreate = false,
  onCreated,
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(suggestedTitle.slice(0, MAX_TITLE));
  const [description, setDescription] = useState('');
  const [responsible, setResponsible] = useState(suggestedResponsible);
  const [due, setDue] = useState(suggestedDue || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [titleTouched, setTitleTouched] = useState(false);
  const [existing, setExisting] = useState(null);
  const [looking, setLooking] = useState(false);

  const linked = originKind !== 'manual' && Boolean(originRef);

  // Reading is open to every member; only an administrator can take work on.
  // A control that always answers 403 is not a choice, so it is not offered.
  if (!canCreate) return null;

  async function openPanel() {
    setOpen(true);
    setError('');
    if (!linked) return;
    setLooking(true);
    try {
      const rows = await tasksApi.forOrigin(brfId, originKind, originRef);
      setExisting(Array.isArray(rows) ? rows : []);
    } catch {
      // Not knowing is not the same as knowing there is none, and the form
      // says so rather than implying the field is clear.
      setExisting(null);
    } finally {
      setLooking(false);
    }
  }

  const trimmed = title.trim();
  const dueValid = due === '' || ISO_DATE.test(due);
  const ready = trimmed.length > 0 && trimmed.length <= MAX_TITLE && dueValid && !busy;
  const duplicates = existing?.length > 0;

  async function submit() {
    setBusy(true);
    setError('');
    try {
      const created = await tasksApi.create(brfId, {
        title: trimmed,
        description: description.trim(),
        responsible: responsible.trim(),
        due_date: due || null,
        origin_kind: originKind,
        origin_ref: originRef,
      });
      setExisting((rows) => (rows ? [...rows, created] : [created]));
      setDescription('');
      setOpen(false);
      onCreated?.(created);
    } catch (err) {
      // 404 for an origin that is gone, 422 for a rubric or a date the route
      // will not take. Both arrive as Swedish sentences and are shown as they
      // came.
      setError(err.message || 'Uppgiften kunde inte skapas.');
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="task-create">
        <button type="button" className="task-create-open" onClick={openPanel}>
          <ClipboardList size={14} /> {openLabel}
        </button>
        {duplicates && (
          <span className="task-create-known">
            {existing.length === 1
              ? 'Det finns redan en uppgift för det här.'
              : `Det finns redan ${existing.length} uppgifter för det här.`}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="task-create open">
      <div className="task-create-panel">
        <h5>Ny uppgift</h5>
        <p className="muted">
          Ingen motor skapar en uppgift. Att skapa den är beslutet, och den
          skrivs som ett — med den som skapade den och när.
          {' '}{EVIDENCE_NOTE[originKind] || EVIDENCE_NOTE.manual}
        </p>

        {linked && looking && (
          <p className="task-create-looking">
            <Loader2 size={13} className="spin" /> Kontrollerar om det redan finns en uppgift…
          </p>
        )}

        {linked && !looking && existing === null && (
          <p className="task-create-unknown">
            Kunde inte läsa vilka uppgifter som redan finns för det här. Kontrollera
            listan under Uppgifter innan du skapar en till.
          </p>
        )}

        {duplicates && (
          <div className="task-create-duplicate">
            <h6>Det finns redan en uppgift för det här</h6>
            <ul>
              {existing.map((task) => (
                <li key={task.id}>
                  <span className="task-create-duplicate-title">{task.title}</span>
                  <span className="muted">
                    {task.status_label} · {task.responsible || 'ej utsedd'}
                    {task.due_date ? ` · ${datum(task.due_date)}` : ' · inget datum'}
                  </span>
                </li>
              ))}
            </ul>
            <p className="muted">
              Skapa en till bara om det är ett annat arbete. Uppgifter tas aldrig
              bort, så en dubblett står kvar.
            </p>
          </div>
        )}

        <label>
          <span>Rubrik</span>
          <input
            type="text"
            value={title}
            maxLength={MAX_TITLE}
            disabled={busy}
            onChange={(e) => { setTitle(e.target.value); setTitleTouched(true); }}
          />
        </label>
        <label>
          <span>Beskrivning (valfri)</span>
          <textarea
            rows={2}
            value={description}
            disabled={busy}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <div className="task-create-fields">
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
            <span>Datum (valfritt)</span>
            <input
              type="date"
              value={due}
              disabled={busy}
              onChange={(e) => setDue(e.target.value)}
            />
          </label>
        </div>

        {titleTouched && !trimmed && <p className="task-invalid">Uppgiften behöver en rubrik.</p>}
        {!dueValid && <p className="task-invalid">Datum ska skrivas ÅÅÅÅ-MM-DD.</p>}
        {!responsible.trim() && (
          <p className="muted">
            Utan namn står uppgiften som <strong>ej utsedd</strong> och räknas
            bland de oplacerade.
          </p>
        )}

        {error && <p className="task-create-error" role="alert">{error}</p>}

        <div className="task-create-actions">
          <button
            type="button"
            className="ui-btn ui-btn--primary ui-btn--sm"
            disabled={!ready}
            onClick={submit}
          >
            {busy ? <Loader2 size={14} className="spin" /> : <ClipboardList size={14} />}
            {' '}{duplicates ? 'Skapa ändå' : 'Skapa uppgift'}
          </button>
          <button
            type="button"
            className="ui-btn ui-btn--ghost ui-btn--sm"
            disabled={busy}
            onClick={() => { setOpen(false); setError(''); }}
          >
            {/* "Stäng", not "Avbryt": avbryta is what happens to a task that
                turned out to be unnecessary, and the word is not spent on
                closing a form. */}
            Stäng
          </button>
        </div>
      </div>
    </div>
  );
}
