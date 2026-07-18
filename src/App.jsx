import React, { useState } from 'react';
import { LayoutDashboard, MessageSquare, Folders, Settings, Search as SearchIcon, Filter, FileText, ArrowRight, Loader2, Sparkles, AlertCircle, Calendar, Upload, CheckCircle2, Clock, AlertTriangle, ArrowUpRight, Plus, X, ChevronRight, CornerDownRight, ArrowLeft, ZoomIn, ZoomOut, Search, Check, ThumbsDown, MessageCircle, Info } from 'lucide-react';
import './App.css';

// --- MOCK DATA ---
const MOCK_DOCUMENTS = [
  { id: 'd1', name: 'Snöröjningsavtal 2026 MOCK.pdf', date: '2026-07-16', pages: 2, status: 'Klar', qa: 'Klar', bevakningar: 1 },
  { id: 'd2', name: 'Stadgar Brf Gjutformen 12 MOCK.pdf', date: '2026-07-15', pages: 18, status: 'Klar', qa: 'Behöver granskas', bevakningar: 0 },
  { id: 'd3', name: 'Styrelseprotokoll 2026-03-12 MOCK.pdf', date: '2026-03-14', pages: 4, status: 'Klar', qa: 'Klar', bevakningar: 2 },
  { id: 'd4', name: 'Årsredovisning 2025 MOCK.pdf', date: '2026-02-10', pages: 32, status: 'Behandlas', qa: 'Ej påbörjad', bevakningar: 0 },
  { id: 'd5', name: 'Underhållsplan 2026-2036 MOCK.pdf', date: '2026-01-05', pages: 14, status: 'Klar', qa: 'Klar', bevakningar: 3 },
];

const MOCK_BEVAKNINGAR = [
  { id: 'b1', docId: 'd1', title: 'Start snöröjningsjour', date: '15 Nov 2026', desc: 'Jouren träder i kraft och pågår till 15 april.', page: 1, done: false },
  { id: 'b2', docId: 'd3', title: 'Städdag', date: '24 Apr 2026', desc: 'Vårstädning av innegården.', page: 3, done: true },
  { id: 'b3', docId: 'd3', title: 'Filterbyte', date: '10 Okt 2026', desc: 'Byte av ventilationsfilter i alla lägenheter.', page: 4, done: false },
];

const MOCK_SEARCH_RESULTS = {
  query: 'andrahandsuthyrning',
  status: 'success',
  totalDocuments: 3,
  totalPassages: 5,
  results: [
    {
      id: 'res1',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 12,
      date: '2026-07-15',
      excerpt: "Bostadsrättshavaren får upplåta sin lägenhet i andra hand till annan för självständigt brukande endast om styrelsen ger sitt samtycke. Samtycke ska lämnas om bostadsrättshavaren har beaktansvärda skäl för upplåtelsen och föreningen inte har någon befogad anledning att vägra samtycke.",
      highlights: ['andra hand', 'samtycke', 'upplåtelse'],
    },
    {
      id: 'res2',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 14,
      date: '2026-07-15',
      excerpt: "Avgiften för andrahandsuthyrning uppgår till 10% av prisbasbeloppet per år. En upplåtelse i andra hand som sker utan samtycke är grund för förverkande av bostadsrätten.",
      highlights: ['andrahandsuthyrning', 'andra hand', 'utan samtycke'],
    }
  ]
};

const MOCK_TEXT_EXTRACTION = {
  d1: {
    1: "AVTAL OM SNÖRÖJNING\n\nMellan Brf Gjutformen 12 och Vintertjänst AB.\n\n1. Omfattning\nEntreprenören åtar sig att utföra snöröjning och halkbekämpning av fastigheten Gjutformen 12.\n\n2. Tider\nJouren träder i kraft den 15 november och pågår till den 15 april varje år. Snöröjning ska påbörjas senast 2 timmar efter att snödjupet överstiger 5 cm.",
    2: "3. Avgift\nFöreningen betalar en fast avgift om 15 000 kr per säsong exklusive moms.\n\n4. Uppsägning\nAvtalet löper på 1 år och förlängs automatiskt om det inte sägs upp senast 3 månader innan avtalsperiodens utgång.\n\nSignaturer:\n[Olsläslig kråka] [Olsläslig kråka]"
  }
};

