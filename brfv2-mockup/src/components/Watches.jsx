import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  HelpCircle,
  Loader2,
  RefreshCw,
  Repeat,
  ScanLine,
  Trash2,
  X,
} from 'lucide-react';
import { watchesApi } from '../api';
import CreateTask from './CreateTask';
import EmptyState from './EmptyState';
import './Watches.css';

/**
 * The association's dated obligations, and the proposals that are not yet any.
 *
 * One rule shapes the whole screen: **a proposal is not a watch.** What the
 * engine read out of a contract lives in its own section, carries the passage
 * its date came from and the arithmetic that produced it, and offers three
 * decisions. What the board has actually taken on lives in the four buckets,
 * and every card there names a human decision — a date somebody confirmed, a
 * person somebody appointed. Blending the two would let a rule engine commit a
 * board to obligations nobody ever agreed to.
 *
 * The second rule follows from the first: a date the engine derived is never
 * shown as a date the board decided. When a human moves it, both dates stay on
 * the card, because the pair is the audit trail — showing only the winner hides
 * that somebody disagreed with the contract's own arithmetic.
 */

const BUCKET_ORDER = ['overdue', 'soon', 'later', 'recurring'];

// An empty bucket is a real state. A column that renders nothing looks like a
// load that failed, so each one says in words which of the two it is.
const EMPTY_BUCKET = {
  overdue: 'Inget är försenat.',
  soon: 'Ingen bevakning har nått sin påminnelsetid.',
  later: 'Inget ligger längre fram.',
  recurring: 'Ingen återkommande skyldighet bevakas.',
};

const RECURRENCE_LABEL = {
  none: 'engångsdatum',
  monthly: 'varje månad',
  quarterly: 'varje kvartal',
  yearly: 'varje år',
  biennial: 'vartannat år',
  triennial: 'vart tredje år',
};

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

// The same two limits the route enforces. Checked here as well so the form
// asks a person to fix the value instead of sending a 422 to find out.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_LEAD_DAYS = 365;

function daysLeftText(days) {
  if (days === null || days === undefined) return '';
  if (days === 0) return 'i dag';
  if (days > 0) return `om ${days} ${days === 1 ? 'dag' : 'dagar'}`;
  const late = Math.abs(days);
  return `${late} ${late === 1 ? 'dag' : 'dagar'} försenat`;
}

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

