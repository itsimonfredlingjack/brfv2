import React from 'react';
import { FileText, Search as SearchIcon } from 'lucide-react';

// Presentational source panel for the dual-pane chat layout
// (cleanup/verified-ui Task 2, salvaging the layout idea documented in
// .superpowers/quarantine/INVENTORY.md §3(a)). Receives `citations`
// (App.jsx's chatResponseMapping.latestCitations(chatMessages) — the
// latest completed ai message's real AskResponse.citations[]) and renders
// each entry 1:1: document_name, page, and the verified `quote` display
// string exactly as returned (multi-span keeps " […] " — never joined
// into a seamless sentence). It invents nothing of its own
// (cleanup-global-constraints.md #1-2).
function CitationsPanel({ citations, openDocViewer }) {
  return (
    <div className="citations-panel">
      <div className="citations-panel-header">
        <FileText size={18} />
        Källhänvisningar
      </div>
      <div className="citations-panel-content">
        {citations.length === 0 ? (
          <div className="citations-panel-empty">
            <SearchIcon size={20} />
            <p>Inga verifierade källor för den senaste frågan ännu.</p>
          </div>
        ) : (
          citations.map((c, i) => (
            <div key={i} className="citation-card">
              <div className="citation-card-header">
                <span className="citation-card-badge">{i + 1}</span>
                <span className="citation-card-title" title={c.document_name}>{c.document_name}</span>
              </div>
              <p className="citation-card-quote">&quot;{c.quote}&quot;</p>
              <button
                className="citation-card-action"
                onClick={() => openDocViewer(c, { page: c.page, rects: c.rects, highlightPage: c.page })}
              >
                <FileText size={14} /> Öppna på s. {c.page}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default CitationsPanel;