function App() {
  const [currentTab, setCurrentTab] = useState('home');
  const [selectedDocument, setSelectedDocument] = useState(null);
  
  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchIsLoading, setSearchIsLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  
  // Doc Filter State
  const [docFilter, setDocFilter] = useState('alla');

  // Workspace State
  const [workspaceTab, setWorkspaceTab] = useState('read'); // 'read', 'review', 'chat'
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [workspaceChatInput, setWorkspaceChatInput] = useState('');
  const [workspaceChatMessages, setWorkspaceChatMessages] = useState([]);
  const [workspaceChatBusy, setWorkspaceChatBusy] = useState(false);
  const [demoState, setDemoState] = useState('standard'); // 'standard', 'no-answer', 'conflict'
  const [reportMenuOpen, setReportMenuOpen] = useState(false);

  // General Chat State
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatScope, setChatScope] = useState('Alla dokument · 14 dokument');

  const executeSearch = (query) => {
    if (!query.trim()) return;
    setSearchQuery(query);
    setCurrentTab('search');
    setSelectedDocument(null);
    setSearchIsLoading(true);
    
    setTimeout(() => {
      setSearchResults(MOCK_SEARCH_RESULTS);
      setSearchIsLoading(false);
    }, 800);
  };

  const openDocument = (docId, initialPage = 1, initialTab = 'read') => {
    const doc = MOCK_DOCUMENTS.find(d => d.id === docId);
    if (doc) {
      setSelectedDocument(doc);
      setPdfPage(initialPage);
      setWorkspaceTab(initialTab);
      setPdfZoom(100);
      setWorkspaceChatMessages([]);
    }
  };

  const closeDocument = () => {
    setSelectedDocument(null);
  };

  const executeWorkspaceChat = () => {
    if (!workspaceChatInput.trim() || workspaceChatBusy) return;
    const query = workspaceChatInput;
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

  const executeGeneralChat = (query) => {
    if (!query.trim() || chatBusy) return;
    setCurrentTab('chat');
    setChatInput('');
    setSelectedDocument(null);
    
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
            { quote: 'styrelsen ger sitt samtycke', document_name: 'Stadgar Brf Gjutformen 12 MOCK.pdf', page: 12 }
          ]
        }];
      });
      setChatBusy(false);
    }, 1000);
  };

  const highlightText = (text, queryWords) => {
    if (!queryWords || queryWords.length === 0) return text;
    const sortedWords = [...queryWords].sort((a, b) => b.length - a.length);
    const pattern = new RegExp(`(${sortedWords.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
    const parts = text.split(pattern);
    return (
      <>
        {parts.map((part, i) => {
          const isMatch = sortedWords.some(w => w.toLowerCase() === part.toLowerCase());
          return isMatch ? <mark key={i} className="search-highlight">{part}</mark> : <span key={i}>{part}</span>;
        })}
      </>
    );
  };

  const filterCounts = {
    alla: MOCK_DOCUMENTS.length,
    granskas: MOCK_DOCUMENTS.filter(d => d.qa === 'Behöver granskas' || d.qa === 'Ej påbörjad').length,
    bevakningar: MOCK_DOCUMENTS.filter(d => d.bevakningar > 0).length,
    behandlas: MOCK_DOCUMENTS.filter(d => d.status === 'Behandlas').length,
    klara: MOCK_DOCUMENTS.filter(d => d.status === 'Klar' && d.qa === 'Klar').length
  };

  const filteredDocs = MOCK_DOCUMENTS.filter(doc => {
    if (docFilter === 'alla') return true;
    if (docFilter === 'granskas') return doc.qa === 'Behöver granskas' || doc.qa === 'Ej påbörjad';
    if (docFilter === 'bevakningar') return doc.bevakningar > 0;
    if (docFilter === 'behandlas') return doc.status === 'Behandlas';
    if (docFilter === 'klara') return doc.status === 'Klar' && doc.qa === 'Klar';
    return true;
  });

  return (
    <div className="app-shell">
      <div className="mock-banner-compact">
        <span className="mock-badge-inline">MOCKUP</span>
        All data, filnamn och svar är fiktiva och ej kopplade till en server.
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* SIDEBAR - Only visible when NO document is selected */}
        {!selectedDocument && (
          <nav className="sidebar">
            <div className="sidebar-brand">
              <div className="logo">Simons <span>RAG</span></div>
            </div>

            <div className="sidebar-menu">
              <button className={`nav-item ${currentTab === 'home' ? 'active' : ''}`} onClick={() => setCurrentTab('home')}>
                <LayoutDashboard size={20} /> Hem
              </button>
              <button className={`nav-item ${currentTab === 'docs' ? 'active' : ''}`} onClick={() => { setCurrentTab('docs'); setDocFilter('alla'); }}>
                <Folders size={20} /> Dokument
              </button>
              <button className={`nav-item ${currentTab === 'chat' ? 'active' : ''}`} onClick={() => setCurrentTab('chat')}>
                <MessageSquare size={20} /> AI-chatt
              </button>
              
              <div style={{ marginTop: '40px', padding: '0 16px', color: 'var(--text-muted)', fontSize: '12px', fontWeight: '600' }}>
                ADMINISTRATION
              </div>
              <button className={`nav-item ${currentTab === 'settings' ? 'active' : ''}`} onClick={() => setCurrentTab('settings')}>
                <Settings size={20} /> Inställningar
              </button>
            </div>
            
            <div style={{ marginTop: 'auto', padding: '16px', borderTop: '1px solid var(--panel-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="chat-avatar" style={{ background: 'rgba(92, 107, 156, 0.3)' }}>AA</div>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: '500' }}>Anna Andersson</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>anna@gjutformen12.se</div>
                </div>
              </div>
            </div>
          </nav>
        )}

        {/* WORKSPACE MODE - Visible when a document is selected */}
        {selectedDocument && (
          <div className="workspace-container">
            {/* Workspace Header */}
            <header className="workspace-header">
              <div className="workspace-header-left">
                <button className="icon-action-btn" onClick={closeDocument} title="Tillbaka till listan" aria-label="Tillbaka">
                  <ArrowLeft size={20} />
                </button>
                <div className="workspace-doc-info">
                  <h1 className="workspace-doc-title">{selectedDocument.name}</h1>
                  <div className="workspace-doc-meta">
                    {selectedDocument.status === 'Klar' ? (
                      <span className="status-text ok"><CheckCircle2 size={12}/> Bearbetad</span>
                    ) : (
                      <span className="status-text muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                    )}
                    <span>·</span>
                    <span className="status-text">{selectedDocument.pages} sidor</span>
                  </div>
                </div>
              </div>
              
              <div className="workspace-tabs">
                <button className={`workspace-tab ${workspaceTab === 'read' ? 'active' : ''}`} onClick={() => setWorkspaceTab('read')}>
                  <FileText size={16}/> Läs dokument
                </button>
                <button className={`workspace-tab ${workspaceTab === 'review' ? 'active' : ''}`} onClick={() => setWorkspaceTab('review')}>
                  <CheckCircle2 size={16}/> Kvalitetskontroll
                  {selectedDocument.qa === 'Behöver granskas' && <span className="tab-badge warning">!</span>}
                </button>
                <button className={`workspace-tab ${workspaceTab === 'chat' ? 'active' : ''}`} onClick={() => setWorkspaceTab('chat')}>
                  <MessageCircle size={16}/> Fråga dokumentet
                </button>
              </div>

              <div className="workspace-header-right">
                 {/* Placeholder for Next/Prev if coming from a queue */}
                 <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Dokument 1 av 1</span>
              </div>
            </header>

            <div className="workspace-content">
              
              {/* === TAB: LÄSA (READ) === */}
              {workspaceTab === 'read' && (
                <div className="workspace-split read-mode">
                  <div className="pdf-viewer-container">
                    <div className="pdf-toolbar">
                      <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1}><ArrowLeft size={16}/></button>
                         <span>Sida {pdfPage} av {selectedDocument.pages}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(selectedDocument.pages, pdfPage + 1))} disabled={pdfPage === selectedDocument.pages}><ArrowRight size={16}/></button>
                      </div>
                      <div className="pdf-actions">
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.max(50, z - 10))} title="Zooma ut"><ZoomOut size={16}/></button>
                         <span style={{ fontSize: '12px', width: '40px', textAlign: 'center' }}>{pdfZoom}%</span>
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.min(200, z + 10))} title="Zooma in"><ZoomIn size={16}/></button>
                         <div className="divider"></div>
                         <button className="icon-action-btn" title="Sök i dokument"><Search size={16}/></button>
                      </div>
                    </div>
                    
                    <div className="pdf-canvas">
                      <div className="mock-pdf-page" style={{ transform: `scale(${pdfZoom / 100})` }}>
                        {selectedDocument.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                          <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'serif', color: '#000', fontSize: '14px', lineHeight: 1.6 }}>
                            {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                          </div>
                        ) : (
                          <div className="mock-pdf-placeholder">
                            <FileText size={48} color="#ccc" style={{ marginBottom: '16px' }}/>
                            <div>Visar sida {pdfPage} av {selectedDocument.name}</div>
                            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>(Detta är en mockad PDF-visare)</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="workspace-sidepanel">
                    <div className="panel-section">
                      <h3>Dokumentinformation</h3>
                      <div className="info-grid">
                        <div className="info-item">
                          <span className="info-label">Laddades upp</span>
                          <span className="info-value">{selectedDocument.date}</span>
                        </div>
                        
                        <div className="info-item">
                          <span className="info-label">Bearbetning</span>
                          <span className="info-value">
                            {selectedDocument.status === 'Klar' ? <span className="status-text ok">Klar</span> : <span className="status-text muted">Behandlas</span>}
                          </span>
                        </div>
                        
                        <div className="info-item">
                          <span className="info-label">Kvalitetskontroll</span>
                          <span className="info-value">
                            {selectedDocument.qa === 'Klar' ? <span className="status-text ok">Klar</span> : <span className="status-text warning">Behöver granskas</span>}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="panel-section">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h3>Bevakningar i dokumentet</h3>
                        <span className="status-badge warning" style={{ background: 'transparent', border: '1px solid var(--status-warning)', color: 'var(--status-warning)' }}>{MOCK_BEVAKNINGAR.filter(b => b.docId === selectedDocument.id).length} st</span>
                      </div>
                      
                      <div className="bevakning-list">
                        {MOCK_BEVAKNINGAR.filter(b => b.docId === selectedDocument.id).length === 0 ? (
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Inga bevakningar funna.</div>
                        ) : (
                          MOCK_BEVAKNINGAR.filter(b => b.docId === selectedDocument.id).map(b => (
                            <div key={b.id} className={`bevakning-card ${b.done ? 'done' : ''}`}>
                              <div className="bevakning-header">
                                <div className="bevakning-date"><Calendar size={14}/> {b.date}</div>
                                {b.done ? <span className="status-badge ok" style={{ padding: '2px 6px', fontSize: '10px' }}>Klar</span> : null}
                              </div>
                              <div className="bevakning-title">{b.title}</div>
                              <div className="bevakning-desc">{b.desc}</div>
                              <div className="bevakning-actions">
                                <button className="small-action-btn" onClick={() => setPdfPage(b.page)}>Sida {b.page}</button>
                                {!b.done && <button className="small-action-btn ok"><Check size={14}/> Markera klar</button>}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* === TAB: KVALITETSKONTROLL (REVIEW) === */}
              {workspaceTab === 'review' && (
                <div className="workspace-split review-mode">
                  {/* Left: PDF */}
                  <div className="pdf-viewer-container half">
                    <div className="pdf-toolbar">
                       <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Original (PDF)</span>
                       <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1}><ArrowLeft size={16}/></button>
                         <span>Sid {pdfPage} / {selectedDocument.pages}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(selectedDocument.pages, pdfPage + 1))} disabled={pdfPage === selectedDocument.pages}><ArrowRight size={16}/></button>
                      </div>
                    </div>
                    <div className="pdf-canvas">
                      <div className="mock-pdf-page" style={{ transform: 'scale(0.8)', transformOrigin: 'top center' }}>
                        {selectedDocument.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                          <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'serif', color: '#000', fontSize: '14px', lineHeight: 1.6 }}>
                            {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                          </div>
                        ) : (
                          <div className="mock-pdf-placeholder">
                            <FileText size={48} color="#ccc" style={{ marginBottom: '16px' }}/>
                            <div>Visar sida {pdfPage}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right: Extraction */}
                  <div className="extraction-container half">
                    <div className="pdf-toolbar extraction-toolbar">
                      <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Extraherad text</span>
                    </div>
                    <div className="extraction-content">
                      {selectedDocument.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                        <div className="extracted-text-box">
                          {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                        </div>
                      ) : (
                        <div className="extracted-text-box empty">
                           Text extraheras eller mockdata saknas för denna fil/sida.
                        </div>
                      )}
                    </div>
                    
                    <div className="extraction-actions">
                       <button className="primary-action-btn ok">
                         <CheckCircle2 size={16}/> Godkänn sida
                       </button>
                       <div style={{ position: 'relative' }}>
                         <button className="primary-action-btn warning" onClick={() => setReportMenuOpen(!reportMenuOpen)}>
                           <ThumbsDown size={16}/> Rapportera problem
                         </button>
                         {reportMenuOpen && (
                           <div className="report-menu">
                             <button onClick={() => setReportMenuOpen(false)}>Saknad text</button>
                             <button onClick={() => setReportMenuOpen(false)}>Felaktigt tecken / Skräptecken</button>
                             <button onClick={() => setReportMenuOpen(false)}>Fel styckeordning</button>
                             <button onClick={() => setReportMenuOpen(false)}>Låg läsbarhet i PDF</button>
                           </div>
                         )}
                       </div>
                    </div>
                  </div>
                </div>
              )}

              {/* === TAB: FRÅGA DOKUMENTET (CHAT) === */}
              {workspaceTab === 'chat' && (
                <div className="workspace-split chat-mode">
                  <div className="pdf-viewer-container half">
                    <div className="pdf-toolbar">
                       <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Referensvy</span>
                    </div>
                    <div className="pdf-canvas">
                      <div className="mock-pdf-page" style={{ transform: 'scale(0.8)', transformOrigin: 'top center' }}>
                        {selectedDocument.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                          <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'serif', color: '#000', fontSize: '14px', lineHeight: 1.6 }}>
                            {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                          </div>
                        ) : (
                          <div className="mock-pdf-placeholder">
                            <FileText size={48} color="#ccc" style={{ marginBottom: '16px' }}/>
                            <div>Visar sida {pdfPage}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="workspace-chat-container half">
                    <div className="workspace-chat-header">
                       <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--ai-accent)' }}>
                         <Sparkles size={18} />
                         <span style={{ fontWeight: '500' }}>AI-chatt för detta dokument</span>
                       </div>
                       
                       <div className="demo-state-selector">
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>MOCK-STATE:</span>
                          <select value={demoState} onChange={e => setDemoState(e.target.value)} title="Ändra vilket svar AI:n tvingas ge i mockupen.">
                            <option value="standard">Svar med citat</option>
                            <option value="no-answer">Otillräckligt underlag</option>
                            <option value="conflict">Motstridiga källor</option>
                          </select>
                       </div>
                    </div>

                    <div className="chat-messages-area" style={{ flex: 1, padding: '20px' }}>
                      {workspaceChatMessages.length === 0 ? (
                        <div className="chat-empty-state">
                           <Info size={32} color="var(--text-muted)" style={{ marginBottom: '16px', opacity: 0.5 }} />
                           <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '24px' }}>
                             Ställ frågor specifikt om innehållet i <strong>{selectedDocument.name}</strong>.
                           </p>
                           <button className="example-prompt-btn" onClick={() => setWorkspaceChatInput('När startar jouren?')}>När startar jouren?</button>
                        </div>
                      ) : (
                        workspaceChatMessages.map((msg, idx) => (
                          <div key={idx} className={`chat-message ${msg.role}`}>
                            <div className="chat-avatar">
                              {msg.role === 'ai' ? (msg.pending ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />) : 'DU'}
                            </div>
                            <div style={{ flex: 1 }}>
                              <div className="chat-content" style={{ borderColor: msg.refusal ? 'var(--status-error-dim)' : (msg.warning ? 'var(--status-warning-dim)' : '') }}>
                                {msg.refusal && !msg.warning && <div className="chat-refusal-header"><AlertCircle size={14} /> Otillräckligt underlag</div>}
                                {msg.warning && <div className="chat-refusal-header warning"><AlertTriangle size={14} /> Motstridiga källor</div>}
                                {msg.content}
                                
                                {msg.citations && (
                                  <div className="chat-citations">
                                    {msg.citations.map((c, i) => (
                                      <div key={i} className="citation-pill interactive" onClick={() => setPdfPage(c.page)} title={`Gå till sida ${c.page}`}>
                                        <span className="citation-number">[{i + 1}]</span>
                                        <span className="citation-text">"{c.quote}"</span>
                                        <span className="citation-source">— s.{c.page}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                              
                              {msg.followUps && !msg.pending && (
                                <div className="chat-followups">
                                  {msg.followUps.map((fu, fidx) => (
                                    <button key={fidx} className="followup-btn" onClick={() => setWorkspaceChatInput(fu)}>
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

                    <div className="chat-input-area" style={{ padding: '20px', borderTop: '1px solid var(--panel-border)' }}>
                      <div className="chat-input-wrapper">
                        <input
                          type="text"
                          value={workspaceChatInput}
                          onChange={(e) => setWorkspaceChatInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && executeWorkspaceChat()}
                          placeholder={`Fråga om ${selectedDocument.name}...`}
                          disabled={workspaceChatBusy}
                        />
                        <button className="chat-send-btn" onClick={() => executeWorkspaceChat()} disabled={workspaceChatBusy || !workspaceChatInput.trim()}>
                          {workspaceChatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>
          </div>
        )}

        {/* MAIN APPLICATION (Visible when NO document is selected) */}
        {!selectedDocument && (
          <main className="main-content">
            {currentTab === 'home' && (
              <div className="tab-content" style={{ maxWidth: '900px' }}>
                <div className="hero-section" style={{ textAlign: 'center', margin: '20px 0 40px 0' }}>
                  <h1 style={{ fontSize: '32px', marginBottom: '16px', fontWeight: '600' }}>Sök i dina dokument</h1>
                  
                  <div className="search-input-large-wrapper" style={{ maxWidth: '640px', margin: '0 auto', padding: '8px 8px 8px 20px' }}>
                    <SearchIcon size={20} color="var(--text-secondary)" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && executeSearch(searchQuery)}
                      placeholder="Sök efter avtal, paragrafer eller ämnen..."
                      style={{ fontSize: '16px' }}
                    />
                    <button className="search-action-btn primary" onClick={() => executeSearch(searchQuery)}>
                      Sök
                    </button>
                  </div>
                  
                  <div style={{ marginTop: '16px', fontSize: '14px', color: 'var(--text-secondary)' }}>
                    Har du en mer komplex fråga? <button onClick={() => executeGeneralChat(searchQuery || 'Vad gäller för...')} className="link-button ai" style={{ fontWeight: '500', textDecoration: 'underline' }}>Ställ den i AI-chatten istället</button>
                  </div>
                </div>

                {/* Kräver uppmärksamhet */}
                <div style={{ marginBottom: '32px' }}>
                  <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-warning)' }}>
                    <AlertTriangle size={18} /> Kräver din uppmärksamhet
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div className="interactive-card" onClick={() => { setCurrentTab('docs'); setDocFilter('granskas'); }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div className="status-badge warning">{filterCounts.granskas} Dokument</div>
                        <ArrowUpRight size={16} color="var(--text-secondary)" />
                      </div>
                      <div style={{ marginTop: '12px', fontSize: '16px', fontWeight: '500' }}>Väntar på kvalitetskontroll</div>
                      <div style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-secondary)' }}>Maskinell extraktion är klar, men mänsklig verifiering saknas.</div>
                    </div>
                    <div className="interactive-card" onClick={() => { setCurrentTab('docs'); setDocFilter('bevakningar'); }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div className="status-badge warning">{filterCounts.bevakningar} Dokument</div>
                        <ArrowUpRight size={16} color="var(--text-secondary)" />
                      </div>
                      <div style={{ marginTop: '12px', fontSize: '16px', fontWeight: '500' }}>Innehåller aktiva bevakningar</div>
                      <div style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-secondary)' }}>Håll koll på datum och tidsfrister.</div>
                    </div>
                  </div>
                </div>

                {/* Översikt */}
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
                  <div className="glass-panel" style={{ padding: '24px' }}>
                    <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Folders size={18} /> Senaste Dokument
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {MOCK_DOCUMENTS.slice(0, 3).map(doc => (
                        <div key={doc.id} className="interactive-row" onClick={() => openDocument(doc.id)} tabIndex={0}>
                          <FileText size={16} color="var(--text-secondary)" />
                          <span style={{ fontSize: '14px', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.name}</span>
                          <span className={`status-text ${doc.qa === 'Klar' ? 'ok' : 'warning'}`}>{doc.qa}</span>
                        </div>
                      ))}
                    </div>
                    <button className="link-button" onClick={() => { setCurrentTab('docs'); setDocFilter('alla'); }} style={{ marginTop: '16px' }}>Visa alla dokument →</button>
                  </div>

                  <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'center', textAlign: 'center' }}>
                     <div style={{ fontSize: '32px', fontWeight: '600', color: 'var(--text-primary)' }}>74</div>
                     <div style={{ fontSize: '13px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Sökbara sidor</div>
                     <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--panel-border)' }}>
                       <div style={{ fontSize: '20px', fontWeight: '600', color: 'var(--text-primary)' }}>{filterCounts.alla}</div>
                       <div style={{ fontSize: '13px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Dokument</div>
                     </div>
                  </div>
                </div>
              </div>
            )}

            {currentTab === 'docs' && (
              <div className="tab-content" style={{ maxWidth: '1200px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <div>
                    <h2 style={{ fontSize: '24px', fontWeight: '600' }}>Dokument</h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Hantera uppladdningar, kvalitetskontroll och bevakningar.</p>
                  </div>
                  <button className="primary-action-btn">
                    <Upload size={16} /> Ladda upp dokument
                  </button>
                </div>

                <div className="docs-filter-bar">
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className={`filter-pill ${docFilter === 'alla' ? 'active' : ''}`} onClick={() => setDocFilter('alla')}>Alla ({filterCounts.alla})</button>
                    <button className={`filter-pill warning ${docFilter === 'granskas' ? 'active' : ''}`} onClick={() => setDocFilter('granskas')}>Behöver granskas ({filterCounts.granskas})</button>
                    <button className={`filter-pill warning ${docFilter === 'bevakningar' ? 'active' : ''}`} onClick={() => setDocFilter('bevakningar')}>Har bevakningar ({filterCounts.bevakningar})</button>
                    <button className={`filter-pill ${docFilter === 'behandlas' ? 'active' : ''}`} onClick={() => setDocFilter('behandlas')}>Behandlas ({filterCounts.behandlas})</button>
                    <button className={`filter-pill ok ${docFilter === 'klara' ? 'active' : ''}`} onClick={() => setDocFilter('klara')}>Klara ({filterCounts.klara})</button>
                  </div>
                  <div className="search-input-small">
                    <SearchIcon size={16} />
                    <input type="text" placeholder="Sök dokumentnamn..." />
                  </div>
                </div>

                <div className="glass-panel" style={{ overflow: 'hidden' }}>
                  <table className="docs-table">
                    <thead>
                      <tr>
                        <th>Dokument</th>
                        <th>Uppladdat</th>
                        <th>Status</th>
                        <th>Sidor</th>
                        <th>Kvalitetskontroll</th>
                        <th>Bevakningar</th>
                        <th>Åtgärd</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDocs.map(doc => (
                        <tr key={doc.id} className="interactive-table-row" onClick={() => openDocument(doc.id)} tabIndex={0}>
                          <td style={{ fontWeight: '500', display: 'flex', alignItems: 'center', gap: '8px' }}>
                             <FileText size={16} color="var(--text-secondary)" /> {doc.name}
                          </td>
                          <td style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                          <td>
                            {doc.status === 'Klar' ? (
                              <span className="status-badge ok"><CheckCircle2 size={12}/> Klar</span>
                            ) : (
                              <span className="status-badge processing"><Loader2 size={12} className="spin"/> Behandlas</span>
                            )}
                          </td>
                          <td>{doc.pages}</td>
                          <td>
                            {doc.qa === 'Klar' ? (
                              <span className="status-text ok"><CheckCircle2 size={14}/> {doc.qa}</span>
                            ) : doc.qa === 'Behöver granskas' ? (
                              <span className="status-text warning"><AlertTriangle size={14}/> {doc.qa}</span>
                            ) : (
                              <span className="status-text muted"><Clock size={14}/> {doc.qa}</span>
                            )}
                          </td>
                          <td>
                             {doc.bevakningar > 0 ? (
                               <span className="status-badge warning" style={{ background: 'transparent', border: '1px solid var(--status-warning)', color: 'var(--status-warning)' }}>{doc.bevakningar} st</span>
                             ) : <span style={{ color: 'var(--text-muted)' }}>-</span>}
                          </td>
                          <td>
                             <button className="icon-action-btn" aria-label="Öppna dokument"><ChevronRight size={18}/></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {currentTab === 'search' && (
              <div className="tab-content" style={{ maxWidth: '800px', margin: '0 auto' }}>
                <div className="search-top-bar" style={{ marginBottom: '24px' }}>
                  <div className="search-input-large-wrapper">
                    <SearchIcon size={20} color="var(--text-secondary)" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && executeSearch(searchQuery)}
                      placeholder="Sök i text..."
                    />
                    <button className="search-action-btn primary" onClick={() => executeSearch(searchQuery)}>
                      {searchIsLoading ? <Loader2 size={16} className="spin" /> : 'Sök'}
                    </button>
                  </div>
                  
                  {!searchIsLoading && searchResults && (
                    <div className="search-summary-text" style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Hittade {searchResults.totalPassages} träffar i {searchResults.totalDocuments} dokument.</span>
                      <button onClick={() => executeGeneralChat(searchQuery)} className="link-button ai">Fråga AI:n istället <Sparkles size={14}/></button>
                    </div>
                  )}
                </div>

                {searchIsLoading ? (
                  <div style={{ textAlign: 'center', marginTop: '60px', color: 'var(--text-secondary)' }}>
                    <Loader2 size={32} className="spin" style={{ margin: '0 auto', color: 'var(--primary-action)' }} />
                    <h3 style={{ marginTop: '16px' }}>Söker i textavsnitt...</h3>
                  </div>
                ) : searchResults && (
                  <div className="search-results-list">
                    {searchResults.results.map((res) => (
                      <div key={res.id} className="search-snippet-card">
                        <div className="snippet-excerpt">
                          {highlightText(res.excerpt, res.highlights)}
                        </div>
                        <div className="snippet-meta">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                             <FileText size={14} /> 
                             <span style={{ fontWeight: '500', color: 'var(--text-primary)' }}>{res.documentName}</span>
                             <span>· Sid {res.page}</span>
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                             <button className="small-action-btn" onClick={() => openDocument(res.documentId, res.page, 'read')}>Öppna källa</button>
                             <button className="small-action-btn ai" onClick={() => {
                               openDocument(res.documentId, res.page, 'chat');
                               setWorkspaceChatInput(`Angående sökningen "${searchQuery}": vad står det mer om detta i dokumentet?`);
                             }}>Fråga AI i dokument <Sparkles size={12}/></button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {currentTab === 'chat' && (
              <div className="tab-content">
                <div className="chat-container">
                  <div className="chat-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Sparkles color="var(--ai-accent)" size={24}/> Global AI-assistent (MOCK)</h2>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>Få svar baserade på alla föreningens indexerade dokument.</p>
                    </div>
                    
                    <div className="chat-scope-selector">
                       <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Söker i:</span>
                       <button className="scope-btn" title="Klicka för att välja vilka dokument som ska sökas">
                         {chatScope} <ChevronRight size={14}/>
                       </button>
                    </div>
                  </div>

                  <div className="chat-messages-area">
                    {chatMessages.length === 0 ? (
                      <div className="chat-empty-state">
                         <Sparkles size={40} color="var(--ai-accent)" style={{ marginBottom: '16px', opacity: 0.5 }} />
                         <h3 style={{ marginBottom: '24px' }}>Vad vill du ha hjälp med?</h3>
                         <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%', maxWidth: '400px' }}>
                           <button className="example-prompt-btn" onClick={() => executeGeneralChat('Vad säger stadgarna om andrahandsuthyrning?')}>
                             Vad säger stadgarna om andrahandsuthyrning?
                           </button>
                           <button className="example-prompt-btn" onClick={() => executeGeneralChat('Vilka datum gäller för snöröjningsjouren?')}>
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
                          <div style={{ flex: 1 }}>
                            <div className="chat-content" style={{ borderColor: msg.refusal ? 'var(--status-error-dim)' : '' }}>
                              {msg.refusal && <div className="chat-refusal-header"><AlertCircle size={14} /> Otillräckligt underlag</div>}
                              {msg.content}
                              
                              {msg.citations && (
                                <div className="chat-citations">
                                  {msg.citations.map((c, i) => (
                                    <div key={i} className="citation-pill interactive" onClick={() => openDocument('d2', c.page, 'read')} title="Öppna källdokumentet">
                                      <span className="citation-number">[{i + 1}]</span>
                                      <span className="citation-text">"{c.quote}"</span>
                                      <span className="citation-source">— {c.document_name} s.{c.page}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                            
                            {msg.followUps && !msg.pending && (
                              <div className="chat-followups">
                                {msg.followUps.map((fu, fidx) => (
                                  <button key={fidx} className="followup-btn" onClick={() => executeGeneralChat(fu)}>
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
                        onKeyDown={(e) => e.key === 'Enter' && executeGeneralChat(chatInput)}
                        placeholder="Ställ en generell fråga till AI:n..."
                        disabled={chatBusy}
                      />
                      <button className="chat-send-btn" onClick={() => executeGeneralChat(chatInput)} disabled={chatBusy || !chatInput.trim()}>
                        {chatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </main>
        )}

      </div>
    </div>
  );
}

export default App;
