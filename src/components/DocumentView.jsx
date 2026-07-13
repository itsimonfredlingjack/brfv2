import React, { forwardRef } from 'react';

// Simulated extracted paragraphs from SNÖRÖJNINGSAVTAL_2024.pdf
export const documentData = [
  {
    id: 'p1',
    text: 'Detta avtal ("Avtalet") är upprättat mellan Beställaren och Entreprenören avseende snöröjning och halkbekämpning för perioden 2024-2025.',
  },
  {
    id: 'p2',
    text: 'Entreprenören åtar sig att utföra snöröjning och halkbekämpning på de ytor som anges i Bilaga 1. Arbetet ska utföras fackmannamässigt och i enlighet med gällande branschstandard.',
  },
  {
    id: 'p3',
    text: 'Snöröjningsjour startar årligen den 15 november och pågår fram till den 15 april. Under denna period ska Entreprenören vara tillgänglig dygnet runt.',
    highlightWord: '15 november',
    type: 'deadline'
  },
  {
    id: 'p4',
    text: 'Vid snöfall som överstiger 5 cm ska plogning påbörjas senast inom 2 timmar från det att snöfallet upphört. Om det snöar ihållande ska kontinuerlig plogning ske för att säkerställa framkomlighet.',
  },
  {
    id: 'p5',
    text: 'Halkbekämpning (saltning eller sandning) ska utföras förebyggande när risk för frosthalka föreligger, samt senast inom 1 timme efter avslutad snöröjning om behov finns för att förhindra isbildning.',
    highlightWord: 'saltning eller sandning',
    type: 'search'
  },
  {
    id: 'p6',
    text: 'Fakturering sker månadsvis i efterskott. Fakturan ska innehålla specifikation över utförda insatser, datum och klockslag. Betalningsvillkor är 30 dagar netto.',
  }
];

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
