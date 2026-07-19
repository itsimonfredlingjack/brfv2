import React, { forwardRef } from 'react';
// Dev-gated demo scaffolding (cleanup/verified-ui Task 5) — this component
// is only ever reached via DemoWorkspace.jsx's dynamic import, which is
// itself only wired up when import.meta.env.DEV is true (see App.jsx and
// src/appModes.js). documentData is fabricated: it never came from a real
// PDF extraction. See src/demoData.js's header comment for the full
// rationale and src/no-fabrication.test.js for the allowlist it's held to.
import { documentData } from '../demoData';

const DocumentView = forwardRef(({ activeId, searchMode }, ref) => {
  return (
    <div className={`document-container ${activeId ? 'shifted' : ''}`}>
      <div className="document-header">
        <h1 className="document-title">SNÖRÖJNINGSAVTAL 2024</h1>
        <div className="document-meta">
          <span>Version 1.2</span>
          <span>Godkänd: 2024-09-01</span>
          <span>Sida 2 av 14</span>
        </div>
      </div>

      <div className="document-content">
        {documentData.map((p, index) => {
          const isActive = activeId === p.id;
          const isDimmed = activeId && !isActive;

          let content = p.text;

          // Apply internal highlights if this paragraph is active and has a highlightWord
          if (isActive && p.highlightWord) {
            const parts = p.text.split(p.highlightWord);
            const highlightClass = p.type === 'deadline' ? 'highlight-date' : 'highlight-search';
            content = (
              <>
                {parts[0]}
                <span className={highlightClass}>{p.highlightWord}</span>
                {parts[1]}
              </>
            );
          }

          let className = `paragraph`;
          if (isActive) {
            className += p.type === 'deadline' ? ' active-deadline focused-line' : ' active-search focused-line';
          } else if (isDimmed) {
            className += ' dimmed';
          }

          return (
            <div
              key={p.id}
              id={p.id}
              className={className}
              ref={el => {
                if (ref && ref.current) {
                  ref.current[p.id] = el;
                }
              }}
            >
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
});

export default DocumentView;
