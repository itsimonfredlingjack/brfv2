import React, { useState } from 'react';
import { LayoutDashboard, MessageSquare, Folders, Settings, Search as SearchIcon, FileText, ArrowRight, Loader2, Sparkles, AlertCircle, Calendar, Upload, CheckCircle2, Clock, AlertTriangle, ArrowUpRight, X, ChevronRight, CornerDownRight, ArrowLeft, ZoomIn, ZoomOut, Search, Check, ThumbsDown, MessageCircle, Info, Menu } from 'lucide-react';
import './App.css';

// --- MOCK DATA ---
const MOCK_DOCUMENTS = [
  { id: 'd1', name: 'Snöröjningsavtal 2026 MOCK.pdf', date: '2026-07-16', pages: 2, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 1 },
  { id: 'd2', name: 'Stadgar Brf Gjutformen 12 MOCK.pdf', date: '2026-07-15', pages: 18, status: 'Färdigbehandlad', qa: 'Behöver granskas', bevakningar: 0 },
  { id: 'd3', name: 'Styrelseprotokoll 2026-03-12 MOCK.pdf', date: '2026-03-14', pages: 4, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 2 },
  { id: 'd4', name: 'Årsredovisning 2025 MOCK.pdf', date: '2026-02-10', pages: 32, status: 'Behandlas', qa: 'Behöver granskas', bevakningar: 0 },
  { id: 'd5', name: 'Underhållsplan 2026-2036 MOCK.pdf', date: '2026-01-05', pages: 14, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 3 },
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

// --- CUSTOM HOOKS ---
function useMediaQuery(query) {
  const [matches, setMatches] = React.useState(() => {
    if (typeof window !== 'undefined') {
      return window.matchMedia(query).matches;
    }
    return false;
  });

  React.useEffect(() => {
    const mediaQuery = window.matchMedia(query);
    const handler = (e) => setMatches(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

function App() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const [documents, setDocuments] = useState(MOCK_DOCUMENTS);
  const [bevakningar, setBevakningar] = useState(MOCK_BEVAKNINGAR);

  const [currentTab, setCurrentTab] = useState('docs');
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const mobileMenuBtnRef = React.useRef(null);
  const sidebarRef = React.useRef(null);

  React.useEffect(() => {
    if (!isMobile && isMobileMenuOpen) {
      setIsMobileMenuOpen(false);
    }
  }, [isMobile, isMobileMenuOpen]);

  React.useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isMobile || !isMobileMenuOpen) return;
      if (e.key === 'Escape') {
        setIsMobileMenuOpen(false);
        mobileMenuBtnRef.current?.focus();
        return;
      }
      if (e.key === 'Tab') {
        const focusableElements = sidebarRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusableElements && focusableElements.length > 0) {
          const firstElement = focusableElements[0];
          const lastElement = focusableElements[focusableElements.length - 1];

          if (e.shiftKey) {
            if (document.activeElement === firstElement) {
              lastElement.focus();
              e.preventDefault();
            }
          } else {
            if (document.activeElement === lastElement) {
              firstElement.focus();
              e.preventDefault();
            }
          }
        }
      }
    };
    if (isMobile && isMobileMenuOpen) {
      document.addEventListener('keydown', handleKeyDown);
      setTimeout(() => {
        const firstFocusable = sidebarRef.current?.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (firstFocusable) firstFocusable.focus();
      }, 50);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isMobile, isMobileMenuOpen]);

  const [toastMessage, setToastMessage] = useState(null);
  const showToast = (message, type = 'info') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchIsLoading, setSearchIsLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);

  // Doc State
  const [docFilter, setDocFilter] = useState('alla');
  const [docsSearchQuery, setDocsSearchQuery] = useState('');

  // Workspace State
  const [workspaceTab, setWorkspaceTab] = useState('read'); // 'read', 'review', 'chat'
  const [mobileQaSegment, setMobileQaSegment] = useState('pdf'); // 'pdf' or 'text'
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

  const executeSearch = (query) => {
    if (!query.trim()) return;
    setSearchQuery(query);
    setCurrentTab('search');
    setSelectedDocument(null);
    setSearchIsLoading(true);
    setIsMobileMenuOpen(false);

    setTimeout(() => {
      setSearchResults(MOCK_SEARCH_RESULTS);
      setSearchIsLoading(false);
    }, 800);
  };

  const openDocument = (docId, initialPage = 1, initialTab = 'read') => {
    const doc = documents.find(d => d.id === docId);
    if (doc) {
      setSelectedDocument(doc);
      setPdfPage(initialPage);
      setWorkspaceTab(initialTab);
      setPdfZoom(100);
      setWorkspaceChatMessages([]);
      setIsMobileMenuOpen(false);
    }
  };

  const closeDocument = () => {
    setSelectedDocument(null);
  };

  const handleApproveQa = () => {
    setDocuments(prev => prev.map(d => d.id === selectedDocument.id ? { ...d, qa: 'Granskad' } : d));
    setSelectedDocument(prev => ({ ...prev, qa: 'Granskad' }));
    showToast('Dokumentet har godkänts och sparats.', 'success');
  };

  const handleMarkBevakningDone = (bevakningId) => {
    setBevakningar(prev => prev.map(b => b.id === bevakningId ? { ...b, done: true } : b));
    showToast('Bevakningen markerades som klar.', 'success');
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
    setIsMobileMenuOpen(false);

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

  // Base counts derived directly from MOCK_DOCUMENTS, independent of text search
  const filterCounts = {
    alla: documents.length,
    granskas: documents.filter(d => d.qa === 'Behöver granskas').length,
    bevakningar: documents.filter(d => d.bevakningar > 0).length,
    behandlas: documents.filter(d => d.status === 'Behandlas').length,
    klara: documents.filter(d => d.status === 'Färdigbehandlad' && d.qa === 'Granskad').length
  };

  const filteredDocs = documents.filter(doc => {
    const searchMatch = docsSearchQuery === '' || doc.name.toLowerCase().includes(docsSearchQuery.toLowerCase());

    let filterMatch = true;
    if (docFilter === 'granskas') filterMatch = doc.qa === 'Behöver granskas';
    else if (docFilter === 'bevakningar') filterMatch = doc.bevakningar > 0;
    else if (docFilter === 'behandlas') filterMatch = doc.status === 'Behandlas';
    else if (docFilter === 'klara') filterMatch = (doc.status === 'Färdigbehandlad' && doc.qa === 'Granskad');

    return searchMatch && filterMatch;
  });

  const getBevakningLabel = (count) => {
    if (count === 0) return "Inga bevakningar";
    if (count === 1) return "1 bevakning";
    return `${count} bevakningar`;
  };

  return (
    <div className="app-shell">
      {toastMessage && (
        <div role="status" aria-live="polite" style={{ position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)', background: toastMessage.type === 'success' ? 'var(--status-ok)' : 'var(--panel-bg)', color: toastMessage.type === 'success' ? '#000' : '#fff', padding: '12px 24px', borderRadius: '8px', zIndex: 1000, display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.5)', border: toastMessage.type !== 'success' ? '1px solid var(--panel-border)' : 'none' }}>
          {toastMessage.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span style={{ fontWeight: '500', fontSize: '14px' }}>{toastMessage.message}</span>
        </div>
      )}
      <div className="mock-banner-compact">
        <span className="mock-badge-inline">MOCKUP</span>
        All data, filnamn och svar är fiktiva och ej kopplade till en server.
      </div>

      {/* MOBILE TOP NAVIGATION */}
      {!selectedDocument && (
        <header className="mobile-top-nav">
          <div className="logo">Simons <span>RAG</span></div>
          <button ref={mobileMenuBtnRef} className="icon-action-btn mobile-menu-btn" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} aria-label="Meny" aria-expanded={isMobileMenuOpen}>
            {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </header>
      )}

      <div className="main-layout">

        {/* SIDEBAR - Responsive */}
        {!selectedDocument && (
          <nav
            ref={sidebarRef}
            className={`sidebar ${isMobileMenuOpen ? 'open' : ''}`}
            aria-hidden={!isMobileMenuOpen && isMobile ? "true" : "false"}
            inert={!isMobileMenuOpen && isMobile ? true : undefined}
          >
            <div className="sidebar-brand desktop-only">
              <div className="logo">Simons <span>RAG</span></div>
            </div>

            <div className="sidebar-menu">
              <button className={`nav-item ${currentTab === 'home' ? 'active' : ''}`} onClick={() => { setCurrentTab('home'); setIsMobileMenuOpen(false); }}>
                <LayoutDashboard size={20} /> Hem
              </button>
              <button className={`nav-item ${currentTab === 'docs' ? 'active' : ''}`} onClick={() => { setCurrentTab('docs'); setDocFilter('alla'); setDocsSearchQuery(''); setIsMobileMenuOpen(false); }}>
                <Folders size={20} /> Dokument
              </button>
              <button className={`nav-item ${currentTab === 'chat' ? 'active' : ''}`} onClick={() => { setCurrentTab('chat'); setIsMobileMenuOpen(false); }}>
                <MessageSquare size={20} /> AI-chatt
              </button>

              <div style={{ marginTop: '40px', padding: '0 16px', color: 'var(--text-muted)', fontSize: '12px', fontWeight: '600' }}>
                ADMINISTRATION
              </div>
              <button className={`nav-item ${currentTab === 'settings' ? 'active' : ''}`} onClick={() => { setCurrentTab('settings'); setIsMobileMenuOpen(false); }}>
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
            <header className="workspace-header">
              <div className="workspace-header-left">
                <button className="icon-action-btn" onClick={closeDocument} title="Tillbaka till listan" aria-label="Tillbaka">
                  <ArrowLeft size={20} />
                </button>
                <div className="workspace-doc-info">
                  <h1 className="workspace-doc-title">{selectedDocument.name}</h1>
                  <div className="workspace-doc-meta">
                    {selectedDocument.status === 'Färdigbehandlad' ? (
                      <span className="status-text ok"><CheckCircle2 size={12}/> Färdigbehandlad</span>
                    ) : (
                      <span className="status-text muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                    )}
                    <span className="meta-divider">·</span>
                    <span className="status-text">{selectedDocument.pages} sidor</span>
                  </div>
                </div>
              </div>

              <div className="workspace-tabs">
                <button className={`workspace-tab ${workspaceTab === 'read' ? 'active' : ''}`} onClick={() => setWorkspaceTab('read')}>
                  <FileText size={16}/> <span className="tab-label">Läs dokument</span>
                </button>
                <button className={`workspace-tab ${workspaceTab === 'review' ? 'active' : ''}`} onClick={() => setWorkspaceTab('review')}>
                  <CheckCircle2 size={16}/> <span className="tab-label">Kvalitetskontroll</span>
                  {selectedDocument.qa === 'Behöver granskas' && <span className="tab-badge warning" aria-label="Kräver granskning">!</span>}
                </button>
                <button className={`workspace-tab ${workspaceTab === 'chat' ? 'active' : ''}`} onClick={() => setWorkspaceTab('chat')}>
                  <MessageCircle size={16}/> <span className="tab-label">Fråga dokumentet</span>
                </button>
              </div>

              <div className="workspace-header-right desktop-only">
                 <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Dokument 1 av 1</span>
              </div>
            </header>

            <div className="workspace-content">
              {workspaceTab === 'read' && (
                <div className="workspace-split read-mode">
                  <div className="pdf-viewer-container">
                    <div className="pdf-toolbar">
                      <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                         <span>Sida {pdfPage} av {selectedDocument.pages}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(selectedDocument.pages, pdfPage + 1))} disabled={pdfPage === selectedDocument.pages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
                      </div>
                      <div className="pdf-actions">
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.max(50, z - 10))} title="Zooma ut" aria-label="Zooma ut"><ZoomOut size={16}/></button>
                         <span style={{ fontSize: '12px', width: '40px', textAlign: 'center' }}>{pdfZoom}%</span>
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.min(200, z + 10))} title="Zooma in" aria-label="Zooma in"><ZoomIn size={16}/></button>
                         <div className="divider"></div>
                         <button className="icon-action-btn" title="Sök i dokument" aria-label="Sök"><Search size={16}/></button>
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
                          <span className="info-label">Systembearbetning</span>
                          <span className="info-value">
                            {selectedDocument.status === 'Färdigbehandlad' ? <span className="status-text ok">Färdigbehandlad</span> : <span className="status-text muted">Behandlas</span>}
                          </span>
                        </div>
                        <div className="info-item">
                          <span className="info-label">Kvalitetskontroll</span>
                          <span className="info-value">
                            {selectedDocument.qa === 'Granskad' ? <span className="status-text ok">Granskad</span> : <span className="status-text warning">Behöver granskas</span>}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="panel-section">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h3>Bevakningar i dokumentet</h3>
                        {bevakningar.filter(b => b.docId === selectedDocument.id).length > 0 && (
                          <span className="status-badge warning" style={{ background: 'transparent', border: '1px solid var(--status-warning)', color: 'var(--status-warning)' }}>
                            {bevakningar.filter(b => b.docId === selectedDocument.id).length}
                          </span>
                        )}
                      </div>

                      <div className="bevakning-list">
                        {bevakningar.filter(b => b.docId === selectedDocument.id).length === 0 ? (
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Inga bevakningar funna.</div>
                        ) : (
                          bevakningar.filter(b => b.docId === selectedDocument.id).map(b => (
                            <div key={b.id} className={`bevakning-card ${b.done ? 'done' : ''}`}>
                              <div className="bevakning-header">
                                <div className="bevakning-date"><Calendar size={14}/> {b.date}</div>
                                {b.done && <span className="status-badge ok" style={{ padding: '2px 6px', fontSize: '10px' }}>Klar</span>}
                              </div>
                              <div className="bevakning-title">{b.title}</div>
                              <div className="bevakning-desc">{b.desc}</div>
                              <div className="bevakning-actions">
                                <button className="small-action-btn" onClick={() => setPdfPage(b.page)}>Sida {b.page}</button>
                                {!b.done && <button className="small-action-btn ok" onClick={() => handleMarkBevakningDone(b.id)}><Check size={14}/> Markera klar</button>}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {workspaceTab === 'review' && (
                <div className="workspace-split review-mode">
                  <div className="mobile-qa-segmented-control mobile-only">
                     <button className={mobileQaSegment === 'pdf' ? 'active' : ''} onClick={() => setMobileQaSegment('pdf')}>Original (PDF)</button>
                     <button className={mobileQaSegment === 'text' ? 'active' : ''} onClick={() => setMobileQaSegment('text')}>Extraherad text</button>
                  </div>
                  <div className={`pdf-viewer-container half ${mobileQaSegment !== 'pdf' ? 'mobile-hidden' : ''}`}>
                    <div className="pdf-toolbar">
                       <span className="desktop-only" style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Original (PDF)</span>
                       <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                         <span>Sid {pdfPage} / {selectedDocument.pages}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(selectedDocument.pages, pdfPage + 1))} disabled={pdfPage === selectedDocument.pages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
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

                  <div className={`extraction-container half ${mobileQaSegment !== 'text' ? 'mobile-hidden' : ''}`}>
                    <div className="pdf-toolbar extraction-toolbar">
                      <span className="desktop-only" style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Extraherad text</span>
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
                       <button className="primary-action-btn ok" onClick={handleApproveQa}>
                         <CheckCircle2 size={16}/> <span className="action-label">Godkänn dokument</span>
                       </button>
                       <div style={{ position: 'relative' }}>
                         <button className="primary-action-btn warning" onClick={() => setReportMenuOpen(!reportMenuOpen)} aria-haspopup="true" aria-expanded={reportMenuOpen}>
                           <ThumbsDown size={16}/> <span className="action-label">Rapportera problem</span>
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

              {workspaceTab === 'chat' && (
                <div className="workspace-split chat-mode">
                  <div className="pdf-viewer-container half desktop-only">
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
                                      <div key={i} className="citation-pill interactive" onClick={() => setPdfPage(c.page)} title={`Gå till sida ${c.page}`} tabIndex={0} role="button" onKeyDown={e => e.key === 'Enter' && setPdfPage(c.page)}>
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
                        <button className="chat-send-btn" onClick={() => executeWorkspaceChat()} disabled={workspaceChatBusy || !workspaceChatInput.trim()} aria-label="Skicka fråga">
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
            {/* Omitted Home/Search/Chat logic from earlier mockup to keep code cleaner, but I should keep them intact if the user wants to navigate back */}
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

                <div style={{ marginBottom: '32px' }}>
                  <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-warning)' }}>
                    <AlertTriangle size={18} /> Kräver din uppmärksamhet
                  </h3>
                  <div className="dashboard-grid">
                    <button className="interactive-card" onClick={() => { setCurrentTab('docs'); setDocFilter('granskas'); setDocsSearchQuery(''); }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div className="status-badge warning">{filterCounts.granskas} Dokument</div>
                        <ArrowUpRight size={16} color="var(--text-secondary)" />
                      </div>
                      <div style={{ marginTop: '12px', fontSize: '16px', fontWeight: '500', textAlign: 'left' }}>Väntar på kvalitetskontroll</div>
                      <div style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'left' }}>Maskinell extraktion är klar, men mänsklig verifiering saknas.</div>
                    </button>
                    <button className="interactive-card" onClick={() => { setCurrentTab('docs'); setDocFilter('bevakningar'); setDocsSearchQuery(''); }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div className="status-badge warning">{filterCounts.bevakningar} Dokument</div>
                        <ArrowUpRight size={16} color="var(--text-secondary)" />
                      </div>
                      <div style={{ marginTop: '12px', fontSize: '16px', fontWeight: '500', textAlign: 'left' }}>Innehåller aktiva bevakningar</div>
                      <div style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'left' }}>Håll koll på datum och tidsfrister.</div>
                    </button>
                  </div>
                </div>

                <div className="dashboard-grid split">
                  <div className="glass-panel" style={{ padding: '24px' }}>
                    <h3 style={{ fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Folders size={18} /> Senaste Dokument
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {documents.slice(0, 3).map(doc => (
                        <button key={doc.id} className="interactive-row text-left" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                          <FileText size={16} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: '14px', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.name}</span>
                          <span className={`status-text ${doc.qa === 'Granskad' ? 'ok' : 'warning'}`}>{doc.qa}</span>
                        </button>
                      ))}
                    </div>
                    <button className="link-button" onClick={() => { setCurrentTab('docs'); setDocFilter('alla'); setDocsSearchQuery(''); }} style={{ marginTop: '16px' }}>Visa alla dokument →</button>
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
              <div className="tab-content docs-overview" style={{ maxWidth: '1200px' }}>
                <header className="page-header">
                  <div className="page-header-text">
                    <h2 style={{ fontSize: '24px', fontWeight: '600', margin: 0 }}>Dokument</h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: '4px 0 0 0' }}>Hantera systembearbetning, kvalitetskontroll och aktiva bevakningar.</p>
                  </div>
                  <button className="primary-action-btn desktop-only" onClick={() => showToast('Funktionen Ladda upp är inte tillgänglig i denna mockup.')} title="Mockup: Ladda upp är avstängt">
                    <Upload size={16} /> Ladda upp dokument
                  </button>
                </header>

                <div className="docs-control-bar">
                  <div className="search-input-small responsive-search">
                    <SearchIcon size={16} />
                    <input
                      type="text"
                      placeholder="Sök dokumentnamn..."
                      value={docsSearchQuery}
                      onChange={(e) => setDocsSearchQuery(e.target.value)}
                      aria-label="Sök dokument"
                    />
                    {docsSearchQuery && (
                      <button className="icon-action-btn clear-search" onClick={() => setDocsSearchQuery('')} aria-label="Rensa sökning">
                        <X size={14} />
                      </button>
                    )}
                  </div>

                  <div className="filter-pill-container">
                    <button className={`filter-pill ${docFilter === 'alla' ? 'active' : ''}`} onClick={() => setDocFilter('alla')}>Alla ({filterCounts.alla})</button>
                    <button className={`filter-pill warning ${docFilter === 'granskas' ? 'active' : ''}`} onClick={() => setDocFilter('granskas')}>Behöver granskas ({filterCounts.granskas})</button>
                    <button className={`filter-pill warning ${docFilter === 'bevakningar' ? 'active' : ''}`} onClick={() => setDocFilter('bevakningar')}>Har bevakningar ({filterCounts.bevakningar})</button>
                    <button className={`filter-pill ${docFilter === 'behandlas' ? 'active' : ''}`} onClick={() => setDocFilter('behandlas')}>Behandlas ({filterCounts.behandlas})</button>
                    <button className={`filter-pill ok ${docFilter === 'klara' ? 'active' : ''}`} onClick={() => setDocFilter('klara')}>Granskade ({filterCounts.klara})</button>
                  </div>
                </div>

                <div className="docs-collection-container">
                  {filteredDocs.length === 0 ? (
                    <div className="docs-empty-state">
                      <FileText size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
                      <h3>Inga dokument matchar din sökning</h3>
                      <p>Prova att ändra sökordet eller ditt filter.</p>
                      {(docsSearchQuery || docFilter !== 'alla') && (
                        <button className="secondary-action-btn" onClick={() => { setDocsSearchQuery(''); setDocFilter('alla'); }}>
                          Rensa sökning och filter
                        </button>
                      )}
                    </div>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <table className="docs-table desktop-only">
                        <thead>
                          <tr>
                            <th scope="col">Dokumentnamn</th>
                            <th scope="col">Uppladdat</th>
                            <th scope="col">Status</th>
                            <th scope="col">Granskning</th>
                            <th scope="col">Bevakningar</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredDocs.map(doc => (
                            <tr
                              key={doc.id}
                              className="interactive-table-row"
                            >
                              <td className="doc-name-cell">
                                <button className="doc-open-btn" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                                  <FileText size={16} color="var(--text-secondary)" className="doc-icon" />
                                  <span className="truncate">{doc.name}</span>
                                </button>
                              </td>
                              <td className="meta-cell">{doc.date}</td>
                              <td>
                                {doc.status === 'Färdigbehandlad' ? (
                                  <span className="status-badge ok"><CheckCircle2 size={12}/> Färdigbehandlad</span>
                                ) : (
                                  <span className="status-badge processing"><Loader2 size={12} className="spin"/> Behandlas</span>
                                )}
                              </td>
                              <td>
                                {doc.qa === 'Granskad' ? (
                                  <span className="status-text ok"><CheckCircle2 size={14}/> {doc.qa}</span>
                                ) : doc.qa === 'Behöver granskas' ? (
                                  <span className="status-text warning"><AlertTriangle size={14}/> {doc.qa}</span>
                                ) : (
                                  <span className="status-text muted"><Clock size={14}/> {doc.qa}</span>
                                )}
                              </td>
                              <td>
                                 {doc.bevakningar > 0 ? (
                                   <span className="status-badge warning outline">{getBevakningLabel(doc.bevakningar)}</span>
                                 ) : <span className="text-muted">{getBevakningLabel(0)}</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      {/* Mobile List View */}
                      <div className="docs-mobile-list mobile-only">
                        {filteredDocs.map(doc => (
                          <button
                            key={doc.id}
                            className="doc-mobile-card"
                            onClick={() => openDocument(doc.id)}
                            aria-label={`Öppna ${doc.name}`}
                          >
                            <div className="doc-card-header">
                              <FileText size={16} color="var(--text-secondary)" />
                              <h4 className="truncate">{doc.name}</h4>
                            </div>
                            <div className="doc-card-meta">
                               <span>{doc.date}</span>
                               <span>·</span>
                               {doc.status === 'Färdigbehandlad' ? (
                                  <span className="status-text ok">Färdig</span>
                                ) : (
                                  <span className="status-text muted">Laddar</span>
                                )}
                            </div>
                            <div className="doc-card-statuses">
                               {doc.qa === 'Granskad' ? (
                                  <span className="status-badge ok"><CheckCircle2 size={10}/> Granskad</span>
                                ) : (
                                  <span className="status-badge warning"><AlertTriangle size={10}/> Granska</span>
                                )}
                                {doc.bevakningar > 0 && (
                                  <span className="status-badge warning outline">{getBevakningLabel(doc.bevakningar)}</span>
                                )}
                            </div>
                            <ChevronRight size={16} className="chevron-icon" />
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Omitted the rest of search/chat for brevity, identical logic */}
            {currentTab === 'search' && (
               // Kept simple for now as it wasn't the main focus, but keeping it functional
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
                    <div className="search-summary-text" style={{ display: 'flex', justifyContent: 'space-between', marginTop: '16px' }}>
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
                      <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: '4px 0 0 0' }}>Få svar baserade på alla föreningens indexerade dokument.</p>
                    </div>

                    <div className="chat-scope-selector desktop-only">
                       <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Söker i:</span>
                       <button className="scope-btn" title="Klicka för att välja vilka dokument som ska sökas">
                         Alla dokument · {documents.length} dokument <ChevronRight size={14}/>
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
                                    <div key={i} className="citation-pill interactive" onClick={() => openDocument('d2', c.page, 'read')} title="Öppna källdokumentet" tabIndex={0} role="button" onKeyDown={e => e.key === 'Enter' && openDocument('d2', c.page, 'read')}>
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
                      <button className="chat-send-btn" onClick={() => executeGeneralChat(chatInput)} disabled={chatBusy || !chatInput.trim()} aria-label="Skicka fråga">
                        {chatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {currentTab === 'settings' && (
              <div className="settings-placeholder" style={{ padding: '24px', background: 'var(--panel-bg)', borderRadius: '12px', border: '1px solid var(--panel-border)', marginTop: '24px' }}>
                <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>Inställningar</h2>
                <p style={{ color: 'var(--text-secondary)' }}>Inställningsvyn är inte implementerad i denna mockup.</p>
              </div>
            )}
          </main>
        )}
      </div>
    </div>
  );
}

export default App;
