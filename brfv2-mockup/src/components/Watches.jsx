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
import Instrument from './Instrument';
import Arendekort from './Arendekort';
import Avsnitt from './Avsnitt';
import './Watches.css';
import { datum, datumTid } from './datum';

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
  const citation = watch.citations?.[0];

  return (
    <Arendekort
      tillstand={{ form: 'belagd', text: watch.status_label }}
      namn={watch.title}
      figur={watch.due_date}
      fakta={[
        { etikett: 'slag', varde: watch.kind_label },
        { etikett: '', varde: daysLeftText(watch.days_left), matt: true },
        { etikett: 'ansvarig', varde: watch.responsible || 'ej utsedd' },
        { etikett: 'påminns', varde: `${watch.remind_at}, ${watch.remind_lead_days} d före` },
        ...(watch.recurrence !== 'none'
          ? [{ etikett: 'återkommer', varde: RECURRENCE_LABEL[watch.recurrence] || watch.recurrence }]
          : []),
      ]}
      kalla={citation ? {
        text: `${citation.document_name} · s. ${citation.page}`,
        onOpen: () => onOpenCitation(citation),
      } : undefined}
      atgarder={(
        <>
          {canDecide && (
            <>
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
            </>
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
        </>
      )}
    >
      {moved ? (
        <>
          Motorn räknade fram <strong>{watch.derived_due_date}</strong> ur {watch.derivation}.
          {' '}En människa har flyttat datumet till <strong>{watch.due_date}</strong>.
        </>
      ) : (
        <>Datumet är motorns eget: {watch.derivation}. En människa har godkänt det.</>
      )}
      {watch.decision_note ? ` Anteckning: ${watch.decision_note}` : ''}
    </Arendekort>
  );
}

/**
 * The horizon: every watched obligation plotted against the twelve months
 * ahead, with what's already late held apart in its own column.
 *
 * This is the page's opening statement, not a widget buried in one bucket —
 * Bevakningar's whole reason to exist is "what's coming and when," and until
 * now that fact lived only as rows of text below the fold. A person should
 * see the shape of the year — where the obligations cluster, whether
 * anything is already late — before reading a single card.
 *
 * Bar height carries the count, not colour: a taller column is more due that
 * month, full stop. "Nu" (already late) gets the one weight-based mark this
 * identity allows for overdue (an ink underline, §01/theme.css's own rule) —
 * never a red bar, because lateness here is a fact stated in weight, not an
 * alarm colour.
 */
const HORIZON_BAR_MAX = 96;

function horizonBarHeight(count, max) {
  if (count === 0) return 2;
  return Math.round(Math.max(10, (count / max) * HORIZON_BAR_MAX));
}

function Horizon({ today, overdue, upcoming }) {
  const cells = useMemo(() => {
    const [year, month] = today.split('-').map(Number);
    return Array.from({ length: 12 }, (_, i) => {
      const index = month - 1 + i;
      const key = `${year + Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
      return {
        key,
        label: MONTHS[index % 12],
        items: upcoming.filter((w) => w.due_date && w.due_date.startsWith(key)),
      };
    });
  }, [today, upcoming]);

  const max = Math.max(1, overdue.length, ...cells.map((c) => c.items.length));

  return (
    <div className="watches-horizon" aria-label="Bevakningar över tid">
      <ol className="horizon-strip">
        <li className={`horizon-cell horizon-now${overdue.length > 0 ? ' loaded overdue' : ''}`}>
          <span className="horizon-bar" style={{ height: `${horizonBarHeight(overdue.length, max)}px` }} />
          <span className="horizon-count">{overdue.length || ''}</span>
          <span className="horizon-label">Nu</span>
        </li>
        {cells.map((cell) => (
          <li
            key={cell.key}
            className={`horizon-cell${cell.items.length > 0 ? ' loaded' : ''}`}
            title={cell.items.length > 0
              ? cell.items.map((w) => `${w.due_date} ${w.title}`).join('\n')
              : `${cell.key}: inget`}
          >
            <span className="horizon-bar" style={{ height: `${horizonBarHeight(cell.items.length, max)}px` }} />
            <span className="horizon-count">{cell.items.length || ''}</span>
            <span className="horizon-label">{cell.label}</span>
          </li>
        ))}
      </ol>
    </div>
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
            Daterade skyldigheter ur föreningens avtal. Motorn föreslår, en människa beslutar.
          </p>
        </div>
        <div className="page-header-actions">
          {isAdmin && (
            <button type="button" className="watches-scan" disabled={loading || busy} onClick={scan}>
              {scanning ? <Loader2 size={15} className="spin" /> : <ScanLine size={15} />} Läs om arkivet
            </button>
          )}
          <button type="button" className="watches-refresh" disabled={loading || busy} onClick={refresh}>
            <RefreshCw size={15} /> Uppdatera
          </button>
        </div>

        {/* Bevakningar's instrument is time, so the horizon belongs *in* the
            band rather than under it: twelve months drawn in paper on ink is
            the screen's own composition, not a chart parked on the page. It
            needs `board` for the server's own date, so the band renders a
            static twelve-month scale until that lands — the shape never
            appears or disappears, only its bars do.

            The four state counts used to sit on paper below the band while
            Fakturor's sat inside it — the same widget with two different homes,
            one tab apart. They belong on the faceplate, to the right of the
            chart, exactly where Fakturor puts its own. */}
        <Instrument
          lead={board ? (
            <Horizon
              today={board.today}
              overdue={board.buckets?.overdue || []}
              upcoming={[
                ...(board.buckets?.soon || []),
                ...(board.buckets?.later || []),
                ...(board.buckets?.recurring || []),
              ]}
            />
          ) : null}
          readings={[
            { label: 'Bevakas', value: watchedCount },
            { label: 'Förslag', value: proposed.length },
            {
              label: 'Försenat',
              value: board?.buckets?.overdue?.length || 0,
              flagged: (board?.buckets?.overdue?.length || 0) > 0,
            },
            { label: 'Odaterat', value: unresolved.length },
          ]}
        />
      </header>

      <Banner tone="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner tone="ok" onDismiss={() => setNotice('')}>{notice}</Banner>

      {loading && (
        <p className="watches-loading"><Loader2 size={16} className="spin" /> Hämtar…</p>
      )}

      {!loading && board && (
        <>
          {/* The horizon's own "Nu" column already anchors today, so restating
              the server's date above it was a second clock on the same wall. */}
          {!isAdmin && (
            <p className="watches-today">
              Bara administratörer kan besluta om bevakningar.
            </p>
          )}

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
              {BUCKET_ORDER.map((key, i) => {
                const rows = board.buckets?.[key] || [];
                return (
                  <section key={key} className={`watch-bucket ${key}`} aria-label={board.bucketLabels[key]}>
                    <Avsnitt
                      nummer={String(i + 1).padStart(2, '0')}
                      namn={board.bucketLabels[key]}
                    >
                      {rows.length === 0
                        ? EMPTY_BUCKET[key]
                        : `${rows.length} ${rows.length === 1 ? 'bevakning' : 'bevakningar'}.`}
                    </Avsnitt>
                    {rows.length > 0 && rows.map((watch) => (
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
                      {' · '}{datumTid(watch.decided_at)}
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
