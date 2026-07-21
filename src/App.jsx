import React, { useState } from 'react';
import { LayoutDashboard, MessageSquare, Folders, Settings, Search as SearchIcon, FileText, ArrowRight, Loader2, Sparkles, AlertCircle, Calendar, Upload, CheckCircle2, AlertTriangle, X, ChevronRight, CornerDownRight, ArrowLeft, ZoomIn, ZoomOut, Search, Check, ThumbsDown, MessageCircle, Info, Menu, ChevronUp, HelpCircle, LogOut } from 'lucide-react';
import Login from './components/Login';
import { api } from './api';
import './App.css';

// --- MOCK DATA ---
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
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState(null);
  const [bevakningar, setBevakningar] = useState(MOCK_BEVAKNINGAR);

  // ---- Auth & active-BRF state (real backend; the document list below is
  // now real too — everything past it (upload, PDF view, extraction, AI
  // answers) is still MOCK_BEVAKNINGAR/MOCK_TEXT_EXTRACTION until the later
  // integration steps land) ----
  const [authState, setAuthState] = useState('loading'); // 'loading' | 'loggedOut' | 'loggedIn'
  const [user, setUser] = useState(null);
  const [memberships, setMemberships] = useState([]);
  const [activeBrfId, setActiveBrfId] = useState(null);
  const [showUserMenu, setShowUserMenu] = useState(false);

  const activeMembership = memberships.find((m) => m.brf_id === activeBrfId) || null;
  const activeBrfName = activeMembership?.name || '';
  const userInitials = (user?.name || '')
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase())
    .slice(0, 2)
    .join('') || '?';

  const handleLoggedIn = (result) => {
    setUser(result.user);
    setMemberships(result.memberships || []);
    setActiveBrfId(result.memberships?.[0]?.brf_id ?? null);
    setAuthState('loggedIn');
  };

  const resetToLogin = () => {
    setUser(null);
    setMemberships([]);
    setActiveBrfId(null);
    setAuthState('loggedOut');
    setShowUserMenu(false);
  };

  // Central 401 handling: an expired session drops straight back to login.
  const handleApiError = (e) => {
    if (e?.status === 401) {
      resetToLogin();
      return true;
    }
    return false;
  };

  const handleLogout = async () => {
    try { await api.logout(); } catch { /* clear locally regardless */ }
    resetToLogin();
  };

  const switchTenant = (value) => {
    // <option> values are strings — resolve back to the membership to keep the original id type.
    const m = memberships.find((mm) => String(mm.brf_id) === String(value));
    if (!m || m.brf_id === activeBrfId) return;
    setActiveBrfId(m.brf_id);
  };

  // Session bootstrap: restore an existing session cookie, else show login.
  React.useEffect(() => {
    api.me()
      .then(handleLoggedIn)
      .catch(() => setAuthState('loggedOut'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [currentTab, setCurrentTab] = useState('docs');
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Fetch the tenant-scoped document list whenever the active BRF changes.
  // Clears immediately so a slow request never leaves the previous BRF's
  // documents on screen after switching tenants.
  React.useEffect(() => {
    setDocuments([]);
    setSelectedDocument(null);
    setDocumentsError(null);
    if (!activeBrfId) return;

    let cancelled = false;
    setDocumentsLoading(true);
    api.listDocuments(activeBrfId)
      .then((docs) => {
        if (cancelled) return;
        setDocuments(docs.map((d) => ({
          id: d.id,
          name: d.name,
          date: d.uploaded_at.slice(0, 10),
          pages: d.pages,
          status: 'Färdigbehandlad', // upload is synchronous server-side — every listed doc is done
        })));
      })
      .catch((e) => {
        if (cancelled) return;
        if (!handleApiError(e)) setDocumentsError(e.message);
      })
      .finally(() => {
        if (!cancelled) setDocumentsLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBrfId]);

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
    setTimeout(() => setToastMessage(null), 4500);
  };

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchIsLoading, setSearchIsLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);

  // Doc State
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
  const reportMenuRef = React.useRef(null);

  React.useEffect(() => {
    if (!reportMenuOpen) return;
    const handleClickOutside = (e) => {
      if (reportMenuRef.current && !reportMenuRef.current.contains(e.target)) {
        setReportMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [reportMenuOpen]);

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
    if (!window.confirm('Är du säker på att du vill godkänna detta dokument?')) return;
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

  const filteredDocs = documents.filter(doc =>
    docsSearchQuery === '' || doc.name.toLowerCase().includes(docsSearchQuery.toLowerCase())
  );

  if (authState === 'loading') {
    return (
      <div className="auth-loading-screen">
        <Loader2 size={28} className="spin" />
        <span>Laddar…</span>
      </div>
    );
  }

  if (authState !== 'loggedIn') {
    return <Login onLoggedIn={handleLoggedIn} />;
  }

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
        Inloggning, förening och dokumentlistan är kopplade till den riktiga backenden. Uppladdning, dokumentvy och AI-svar nedan är fortfarande fiktiva.
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

        {isMobile && isMobileMenuOpen && (
          <div className="sidebar-backdrop" onClick={() => setIsMobileMenuOpen(false)} aria-hidden="true" />
        )}

        {/* SIDEBAR - Responsive */}
        {!selectedDocument && (
          <nav
            ref={sidebarRef}
            className={`sidebar ${isMobileMenuOpen ? 'open' : ''}`}
            aria-hidden={isMobile && !isMobileMenuOpen ? "true" : undefined}
            inert={isMobile && !isMobileMenuOpen ? true : undefined}
          >
            <div className="sidebar-brand desktop-only">
              <div className="logo">Simons <span>RAG</span></div>
            </div>

            <div className="sidebar-menu">
              <button className={`nav-item ${currentTab === 'home' ? 'active' : ''}`} onClick={() => { setCurrentTab('home'); setIsMobileMenuOpen(false); }}>
                <LayoutDashboard size={20} /> Hem
              </button>
              <button className={`nav-item ${currentTab === 'docs' ? 'active' : ''}`} onClick={() => { setCurrentTab('docs'); setDocsSearchQuery(''); setIsMobileMenuOpen(false); }}>
                <Folders size={20} /> Dokument
              </button>
              <button className={`nav-item ${currentTab === 'chat' ? 'active' : ''}`} onClick={() => { setCurrentTab('chat'); setIsMobileMenuOpen(false); }}>
                <MessageSquare size={20} /> AI-chatt
              </button>

              <div className="sidebar-section-label">
                ADMINISTRATION
              </div>
              <button className={`nav-item ${currentTab === 'settings' ? 'active' : ''}`} onClick={() => { setCurrentTab('settings'); setIsMobileMenuOpen(false); }}>
                <Settings size={20} /> Inställningar
              </button>
            </div>

            <div className="sidebar-footer">
              {memberships.length > 1 ? (
                <div className="tenant-switcher">
                  <label htmlFor="tenant-select">Förening</label>
                  <select
                    id="tenant-select"
                    value={String(activeBrfId ?? '')}
                    onChange={(e) => switchTenant(e.target.value)}
                  >
                    {memberships.map((m) => (
                      <option key={m.brf_id} value={String(m.brf_id)}>{m.name}</option>
                    ))}
                  </select>
                </div>
              ) : (
                activeBrfName && <div className="tenant-label" title={activeBrfName}>{activeBrfName}</div>
              )}

              {showUserMenu && (
                <div className="user-menu-popover glass-panel">
                  <div className="user-menu-item"><HelpCircle size={16} /> Hjälp & Support</div>
                  <div className="user-menu-divider"></div>
                  <div className="user-menu-item text-danger" onClick={handleLogout}><LogOut size={16} /> Logga ut</div>
                </div>
              )}

              <div className="user-profile" onClick={() => setShowUserMenu(!showUserMenu)}>
                <div className="user-avatar">{userInitials}</div>
                <div className="user-info">
                  <span className="user-name">{user?.name || user?.email}</span>
                  <span className="user-email">{user?.email}</span>
                </div>
                <ChevronUp size={16} color="var(--text-secondary)" style={{ marginLeft: 'auto', transform: showUserMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
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
                          <span className="status-badge warning outline">
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
                       <div ref={reportMenuRef} style={{ position: 'relative' }}>
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

                       <div className="demo-state-fence">
                         <span className="demo-state-fence-label">Dev</span>
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
                          <button className="example-prompt-btn" onClick={() => setWorkspaceChatInput(
                            selectedDocument.id === 'd1' ? 'När startar jouren?' :
                            selectedDocument.id === 'd2' ? 'Vad gäller för andrahandsuthyrning?' :
                            'Sammanfatta dokumentet'
                          )}>
                            {selectedDocument.id === 'd1' ? 'När startar jouren?' :
                             selectedDocument.id === 'd2' ? 'Vad gäller för andrahandsuthyrning?' :
                             'Sammanfatta dokumentet'}
                          </button>
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
                <div className="hero-section">
                  <h1 className="hero-title">Sök i dina dokument</h1>

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

                  <div className="hero-subtitle">
                    Har du en mer komplex fråga? <button onClick={() => { if (searchQuery.trim()) executeGeneralChat(searchQuery); else { setCurrentTab('chat'); setIsMobileMenuOpen(false); } }} className="link-button ai" style={{ fontWeight: '500', textDecoration: 'underline' }}>Ställ den i AI-chatten istället</button>
                  </div>
                </div>

                <div className="dashboard-grid split">
                  <div className="glass-panel" style={{ padding: '24px' }}>
                    <h3 className="recent-docs-heading">
                      <Folders size={18} /> Senaste Dokument
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {documents.length === 0 ? (
                        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
                          {documentsLoading ? 'Hämtar dokument…' : 'Inga dokument ännu.'}
                        </p>
                      ) : documents.slice(0, 3).map(doc => (
                        <button key={doc.id} className="interactive-row text-left" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                          <FileText size={16} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: '14px', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.name}</span>
                          <span className="status-text">{doc.pages} sidor</span>
                        </button>
                      ))}
                    </div>
                    <button className="link-button" onClick={() => { setCurrentTab('docs'); setDocsSearchQuery(''); }} style={{ marginTop: '16px' }}>Visa alla dokument →</button>
                  </div>

                  <div className="glass-panel stat-card">
                     <div className="stat-number">{documents.reduce((sum, d) => sum + d.pages, 0)}</div>
                     <div className="stat-label">Sökbara sidor</div>
                     <div className="stat-divider">
                       <div className="stat-number">{documents.length}</div>
                       <div className="stat-label">Dokument</div>
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
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: '4px 0 0 0' }}>{activeBrfName ? `Dokument för ${activeBrfName}.` : 'Hantera dokument.'}</p>
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
                </div>

                <div className="docs-collection-container">
                  {documentsLoading ? (
                    <div className="docs-empty-state">
                      <Loader2 size={32} className="spin" style={{ marginBottom: '16px' }} />
                      <h3>Hämtar dokument…</h3>
                    </div>
                  ) : documentsError ? (
                    <div className="docs-empty-state">
                      <AlertCircle size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
                      <h3>Kunde inte hämta dokument</h3>
                      <p>{documentsError}</p>
                    </div>
                  ) : documents.length === 0 ? (
                    <div className="docs-empty-state">
                      <FileText size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
                      <h3>Inga dokument ännu</h3>
                      <p>Det finns inga dokument för {activeBrfName || 'den här föreningen'} än.</p>
                    </div>
                  ) : filteredDocs.length === 0 ? (
                    <div className="docs-empty-state">
                      <FileText size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
                      <h3>Inga dokument matchar din sökning</h3>
                      <p>Prova att ändra sökordet.</p>
                      <button className="secondary-action-btn" onClick={() => setDocsSearchQuery('')}>
                        Rensa sökning
                      </button>
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
                          </tr>
                        </thead>
                        <tbody>
                          {filteredDocs.map(doc => (
                            <tr
                              key={doc.id}
                              className="interactive-table-row"
                              onClick={() => openDocument(doc.id)}
                              role="row"
                            >
                              <td className="doc-name-cell">
                                <button className="doc-open-btn" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                                  <FileText size={16} color="var(--text-secondary)" className="doc-icon" />
                                  <span className="truncate">{doc.name}</span>
                                </button>
                              </td>
                              <td className="meta-cell">{doc.date}</td>
                              <td>
                                <span className="status-badge ok"><CheckCircle2 size={12}/> Färdigbehandlad</span>
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
                               <span className="status-text ok">Färdig</span>
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
                      <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Sparkles color="var(--ai-accent)" size={24}/> Global AI-assistent</h2>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: '4px 0 0 0' }}>Få svar baserade på alla föreningens indexerade dokument.</p>
                    </div>

                    <div className="chat-scope-selector desktop-only">
                       <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Söker i:</span>
                       <button className="scope-btn" onClick={() => showToast('Dokumentfiltrering är inte tillgängligt i denna mockup.')} title="Klicka för att välja vilka dokument som ska sökas">
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