function Banner({ tone, children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`watches-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="watches-banner-dismiss" onClick={onDismiss} aria-label="Stäng meddelande">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

/**
 * The passage the date was read from.
 *
 * Routed through the app's own citation navigation, so a watch opens the
 * contract at the same page, with the same highlight, as an answer's citation
 * does. A deadline whose source cannot be opened is a claim, not a watch.
 */
function Citation({ citation, onOpen }) {
  return (
    <button
      type="button"
      className="watch-citation"
      onClick={() => onOpen(citation)}
      title={`Öppna ${citation.document_name} sida ${citation.page}`}
    >
      <FileText size={14} />
      <span className="watch-citation-source">
        {citation.document_name} · s. {citation.page}
        {citation.approximate && <em className="watch-citation-approx"> (markering ungefärlig)</em>}
      </span>
      <q className="watch-citation-quote">{citation.quote}</q>
    </button>
  );
}

function Citations({ citations, onOpen }) {
  if (!citations || citations.length === 0) return null;
  return (
    <div className="watch-citations">
      {citations.map((citation, i) => (
        <Citation key={i} citation={citation} onOpen={onOpen} />
      ))}
    </div>
  );
}

/** The derived date and the arithmetic behind it, readable without trusting it. */
function Derivation({ watch }) {
  return (
    <dl className="watch-derivation">
      <div>
        <dt>Uträkning</dt>
        <dd>{watch.derivation}</dd>
      </div>
      <div>
        <dt>Ger datumet</dt>
        <dd>{watch.derived_due_date}</dd>
      </div>
      <div>
        <dt>Läst ur</dt>
        <dd>{watch.source_document_name || '—'}</dd>
      </div>
    </dl>
  );
}

/**
 * One proposal: what the engine read, and the three things a person may do
 * with it. Nothing here is an obligation yet, and the card says so before it
 * says anything else.
 */
function Proposal({ watch, busy, canDecide, onApprove, onDismiss, onDelete, onOpenCitation }) {
  const [due, setDue] = useState(watch.due_date);
  const [responsible, setResponsible] = useState(watch.responsible || '');
  const [lead, setLead] = useState(String(watch.remind_lead_days));
  const [note, setNote] = useState('');

  const leadNumber = Number(lead);
  const leadValid = lead !== '' && Number.isInteger(leadNumber)
    && leadNumber >= 0 && leadNumber <= MAX_LEAD_DAYS;
  const dueValid = ISO_DATE.test(due);
  const blocked = busy || !canDecide;

  return (
    <article className="watch proposal">
      <header className="watch-head">
        <span className="watch-kind">{watch.kind_label}</span>
        <span className="watch-badge proposed">förslag — ingen bevakning ännu</span>
      </header>

      <h4 className="watch-title">{watch.title}</h4>

      <Derivation watch={watch} />
      <Citations citations={watch.citations} onOpen={onOpenCitation} />

      <div className="watch-approve">
        <h5>Godkänn som bevakning</h5>
        <div className="watch-fields">
          <label>
            <span>Datum</span>
            <input
              type="date"
              value={due}
              disabled={blocked}
              onChange={(e) => setDue(e.target.value)}
            />
          </label>
          <label>
            <span>Ansvarig</span>
            <input
              type="text"
              value={responsible}
              disabled={blocked}
              placeholder="ej utsedd"
              onChange={(e) => setResponsible(e.target.value)}
            />
          </label>
          <label>
            <span>Påminn dagar före</span>
            <input
              type="number"
              min="0"
              max={MAX_LEAD_DAYS}
              value={lead}
              disabled={blocked}
              onChange={(e) => setLead(e.target.value)}
            />
          </label>
        </div>
        {!dueValid && <p className="watch-invalid">Datum ska skrivas ÅÅÅÅ-MM-DD.</p>}
        {!leadValid && (
          <p className="watch-invalid">Påminnelsen ska ligga 0–{MAX_LEAD_DAYS} dagar före.</p>
        )}
        <button
          type="button"
          className="watch-action approve"
          disabled={blocked || !dueValid || !leadValid}
          onClick={() => onApprove(watch, {
            due_date: due,
            responsible: responsible.trim(),
            remind_lead_days: leadNumber,
          })}
        >
          <CheckCircle2 size={14} /> Godkänn
        </button>
      </div>

      <div className="watch-dismiss">
        <label>
          <span>Varför avfärdas den? (krävs)</span>
          <input
            type="text"
            value={note}
            disabled={blocked}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="watch-action dismiss"
          disabled={blocked || !note.trim()}
          title={note.trim() ? undefined : 'Skriv först varför bevakningen inte gäller.'}
          onClick={() => onDismiss(watch, note.trim())}
        >
          Avfärda
        </button>
      </div>

      <div className="watch-remove">
        <button
          type="button"
          className="watch-action remove"
          disabled={blocked}
          onClick={() => onDelete(watch)}
        >
          <Trash2 size={14} /> Ta bort
        </button>
        <span className="muted">
          Tar bort förslaget utan att spara något beslut. Nästa genomläsning kan
          föreslå det igen.
        </span>
      </div>
    </article>
  );
}

/** One obligation the association has taken on. */
function BoardWatch({
  watch, brfId, busy, canDecide, onComplete, onDismiss, onOpenCitation, onTaskCreated,
}) {
  const [note, setNote] = useState('');
  const moved = watch.due_date !== watch.derived_due_date;
  const late = typeof watch.days_left === 'number' && watch.days_left < 0;

  return (
    <article className={`watch board${late ? ' late' : ''}`}>
      {/* Time is this workspace's axis, so the date stands on its own rail
          before anything else on the card. A passed date reads as weight, not
          as a hue — the boxed measurement theme.css prescribes. */}
      <div className="watch-when">
        <span className="watch-date">{watch.due_date}</span>
        {late
          ? <span className="matt--overdue">{daysLeftText(watch.days_left)}</span>
          : <span className="watch-days">{daysLeftText(watch.days_left)}</span>}
      </div>

      <div className="watch-body">
      <header className="watch-head">
        <span className="watch-kind">{watch.kind_label}</span>
        <span className="watch-badge approved">{watch.status_label}</span>
      </header>

      <h4 className="watch-title">{watch.title}</h4>

      <dl className="watch-facts">
        <div>
          <dt>Ansvarig</dt>
          <dd>
            {watch.responsible
              ? watch.responsible
              : <span className="watch-unassigned">ej utsedd</span>}
          </dd>
        </div>
        <div>
          <dt>Påminnelse</dt>
          <dd>{watch.remind_at} ({watch.remind_lead_days} dagar före)</dd>
        </div>
        {watch.recurrence !== 'none' && (
          <div>
            <dt>Återkommer</dt>
            <dd>
              <Repeat size={13} /> {RECURRENCE_LABEL[watch.recurrence] || watch.recurrence}
              {watch.next_due_after && ` · sedan ${watch.next_due_after}`}
            </dd>
          </div>
        )}
        <div>
          <dt>Läst ur</dt>
          <dd>{watch.source_document_name || '—'}</dd>
        </div>
      </dl>

      {moved ? (
        <p className="watch-moved">
          Motorn räknade fram <strong>{watch.derived_due_date}</strong> ur {watch.derivation}.
          En människa har flyttat datumet till <strong>{watch.due_date}</strong>.
        </p>
      ) : (
        <p className="watch-kept">
          Datumet är motorns eget: {watch.derivation}. En människa har godkänt det.
        </p>
      )}

      <Citations citations={watch.citations} onOpen={onOpenCitation} />

      {watch.decision_note && <p className="watch-note">Anteckning: {watch.decision_note}</p>}

      {canDecide && (
        <div className="watch-decision">
          <button
            type="button"
            className="watch-action complete"
            disabled={busy}
            onClick={() => onComplete(watch)}
          >
            <CheckCircle2 size={14} /> Markera som avklarad
          </button>
          {/* Dismissing is the exception, so its reason field waits behind a
              disclosure instead of standing open on every card on the board. */}
          <details className="watch-dismiss-wrap">
            <summary>Avfärda …</summary>
            <div className="watch-dismiss">
              <label>
                <span>Varför avfärdas den? (krävs)</span>
                <input
                  type="text"
                  value={note}
                  disabled={busy}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="watch-action dismiss"
                disabled={busy || !note.trim()}
                title={note.trim() ? undefined : 'Skriv först varför bevakningen inte gäller.'}
                onClick={() => onDismiss(watch, note.trim())}
              >
                Avfärda
              </button>
            </div>
          </details>
        </div>
      )}

      {/* A date is not work. Turning this obligation into somebody's job is a
          separate decision, taken here and recorded as one — the watch itself
          is unchanged by it. */}
      <CreateTask
        brfId={brfId}
        canCreate={canDecide}
        originKind="watch"
        originRef={watch.id}
        suggestedTitle={watch.title}
        suggestedResponsible={watch.responsible || ''}
        suggestedDue={watch.due_date || ''}
        onCreated={onTaskCreated}
      />
      </div>
    </article>
  );
}

/**
 * Twelve months forward, for the recurring bucket only.
 *
 * A strip, not a calendar: it answers "which months are loaded" and nothing
 * else. The dates themselves are on the cards.
 */
function MonthStrip({ today, watches }) {
  const cells = useMemo(() => {
    const [year, month] = today.split('-').map(Number);
    return Array.from({ length: 12 }, (_, i) => {
      const index = month - 1 + i;
      const key = `${year + Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
      return {
        key,
        label: MONTHS[index % 12],
        items: watches.filter((w) => w.due_date.startsWith(key)),
      };
    });
  }, [today, watches]);

  if (watches.length === 0) return null;

  return (
    <ol className="watch-strip" aria-label="Tolv månader framåt">
      {cells.map((cell) => (
        <li
          key={cell.key}
          className={cell.items.length > 0 ? 'loaded' : ''}
          title={cell.items.length > 0
            ? cell.items.map((w) => `${w.due_date} ${w.title}`).join('\n')
            : `${cell.key}: inget`}
        >
          <span className="strip-month">{cell.label}</span>
          <span className="strip-count">{cell.items.length > 0 ? cell.items.length : ''}</span>
        </li>
      ))}
    </ol>
  );
}

