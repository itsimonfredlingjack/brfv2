import React, { useState } from 'react';
import { Sparkles, ArrowRight, Loader2, AlertCircle, CornerDownRight, AlertTriangle, Info } from 'lucide-react';

export default function DocumentChat({ selectedDocument, setPdfPage }) {
  const [workspaceChatInput, setWorkspaceChatInput] = useState('');
  const [workspaceChatMessages, setWorkspaceChatMessages] = useState([]);
  const [workspaceChatBusy, setWorkspaceChatBusy] = useState(false);
  const [demoState, setDemoState] = useState('standard'); 

  const executeWorkspaceChat = (queryStr) => {
    const query = queryStr || workspaceChatInput;
    if (!query.trim() || workspaceChatBusy) return;
    
    setWorkspaceChatInput('');
    
    const newUserMsg = { role: 'user', content: query };
    const pendingAiMsg = { role: 'ai', pending: true, content: 'Analyserar dokumentet (MOCK)...' };
    
    setWorkspaceChatMessages(prev => [...prev, newUserMsg, pendingAiMsg]);
    setWorkspaceChatBusy(true);

    setTimeout(() => {
      setWorkspaceChatMessages(prev => {
        const withoutPending = prev.slice(0, -1);
        
        if (demoState === 'no-answer') {
           return [...withoutPending, {
             role: 'ai',
             content: 'Jag hittar ingen information i det här dokumentet som besvarar din fråga. Jag avstår från att svara för att undvika gissningar.',
             refusal: true
           }];
        }
        
        if (demoState === 'conflict') {
           return [...withoutPending, {
             role: 'ai',
             content: 'Det finns motstridig information i dokumentet. På sida 1 står det att jouren startar 15 november, men ett senare tillägg på sida 2 antyder att den kan starta 1 december vid mildväder. Det rekommenderas att verifiera detta med styrelsen.',
             refusal: true,
             warning: true,
             citations: [
               { quote: 'Jouren träder i kraft den 15 november', page: 1 },
               { quote: 'Tillägg: 1 december vid mildväder', page: 2 }
             ]
           }];
        }

        return [...withoutPending, {
          role: 'ai',
          content: 'Jouren träder i kraft den 15 november och pågår till den 15 april.',
          citations: [
            { quote: 'Jouren träder i kraft den 15 november och pågår till den 15 april', page: 1 }
          ],
          followUps: ["Hur mycket kostar det?", "När måste de påbörja snöröjningen?"]
        }];
      });
      setWorkspaceChatBusy(false);
    }, 1200);
  };

  return (
    <div className="workspace-chat-container half full-width-mobile">
      <div className="workspace-chat-header">
         <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--ai-accent)' }}>
           <Sparkles size={18} />
           <span style={{ fontWeight: '500' }}>AI-chatt för detta dokument</span>
         </div>
         
         <div className="demo-state-selector">
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }} className="desktop-only">MOCK-STATE:</span>
            <select value={demoState} onChange={e => setDemoState(e.target.value)} title="Ändra vilket svar AI:n tvingas ge i mockupen." aria-label="Välj AI svarstillstånd">
              <option value="standard">Svar med citat</option>
              <option value="no-answer">Otillräckligt underlag</option>
              <option value="conflict">Motstridiga källor</option>
            </select>
         </div>
      </div>

      <div className="chat-messages-area">
        {workspaceChatMessages.length === 0 ? (
          <div className="chat-empty-state">
             <Info size={32} color="var(--text-muted)" style={{ marginBottom: '16px', opacity: 0.5 }} />
             <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '24px' }}>
               Ställ frågor specifikt om innehållet i <strong>{selectedDocument.name}</strong>.
             </p>
             <button className="example-prompt-btn" onClick={() => executeWorkspaceChat('När startar jouren?')}>När startar jouren?</button>
          </div>
        ) : (
          workspaceChatMessages.map((msg, idx) => (
            <div key={idx} className={`chat-message ${msg.role}`}>
              <div className="chat-avatar">
                {msg.role === 'ai' ? (msg.pending ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />) : 'DU'}
              </div>
              <div className="chat-message-body">
                <div className={`chat-content ${msg.refusal && !msg.warning ? 'refusal' : ''} ${msg.warning ? 'warning' : ''}`}>
                  {msg.refusal && !msg.warning && <div className="chat-refusal-header"><AlertCircle size={14} /> Otillräckligt underlag</div>}
                  {msg.warning && <div className="chat-refusal-header warning"><AlertTriangle size={14} /> Motstridiga källor</div>}
                  {msg.content}
                  
                  {msg.citations && (
                    <div className="chat-citations">
                      {msg.citations.map((c, i) => (
                        <button key={i} className="citation-pill interactive" onClick={() => setPdfPage(c.page)} title={`Gå till sida ${c.page}`}>
                          <span className="citation-number">[{i + 1}]</span>
                          <span className="citation-text">"{c.quote}"</span>
                          <span className="citation-source">— s.{c.page}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                
                {msg.followUps && !msg.pending && (
                  <div className="chat-followups">
                    {msg.followUps.map((fu, fidx) => (
                      <button key={fidx} className="followup-btn" onClick={() => executeWorkspaceChat(fu)}>
                        <CornerDownRight size={14}/> {fu}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <input
            type="text"
            value={workspaceChatInput}
            onChange={(e) => setWorkspaceChatInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && executeWorkspaceChat()}
            placeholder={`Fråga om ${selectedDocument.name}...`}
            disabled={workspaceChatBusy}
          />
          <button className="chat-send-btn" onClick={() => executeWorkspaceChat()} disabled={workspaceChatBusy || !workspaceChatInput.trim()} aria-label="Skicka fråga">
            {workspaceChatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}
