import React from 'react';
import { Search as SearchIcon, ArrowRight } from 'lucide-react';

// The Home/App-shell "Search" affordance (cleanup/verified-ui Task 4:
// cleanup-task-4-brief.md). Extracted verbatim from App.jsx's renderOverview
// hero-search markup so the wiring can be tested in isolation — same class
// names, same JSX, no behavior change.
//
// Fact established for this task (see cleanup-task-4-report.md): no
// /search backend endpoint exists (backend/app/main.py has no such route;
// src/api.js exposes no search()). This box was never a mock-search feature
// — it has always been the real ask flow's front door. App.jsx passes it the
// SAME `handleChatSubmit`/`askQuestion` functions the chat tab's own input
// uses (single function references, not a parallel/duplicated path), so
// submitting here calls straight into runAskQuestion (askQuestion.js),
// already proven end-to-end against the real api.ask() contract by
// askQuestion.test.js. Renders no results, counts, dates, or scores of its
// own — it is a pure input, never a results view
// (cleanup-global-constraints.md #1). The quarantined agent's separate
// "Search results" tab (see .superpowers/quarantine/INVENTORY.md, stash@{0})
// is unrelated to this box and was NOT salvaged — it had no real backend to
// wire to (see cleanup-task-4-report.md).
function HeroSearch({ chatInput, setChatInput, chatBusy, onSubmit, onSuggestionClick }) {
  const suggestions = [
    'Vad krävs för andrahandsuthyrning?',
    'När startar snöröjningsjouren?',
    'Vad kostar stambytet?',
  ];

  return (
    <div className="hero-search-container">
      <h1 className="hero-search-title">Vad vill du veta?</h1>
      <p className="hero-search-subtitle">Ställ frågor på svenska och få svar med exakta, verifierade källhänvisningar i dina PDF:er.</p>

      <div className="hero-search-box">
        <SearchIcon size={24} color="var(--accent-search)" className="hero-search-icon" />
        <input
          type="text"
          placeholder="T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'"
          className="hero-search-input"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          disabled={chatBusy}
        />
        <button className="hero-search-btn" onClick={onSubmit} disabled={chatBusy}>
          Fråga <ArrowRight size={18} />
        </button>
      </div>

      <div className="hero-search-suggestions">
        {suggestions.map((q) => (
          <span key={q} className="suggestion-pill" onClick={() => onSuggestionClick(q)} style={{ cursor: 'pointer' }}>
            {q}
          </span>
        ))}
      </div>
    </div>
  );
}

export default HeroSearch;
