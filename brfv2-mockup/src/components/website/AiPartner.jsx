import React, { useEffect, useRef, useState } from 'react';
import {
  CornerUpLeft,
  FileText,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  SendHorizontal,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import { websiteApi } from '../../api';

// The AI partner: a conversation, a record of what it changed, and a way to take
// any of it back.
//
// Three things it deliberately shows that a plain chat panel would not:
//
// - **What is selected right now.** The instruction "korta den markerade texten"
//   only means something if both sides agree on what is marked, so the panel
//   states it above the input rather than leaving the operator to guess.
// - **Where the words came from.** A change built out of the association's own
//   documents lists them, and each one opens the PDF at the cited page — the
//   same evidence trail the rest of the product runs on.
// - **A refusal, in full.** When the model wanted to write something the
//   documents do not support, the panel says so and says nothing was written.
//   That is the product working, not an error to hide.

function ContextChip({ selection, selectedType }) {
  if (!selection.block_id) {
    return <div className="ai-context">Inget markerat — ändringen gäller sidan.</div>;
  }
  const parts = [selectedType || 'block'];
  if (selection.field) parts.push(`fältet ${selection.field}`);
  if (selection.selected_text) {
    const text = selection.selected_text.trim();
    parts.push(`”${text.length > 40 ? `${text.slice(0, 40)}…` : text}”`);
  }
  return <div className="ai-context ai-context--active">Markerat: {parts.join(' · ')}</div>;
}

function Entry({ entry, onUndo, onOpenCitation, undoing }) {
  if (entry.kind === 'user') {
    return <div className="ai-msg ai-msg--user">{entry.text}</div>;
  }

  if (entry.kind === 'refusal') {
    return (
      <div className="ai-msg ai-msg--refusal">
        <div className="ai-msg__label">
          <ShieldAlert size={14} aria-hidden="true" /> Ingenting skrevs
        </div>
        <p>{entry.text}</p>
      </div>
    );
  }

  if (entry.kind === 'note') {
    return <div className="ai-msg ai-msg--note">{entry.text}</div>;
  }

  return (
    <div className="ai-msg ai-msg--change">
      <div className="ai-msg__label">
        <Sparkles size={14} aria-hidden="true" /> AI-ändring
      </div>
      <div className="ai-change__summary">{entry.summary}</div>
      {entry.message ? <p className="ai-change__message">{entry.message}</p> : null}
      <div className="ai-change__meta">
        {entry.operationCount} {entry.operationCount === 1 ? 'operation' : 'operationer'}
      </div>

      {(entry.sources || []).length > 0 && (
        <div className="ai-change__sources">
          <div className="ai-change__sources-label">Källor</div>
          {entry.sources.map((citation, i) => (
            <button
              key={i}
              type="button"
              className="ai-change__source"
              onClick={() => onOpenCitation?.(citation)}
              title={citation.quote}
            >
              <FileText size={12} aria-hidden="true" />
              <span>{citation.document_name}, s. {citation.page}</span>
            </button>
          ))}
        </div>
      )}

      {entry.transactionId && !entry.undone && (
        <button
          type="button"
          className="ai-change__undo"
          onClick={() => onUndo(entry.transactionId)}
          disabled={undoing}
        >
          <CornerUpLeft size={13} aria-hidden="true" /> Ångra allt
        </button>
      )}
      {entry.undone && <div className="ai-change__undone">Ångrad</div>}
    </div>
  );
}

export default function AiPartner({
  brfId,
  isAdmin,
  collapsed,
  onToggleCollapse,
  selection,
  selectedType,
  history,
  onApplied,
  onUndo,
  onOpenCitation,
}) {
  const [entries, setEntries] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length, busy]);

  // An undo can also come from elsewhere (the history list, another session), so
  // the panel reads the server's record rather than only its own memory.
  const undoneIds = new Set((history || []).filter((t) => t.undone_by).map((t) => t.id));

  const send = async () => {
    const instruction = input.trim();
    if (!instruction || busy) return;
    setInput('');
    setEntries((prev) => [...prev, { kind: 'user', text: instruction }]);
    setBusy(true);
    try {
      const result = await websiteApi.ai(brfId, { instruction, ...selection });
      if (result.applied) {
        setEntries((prev) => [...prev, {
          kind: 'change',
          summary: result.transaction.summary,
          message: result.message,
          operationCount: result.transaction.operation_count,
          transactionId: result.transaction.id,
          sources: result.sources || [],
        }]);
        onApplied(result);
      } else if (result.refusal) {
        setEntries((prev) => [...prev, { kind: 'refusal', text: result.refusal }]);
        onApplied(result);
      } else {
        setEntries((prev) => [...prev, { kind: 'note', text: result.message || 'Ingen ändring gjordes.' }]);
      }
    } catch (err) {
      setEntries((prev) => [...prev, {
        kind: 'refusal',
        text: err.message || 'AI-assistenten gick inte att nå. Ingenting skrevs.',
      }]);
    } finally {
      setBusy(false);
    }
  };

  const undo = async (transactionId) => {
    setUndoing(true);
    try {
      await onUndo(transactionId);
      setEntries((prev) => prev.map((entry) => (
        entry.transactionId === transactionId ? { ...entry, undone: true } : entry
      )));
    } catch (err) {
      setEntries((prev) => [...prev, { kind: 'refusal', text: err.message || 'Ångringen gick inte igenom.' }]);
    } finally {
      setUndoing(false);
    }
  };

  if (collapsed) {
    return (
      <aside className="ai-panel ai-panel--collapsed" aria-label="AI-partner">
        <button type="button" className="ai-collapse" onClick={onToggleCollapse} title="Visa AI-partner">
          <PanelLeftOpen size={16} />
        </button>
        <div className="ai-panel__rail">
          <Sparkles size={16} aria-hidden="true" />
          <span>AI-partner</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className="ai-panel" aria-label="AI-partner">
      <header className="ai-panel__head">
        <div className="ai-panel__title">
          <Sparkles size={15} aria-hidden="true" />
          <span>AI-partner</span>
        </div>
        <button type="button" className="ai-collapse" onClick={onToggleCollapse} title="Dölj AI-partner">
          <PanelLeftClose size={16} />
        </button>
      </header>

      <div className="ai-panel__list" ref={listRef}>
        {entries.length === 0 && (
          <div className="ai-empty">
            <p>Beskriv vad du vill ändra på sidan.</p>
            <ul>
              <li>”Skriv ett meddelande om att vattnet stängs av 12 mars 08–15”</li>
              <li>”Korta den markerade texten och gör den tydligare”</li>
              <li>”Flytta detta under nyheterna”</li>
              <li>”Skapa en sida för nya boende och lägg den i menyn efter För boende”</li>
            </ul>
            <p className="ai-empty__note">
              Sakuppgifter om föreningen hämtas ur era egna dokument, med källa. Det
              som inte går att belägga skrivs inte.
            </p>
          </div>
        )}

        {entries.map((entry, i) => (
          <Entry
            key={i}
            entry={{ ...entry, undone: entry.undone || undoneIds.has(entry.transactionId) }}
            onUndo={undo}
            onOpenCitation={onOpenCitation}
            undoing={undoing}
          />
        ))}

        {busy && (
          <div className="ai-msg ai-msg--thinking">
            <Loader2 size={14} className="site-spin" aria-hidden="true" /> Arbetar…
          </div>
        )}
      </div>

      <div className="ai-panel__composer">
        <ContextChip selection={selection} selectedType={selectedType} />
        <div className="ai-input">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={isAdmin ? 'Vad ska ändras?' : 'Bara administratörer kan ändra webbplatsen.'}
            rows={2}
            disabled={!isAdmin || busy}
            aria-label="Instruktion till AI-partnern"
          />
          <button
            type="button"
            onClick={send}
            disabled={!isAdmin || busy || !input.trim()}
            aria-label="Skicka"
          >
            <SendHorizontal size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}