export default function Watches({ brfId, isAdmin = false, onOpenCitation }) {
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // Separate from `busy` only so the spinner sits on the button that is
  // actually working: a scan reads every document and takes its time.
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    if (!brfId) return;
    setLoading(true);
    try {
      setBoard(await watchesApi.board(brfId));
      setError('');
    } catch (err) {
      setError(err.message || 'Kunde inte hämta bevakningarna.');
    } finally {
      setLoading(false);
    }
  }, [brfId]);

  useEffect(() => { refresh(); }, [refresh]);

  const openCitation = useCallback(
    (citation) => onOpenCitation?.(citation),
    [onOpenCitation],
  );

  async function decide(watch, decision, describe) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await watchesApi.decide(brfId, watch.id, decision);
      setNotice(describe(result));
      await refresh();
    } catch (err) {
      setError(err.message || 'Beslutet kunde inte sparas.');
    } finally {
      setBusy(false);
    }
  }

  const approve = (watch, fields) => decide(
    watch,
    { status: 'approved', ...fields },
    (result) => `Godkänd och bevakas till ${result.watch.due_date}. Ansvarig: `
      + `${result.watch.responsible || 'ej utsedd'}.`,
  );

  const dismiss = (watch, note) => decide(
    watch,
    { status: 'dismissed', note },
    () => 'Avfärdad. Anteckningen är sparad med beslutet.',
  );

  // A completed recurring obligation returns its own next turn, already
  // approved. Saying so is the point: otherwise the board sees an entry vanish
  // and a new one appear without being told they are the same duty.
  const complete = (watch) => decide(
    watch,
    { status: 'done' },
    (result) => (result.successor
      ? `Avklarad. Nästa gång ${result.successor.due_date} — den turen är redan `
        + 'godkänd och ligger under Återkommande.'
      : 'Avklarad.'),
  );

  async function remove(watch) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await watchesApi.remove(brfId, watch.id);
      setNotice('Förslaget togs bort.');
      await refresh();
    } catch (err) {
      // 409 when somebody decided on it while this list was on screen. The
      // route's own sentence says what to do instead, so it is shown verbatim.
      setError(err.message || 'Förslaget kunde inte tas bort.');
    } finally {
      setBusy(false);
    }
  }

  // The watch is untouched by this: a task is a separate record, and the board
  // is told where it went rather than left to guess.
  const taskCreated = useCallback((task) => {
    setError('');
    setNotice(
      `Uppgift skapad: ${task.title}. Ansvarig: ${task.responsible || 'ej utsedd'}.`
      + ' Den ligger under Uppgifter. Bevakningen är oförändrad.',
    );
  }, []);

  async function scan() {
    setBusy(true);
    setScanning(true);
    setError('');
    setNotice('');
    try {
      const result = await watchesApi.scan(brfId);
      const count = result.proposed?.length || 0;
      setNotice(
        `Läste ${result.documentsRead} dokument. ${count} förslag att ta ställning till.`
        + ' Beslutade bevakningar rördes inte.',
      );
      await refresh();
    } catch (err) {
      setError(err.message || 'Genomläsningen kunde inte köras.');
    } finally {
      setScanning(false);
      setBusy(false);
    }
  }

  const settled = board?.settled || [];
  const proposed = board?.proposed || [];
  const unresolved = board?.unresolved || [];
  const watchedCount = useMemo(
    () => BUCKET_ORDER.reduce((sum, key) => sum + (board?.buckets?.[key]?.length || 0), 0),
    [board],
  );
  // A board that has never held anything is one state, not four empty
  // sections stacked on each other. Once anything exists — even only settled
  // history — the sections render and say their own emptiness in words.
  const nothingYet = watchedCount === 0
    && proposed.length === 0 && unresolved.length === 0 && settled.length === 0;

  return (
    <div className="watches">
      <header className="watches-header page-header">
        <div className="page-header-text">
          <h2 className="page-title">Bevakningar</h2>
          <p className="page-header-sub">
            Daterade skyldigheter lästa ur föreningens egna avtal. Motorn föreslår,
            en människa beslutar — ingenting här är en skyldighet förrän någon
            godkänt det.
          </p>
        </div>
        <div className="watches-header-actions">
          {isAdmin && (
            <button type="button" className="watches-scan" disabled={loading || busy} onClick={scan}>
              {scanning ? <Loader2 size={15} className="spin" /> : <ScanLine size={15} />} Läs om arkivet
            </button>
          )}
          <button type="button" className="watches-refresh" disabled={loading || busy} onClick={refresh}>
            <RefreshCw size={15} /> Uppdatera
          </button>
        </div>
      </header>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {loading && (
        <p className="watches-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>
      )}

      {!loading && board && (
        <>
          <p className="watches-summary">
            Dagens datum enligt servern: <strong>{board.today}</strong>.
            {' '}{watchedCount} bevakas, {proposed.length} väntar på beslut.
            {!isAdmin && ' Bara administratörer kan besluta om bevakningar.'}
          </p>

          {nothingYet && (
            <EmptyState
              title="Inga bevakningar ännu."
              actions={isAdmin ? (
                <button type="button" className="ui-btn ui-btn--primary" onClick={scan} disabled={busy || scanning}>
                  {scanning ? <Loader2 size={15} className="spin" /> : <ScanLine size={15} />} Läs om arkivet
                </button>
              ) : null}
            >
              Läs om arkivet så håller Träff koll på villkor som inte längre bör gälla.
            </EmptyState>
          )}

          {!nothingYet && (
          <>
          <section className="watches-board" aria-label="Bevakas">
            <h3>Bevakas</h3>
            <p className="muted">
              Det här har föreningen tagit på sig. Varje datum är godkänt av en
              människa.
            </p>
            <div className="watch-buckets">
              {BUCKET_ORDER.map((key) => {
                const rows = board.buckets?.[key] || [];
                return (
                  <section key={key} className={`watch-bucket ${key}`} aria-label={board.bucketLabels[key]}>
                    <h4>
                      {board.bucketLabels[key]}
                      <span className="bucket-count">{rows.length}</span>
                    </h4>
                    {key === 'recurring' && <MonthStrip today={board.today} watches={rows} />}
                    {rows.length === 0 ? (
                      <p className="empty">{EMPTY_BUCKET[key]}</p>
                    ) : rows.map((watch) => (
                      <BoardWatch
                        key={watch.id}
                        watch={watch}
                        brfId={brfId}
                        busy={busy}
                        canDecide={isAdmin}
                        onComplete={complete}
                        onDismiss={dismiss}
                        onOpenCitation={openCitation}
                        onTaskCreated={taskCreated}
                      />
                    ))}
                  </section>
                );
              })}
            </div>
          </section>

          <section className="watches-proposals" aria-label="Förslag">
            <h3>Förslag från genomläsningen</h3>
            <p className="muted">
              Det här har motorn läst ur avtalen. Ingenting nedan bevakas: varje
              rad visar datumet den räknat fram, uträkningen bakom det och
              passagen den lästes ur, och väntar på att någon tar ställning.
            </p>
            {proposed.length === 0 ? (
              <p className="empty">Inga förslag väntar på beslut.</p>
            ) : proposed.map((watch) => (
              <Proposal
                key={watch.id}
                watch={watch}
                busy={busy}
                canDecide={isAdmin}
                onApprove={approve}
                onDismiss={dismiss}
                onDelete={remove}
                onOpenCitation={openCitation}
              />
            ))}
          </section>

          <section className="watches-unresolved" aria-label="Tidsvillkor utan datum">
            <h3><HelpCircle size={17} /> Tidsvillkor som inte kunde dateras</h3>
            <p className="muted">
              Lästa villkor utan ett datum att räkna från. Det är ett svar, inte
              ett fel: <em>varför</em> säger vilken uppgift som gör villkoret
              daterbart — ett undertecknandedatum, en slutbesiktning. Ingen
              gissning görs, för en påhittad kalender är sämre än en tom.
            </p>
            {unresolved.length === 0 ? (
              <p className="empty">Inga sådana villkor i arkivet.</p>
            ) : unresolved.map((row) => (
              <article key={row.id} className="watch unresolved">
                <h4 className="watch-title">{row.what}</h4>
                <p className="watch-why">{row.why}</p>
                <Citations citations={row.citations} onOpen={openCitation} />
                <p className="muted">Läst ur {row.source_document_name || '—'}</p>
              </article>
            ))}
          </section>

          <details className="watches-settled">
            <summary>Avgjorda bevakningar ({settled.length})</summary>
            {settled.length === 0 ? (
              <p className="empty">Inget är avklarat eller avfärdat ännu.</p>
            ) : (
              <ul>
                {settled.map((watch) => (
                  <li key={watch.id}>
                    <span className="settled-title">{watch.title}</span>
                    <span className="settled-meta">
                      {watch.status_label} · {watch.decided_by || 'okänd'}
                      {' · '}{formatDateTime(watch.decided_at)}
                      {watch.succeeded_by && ' · efterföljare skapad'}
                    </span>
                    {watch.decision_note && (
                      <span className="settled-note">Anteckning: {watch.decision_note}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </details>
          </>
          )}
        </>
      )}

      {!loading && !board && !error && (
        <p className="empty"><AlertTriangle size={15} /> Inga bevakningsdata kunde läsas.</p>
      )}
    </div>
  );
}
