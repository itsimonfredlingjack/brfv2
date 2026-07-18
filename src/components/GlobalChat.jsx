import React, { useState } from 'react';
import { Sparkles, ArrowRight, Loader2, AlertCircle, CornerDownRight, ChevronRight, FileText } from 'lucide-react';
import { MOCK_DOCUMENTS } from '../data/MockData';

export default function GlobalChat({ openDocument, initialQuery }) {
  const [chatInput, setChatInput] = useState(initialQuery || '');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [scopeMenuOpen, setScopeMenuOpen] = useState(false);

  // If initialQuery is set and messages are empty, we might auto-execute. For simplicity, just use the input.
  const executeChat = (query) => {
    if (!query.trim() || chatBusy) return;
    setChatInput('');
    
    const newUserMsg = { role: 'user', content: query };
    const pendingAiMsg = { role: 'ai', pending: true, content: 'Söker och analyserar (MOCK)...' };
    
    setChatMessages(prev => [...prev, newUserMsg, pendingAiMsg]);
    setChatBusy(true);

    setTimeout(() => {
      setChatMessages(prev => {
        const withoutPending = prev.slice(0, -1);
        const q = query.toLowerCase();
        
        if (q.includes('katter') || q.includes('hundar')) {
           return [...withoutPending, {
             role: 'ai',
             content: 'Jag hittar ingen information i de indexerade dokumenten som behandlar husdjur eller katter.',
             refusal: true
           }];
        }

        return [...withoutPending, {
          role: 'ai',
          content: 'Enligt stadgarna krävs alltid styrelsens samtycke för att få hyra ut i andra hand.',
          citations: [
            { quote: 'styrelsen ger sitt samtycke', document_name: 'Stadgar Brf Gjutformen 12 MOCK.pdf', page: 12, document_id: 'd2' }
          ]
        }];
      });
      setChatBusy(false);
    }, 1000);
  };

  return (
    <div className="tab-content">
      <div className="chat-container">
        <div className="chat-header">
          <div>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles color="var(--ai-accent)" size={24}/> Global AI-assistent
            </h2>
            <p className="chat-subtitle">Ställ frågor över alla föreningens indexerade dokument.</p>
          </div>
          
          <div className="chat-scope-selector desktop-only" style={{ position: 'relative' }}>
             <span className="scope-label">Söker i:</span>
             <button className="scope-btn" onClick={() => setScopeMenuOpen(!scopeMenuOpen)} aria-haspopup="true" aria-expanded={scopeMenuOpen}>
               Alla dokument · {MOCK_DOCUMENTS.length} st <ChevronRight size={14}/>
             </button>
             {scopeMenuOpen && (
               <div className="report-menu" style={{ right: 0, left: 'auto', bottom: 'auto', top: '100%', marginTop: '8px' }}>
                 <div style={{ padding: '8px 12px', fontSize: '12px', color: 'var(--text-muted)' }}>MOCKUP: Global sökning aktiv</div>
                 {MOCK_DOCUMENTS.map(d => (
                   <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                     <FileText size={14} /> <span className="truncate">{d.name}</span>
                   </div>
                 ))}
               </div>
             )}
          </div>
        </div>

        <div className="chat-messages-area">
          {chatMessages.length === 0 ? (
            <div className="chat-empty-state">
               <Sparkles size={40} color="var(--ai-accent)" style={{ marginBottom: '16px', opacity: 0.5 }} />
               <h3 style={{ marginBottom: '24px' }}>Vad vill du ha hjälp med?</h3>
               <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%', maxWidth: '400px' }}>
                 <button className="example-prompt-btn" onClick={() => executeChat('Vad säger stadgarna om andrahandsuthyrning?')}>
                   Vad säger stadgarna om andrahandsuthyrning?
                 </button>
                 <button className="example-prompt-btn" onClick={() => executeChat('Vilka datum gäller för snöröjningsjouren?')}>
                   Vilka datum gäller för snöröjningsjouren?
                 </button>
               </div>
            </div>
          ) : (
            chatMessages.map((msg, idx) => (
              <div key={idx} className={`chat-message ${msg.role}`}>
                <div className="chat-avatar">
                  {msg.role === 'ai' ? (msg.pending ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />) : 'DU'}
                </div>
                <div className="chat-message-body">
                  <div className={`chat-content ${msg.refusal ? 'refusal' : ''}`}>
                    {msg.refusal && <div className="chat-refusal-header"><AlertCircle size={14} /> Otillräckligt underlag</div>}
                    {msg.content}
                    
                    {msg.citations && (
                      <div className="chat-citations">
                        {msg.citations.map((c, i) => (
                          <button key={i} className="citation-pill interactive" onClick={() => openDocument(c.document_id, c.page, 'read')} title="Öppna källdokumentet">
                            <span className="citation-number">[{i + 1}]</span>
                            <span className="citation-text">"{c.quote}"</span>
                            <span className="citation-source">— {c.document_name} s.{c.page}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {msg.followUps && !msg.pending && (
                    <div className="chat-followups">
                      {msg.followUps.map((fu, fidx) => (
                        <button key={fidx} className="followup-btn" onClick={() => executeChat(fu)}>
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
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && executeChat(chatInput)}
              placeholder="Ställ en generell fråga till AI:n..."
              disabled={chatBusy}
            />
            <button className="chat-send-btn" onClick={() => executeChat(chatInput)} disabled={chatBusy || !chatInput.trim()} aria-label="Skicka fråga">
              {chatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
