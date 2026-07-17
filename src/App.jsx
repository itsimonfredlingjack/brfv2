import React, { useState, useRef, useEffect, Suspense } from 'react';
import {
  Search as SearchIcon, X, UploadCloud, FileText,
  Loader2, CheckCircle2,
  ArrowRight, AlertCircle, LayoutDashboard, Folders, CheckSquare, Clock,
  Trash2, Edit3, ChevronUp, Settings, HelpCircle, LogOut,
  Filter, ArrowDownUp, List, LayoutGrid, MessageSquare, Send
} from 'lucide-react';
import SettingsView from './components/SettingsView';
import PdfViewer from './components/PdfViewer';
import Login from './components/Login';
import ChatMessageList from './components/ChatMessageList';
import CitationsPanel from './components/CitationsPanel';
import HeroSearch from './components/HeroSearch';
import { api } from './api';
import { runAskQuestion } from './askQuestion';
import { latestCitations } from './chatResponseMapping';
import { demoTabsEnabled } from './appModes';
import './App.css';

// Dev-gated demo scaffolding (cleanup/verified-ui Task 5): Granskning,
// Bevakningar, and the Document Canvas they open render fabricated,
// pipeline-shaped demo data (src/demoData.js) and must never reach a
// production build. The `import.meta.env.DEV` check here is a literal, not
// routed through demoTabsEnabled() — that's deliberate: it's what lets
// Vite/esbuild fold this whole assignment (including the import() call) to
// `null` and drop DemoWorkspace's module graph out of production builds
// entirely, not just skip rendering it. demoTabsEnabled() is still the
// single source of truth for every render-time gating decision below.
// Verified via `npm run build` + grepping `dist/` for demo markers — see
// docs/evidence/verified-ui-restore.md.
const DemoWorkspace = import.meta.env.DEV
  ? React.lazy(() => import('./components/DemoWorkspace'))
  : null;

function App() {
  const [currentTab, setCurrentTab] = useState('overview'); // overview, documents, review, deadlines, search
  const [activeDocument, setActiveDocument] = useState(null); // null or doc ID e.g. 'snorojning'
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  // Real backend state
  const [documents, setDocuments] = useState([]);
  const [uploadError, setUploadError] = useState(null);
  const [viewer, setViewer] = useState(null); // {url, title, page, rects, highlightPage}
  const [chatBusy, setChatBusy] = useState(false);
  const fileInputRef = useRef(null);

  const [settingsSaveState, setSettingsSaveState] = useState(null); // null | 'saving' | 'saved' | 'error'
  const settingsSaveTimerRef = useRef(null);

  // ---- Auth & tenant state ----
  const [authState, setAuthState] = useState('loading'); // 'loading' | 'loggedOut' | 'loggedIn'
  const [user, setUser] = useState(null);
  const [memberships, setMemberships] = useState([]);
  const [activeBrfId, setActiveBrfId] = useState(null);

  const activeMembership = memberships.find((m) => m.brf_id === activeBrfId) || null;
  const activeRole = activeMembership?.role || 'member';
  const isAdmin = activeRole === 'admin';
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
    setViewer(null);
    setDocuments([]);
    setChatMessages([]);
    setActiveDocument(null);
    setCurrentTab('overview');
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
    setViewer(null);
    setActiveDocument(null);
    setDocuments([]);
    setCurrentTab('overview');
  };

  const refreshDocuments = async () => {
    if (!activeBrfId) return;
    try {
      setDocuments(await api.listDocuments(activeBrfId));
    } catch (e) {
      handleApiError(e);
      setDocuments([]);
    }
  };

  // Session bootstrap: restore an existing session cookie, else show login.
  useEffect(() => {
    api.me()
      .then(handleLoggedIn)
      .catch(() => setAuthState('loggedOut'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tenant (re)load: documents + settings follow the active BRF.
  useEffect(() => {
    if (authState !== 'loggedIn' || !activeBrfId) return;
    refreshDocuments();
    // Hydrate settings from the backend (backend keys win; UI-only keys keep defaults)
    api.getSettings(activeBrfId)
      .then((s) => setSettingsConfig((prev) => ({ ...prev, ...s })))
      .catch((e) => handleApiError(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState, activeBrfId]);

  // Fresh tenant context ⇒ fresh chat greeting (also clears cross-tenant history).
  useEffect(() => {
    if (authState !== 'loggedIn' || !user || !activeBrfId) return;
    const firstName = (user.name || '').split(' ')[0] || user.email;
    setChatMessages([{
      role: 'ai',
      content: `Hej ${firstName}! Jag är kopplad till alla dokument i ${activeBrfName} (styrelseprotokoll, stadgar, årsredovisningar m.m.). Vad vill du ha hjälp med att hitta eller analysera idag?`,
    }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState, user, activeBrfId]);

  const BACKEND_SETTINGS_KEYS = [
    'chunkStrategy', 'chunkSize', 'chunkOverlap',
    'searchWeighting', 'candidateCount', 'topK', 'minRelevance',
    'aiModel', 'systemPrompt', 'maxResponseLength', 'requireSources', 'insufficientDataBehavior',
  ];

  const saveSettings = async () => {
    // A stale timer from a previous save must not wipe this save's state.
    clearTimeout(settingsSaveTimerRef.current);
    setSettingsSaveState('saving');
    try {
      const payload = Object.fromEntries(
        BACKEND_SETTINGS_KEYS.map((k) => [k, settingsConfig[k]]).filter(([, v]) => v !== undefined)
      );
      const saved = await api.putSettings(activeBrfId, payload);
      setSettingsConfig((prev) => ({ ...prev, ...saved }));
      await refreshDocuments(); // chunk-knob changes re-chunk documents
      setSettingsSaveState('saved');
      clearTimeout(settingsSaveTimerRef.current);
      settingsSaveTimerRef.current = setTimeout(() => setSettingsSaveState(null), 2500);
    } catch (e) {
      if (handleApiError(e)) return;
      console.error('Kunde inte spara inställningar', e);
      setSettingsSaveState('error');
    }
  };

  const openDocViewer = (doc, opts = {}) =>
    setViewer({
      url: api.pdfUrl(activeBrfId, doc.document_id || doc.id),
      title: doc.document_name || doc.name,
      page: opts.page || 1,
      rects: opts.rects || [],
      highlightPage: opts.highlightPage ?? null,
    });
  // Settings State
  const [activeSettingsTab, setActiveSettingsTab] = useState('dokument');
  const [settingsConfig, setSettingsConfig] = useState({
    // Dokument
    allowedFormats: 'pdf',
    maxFileSize: 50,
    ocrMode: 'auto',
    languageDetection: true,
    duplicateCheck: true,
    // Chunking
    chunkStrategy: 'recursive',
    chunkSize: 1000,
    chunkOverlap: 200,
    headerHandling: true,
    tableHandling: 'markdown',
    // Sökning
    searchWeighting: 50,
    candidateCount: 100,
    topK: 10,
    minRelevance: 0.7,
    // AI-svar
    aiModel: 'claude-opus-4-8',
    systemPrompt: 'Du är en hjälpsam AI-assistent...',
    temperature: 0.3,
    maxResponseLength: 1000,
    requireSources: true,
    insufficientDataBehavior: 'refuse',
    // Källmarkering
    requirePageNumbers: true,
    requireBoundingBoxes: false,
    allowPassageWithoutCoords: true,
    fallbackToPageLevel: true
  });

  // Chat State (the greeting is seeded per user + active BRF by the effect above)
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);

  const askQuestion = (question) => runAskQuestion(question, {
    activeBrfId,
    chatBusy,
    setCurrentTab,
    setActiveDocument,
    setChatMessages,
    setChatBusy,
    handleApiError,
  });

  const handleChatSubmit = () => {
    const q = chatInput.trim();
    // Guard BEFORE clearing the input — otherwise a submit while a previous
    // question is in flight silently discards what the user typed.
    if (!q || chatBusy) return;
    setChatInput('');
    askQuestion(q);
  };

  // Demo-tab state (Granskning/Bevakningar/Document Canvas — qaDocuments,
  // timelineData, cardData, activeId/searchQuery/etc.) now lives entirely
  // inside src/components/DemoWorkspace.jsx (cleanup/verified-ui Task 5):
  // that state exists only to drive fabricated demo data and has no reason
  // to be evaluated in a production render at all, so it moved with the
  // data rather than staying here behind a rendering gate.

  const handleGlobalUpload = () => {
    if (!isAdmin) return; // members are read-only — the backend 403s anyway
    setUploadError(null);
    setShowUploadModal(true);
  };

  const handleDeleteDocument = async (doc) => {
    if (!isAdmin) return;
    const name = doc.document_name || doc.name;
    if (!window.confirm(`Ta bort "${name}"? Dokumentet försvinner ur sökindexet.`)) return;
    try {
      await api.deleteDocument(activeBrfId, doc.document_id || doc.id);
      await refreshDocuments();
    } catch (e) {
      if (!handleApiError(e)) alert(`Kunde inte ta bort dokumentet: ${e.message}`);
    }
  };

  const handleFileChosen = async (file) => {
    if (!file) return;
    setUploadError(null);
    setShowUploadModal(false);
    setIsProcessing(true);
    setProcessingStep(0);
    const t1 = setTimeout(() => setProcessingStep(1), 600);
    const t2 = setTimeout(() => setProcessingStep(2), 1500);
    try {
      await api.uploadDocument(activeBrfId, file);
      setProcessingStep(3);
      await refreshDocuments();
      setTimeout(() => {
        setIsProcessing(false);
        setCurrentTab('documents');
      }, 500);
    } catch (e) {
      setIsProcessing(false);
      if (!handleApiError(e)) {
        setUploadError(e.message);
        setShowUploadModal(true);
      }
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
    }
  };

  // navigateToDoc/closeDocument/clearActive/handleDeadlineToggle/handleSearch/
  // activateParagraph (Document Canvas navigation) moved into
  // src/components/DemoWorkspace.jsx with the rest of the demo-tab state —
  // they only ever drove the fabricated Document Canvas.

  // --- Renderers for Tabs --- //

  const renderProcessingOverlay = () => {
    if (!isProcessing) return null;
    return (
      <div className="processing-overlay glass-panel">
        <FileText size={40} className="pulse-icon" color="var(--accent-search)" />
        <h2 className="processing-title">Bearbetar dokument...</h2>
        <div className="processing-steps">
          <div className={`step ${processingStep >= 0 ? 'active' : ''}`}>
            {processingStep > 0 ? <CheckCircle2 size={16} color="var(--accent-date)" /> : <Loader2 size={16} className="spin" />}
            <span>Laddar upp PDF-fil...</span>
          </div>
          <div className={`step ${processingStep >= 1 ? 'active' : ''} ${processingStep < 1 ? 'pending' : ''}`}>
            {processingStep > 1 ? <CheckCircle2 size={16} color="var(--accent-date)" /> : (processingStep === 1 ? <Loader2 size={16} className="spin" /> : <div className="dot"></div>)}
            <span>Extraherar text sida för sida...</span>
          </div>
          <div className={`step ${processingStep >= 2 ? 'active' : ''} ${processingStep < 2 ? 'pending' : ''}`}>
            {processingStep > 2 ? <CheckCircle2 size={16} color="var(--accent-date)" /> : (processingStep === 2 ? <Loader2 size={16} className="spin" /> : <div className="dot"></div>)}
            <span>Identifierar tidsfrister och datum...</span>
          </div>
          <div className={`step ${processingStep >= 3 ? 'active' : ''} ${processingStep < 3 ? 'pending' : ''}`}>
            {processingStep > 3 ? <CheckCircle2 size={16} color="var(--accent-date)" /> : (processingStep === 3 ? <Loader2 size={16} className="spin" /> : <div className="dot"></div>)}
            <span>Bygger rums-indexering...</span>
          </div>
        </div>
      </div>
    );
  };

  const renderUploadModal = () => {
    if (!showUploadModal) return null;
    return (
      <div className="upload-modal-overlay" onClick={() => setShowUploadModal(false)}>
        <div className="upload-modal-content glass-panel" onClick={(e) => e.stopPropagation()}>
          <button className="icon-btn close-modal-btn" onClick={() => setShowUploadModal(false)}>
            <X size={20} />
          </button>
          <input
            type="file"
            accept="application/pdf,.pdf"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              // Reset now (the input unmounts with the modal before any async
              // finally runs) so re-picking the same file fires onChange again.
              e.target.value = '';
              handleFileChosen(file);
            }}
          />
          <div
            className="upload-box"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              handleFileChosen(e.dataTransfer.files?.[0]);
            }}
          >
            <div className="upload-icon-wrapper">
              <UploadCloud size={64} strokeWidth={1} color="var(--text-secondary)" />
            </div>
            <h2 className="upload-title" style={{fontSize: '28px', marginBottom: '10px'}}>Ladda upp PDF</h2>
            <p className="upload-subtitle" style={{fontSize: '16px', color: 'var(--text-secondary)'}}>Dra och släpp ditt avtal eller dokument här. Texten extraheras ord för ord med positioner och blir sökbar med källhänvisningar.</p>

            {uploadError && (
              <div className="upload-error">
                <AlertCircle size={16} /> {uploadError}
              </div>
            )}

            <div className="upload-features">
              <span><CheckCircle2 size={16} /> Extraherar text + positioner</span>
              <span><CheckCircle2 size={16} /> Chunkar & indexerar</span>
              <span><CheckCircle2 size={16} /> Gör sökbart med källor</span>
            </div>

            <button className="primary-btn" style={{marginTop: '40px'}}>Välj fil lokalt</button>
          </div>
        </div>
      </div>
    );
  };

  const renderOverview = () => (
    <div className="tab-content">
      {/* Hero Search Section — the Home/App-shell search affordance; routes
          to the real ask flow (see src/components/HeroSearch.jsx) */}
      <HeroSearch
        chatInput={chatInput}
        setChatInput={setChatInput}
        chatBusy={chatBusy}
        onSubmit={handleChatSubmit}
        onSuggestionClick={askQuestion}
      />
      <div className="overview-grid">
        <div className="overview-stats">
          <div className="stat-card glass-panel">
            <span className="stat-value">{documents.length}</span>
            <span className="stat-label">Dokument</span>
          </div>
          <div className="stat-card glass-panel">
            <span className="stat-value">{documents.reduce((a, d) => a + (d.pages || 0), 0)}</span>
            <span className="stat-label">Sidor indexerade</span>
          </div>
          <div className="stat-card glass-panel">
            <span className="stat-value">{documents.reduce((a, d) => a + (d.chunks || 0), 0)}</span>
            <span className="stat-label">Chunks i sökindex</span>
          </div>
        </div>

        <div className="overview-main-sections" style={{ display: 'flex', gap: '30px', marginTop: '40px' }}>

          <div className="documents-section" style={{ flex: 1 }}>
            <h3 className="section-title">Dokument i arbetsytan</h3>
            <div className="documents-grid">
              {documents.slice(0, 4).map((doc) => (
                <div key={doc.id} className="document-card glass-panel" onClick={() => openDocViewer(doc)}>
                  <div className="doc-icon"><FileText size={24} color="var(--accent-search)" /></div>
                  <div className="doc-info">
                    <h4>{doc.name}</h4>
                    <span>{doc.pages} sidor • {doc.chunks} chunks</span>
                  </div>
                </div>
              ))}
              {documents.length === 0 && (
                <div className="document-card glass-panel" onClick={handleGlobalUpload} style={{ cursor: isAdmin ? 'pointer' : 'default' }}>
                  <div className="doc-icon dimmed"><UploadCloud size={24} color="var(--text-secondary)" /></div>
                  <div className="doc-info">
                    <h4>{isAdmin ? 'Ladda upp din första PDF' : 'Inga dokument ännu'}</h4>
                    <span>{isAdmin ? 'Texten indexeras och blir frågebar' : 'En administratör kan ladda upp föreningens dokument'}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );

  const renderDocuments = () => (
    <div className="tab-content">
      <h2 className="tab-title">Alla Dokument</h2>

      {/* Toolbar */}
      <div className="documents-toolbar">
        <div className="toolbar-left">
          <div className="search-input-wrapper">
            <SearchIcon size={14} />
            <input type="text" placeholder="Sök dokumentnamn..." className="toolbar-search-input" />
          </div>
          <button className="toolbar-btn">
            <Filter size={14} /> Filter
          </button>
          <button className="toolbar-btn">
            <ArrowDownUp size={14} /> Sortera
          </button>
        </div>
        <div className="toolbar-right">
          <div className="view-toggle">
            <button className="view-toggle-btn active"><List size={16} /></button>
            <button className="view-toggle-btn"><LayoutGrid size={16} /></button>
          </div>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
        <table className="documents-table">
          <thead>
            <tr>
              <th>Dokument</th>
              <th>Uppladdat</th>
              <th>Status</th>
              <th>Sidor</th>
              <th>Chunks</th>
              <th style={{textAlign: 'right'}}>Åtgärd</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '40px' }}>
                  Inga dokument ännu — ladda upp en PDF för att komma igång.
                </td>
              </tr>
            )}
            {documents.map(doc => (
              <tr key={doc.id} onClick={() => openDocViewer(doc)} style={{ cursor: 'pointer' }}>
                <td style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <FileText size={18} color="var(--accent-search)" />
                  <span style={{ fontWeight: 500 }}>{doc.name}</span>
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>{(doc.uploaded_at || '').slice(0, 10)}</td>
                <td>
                  <span className="status-badge ready">Klar</span>
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>{doc.pages}</td>
                <td style={{ color: 'var(--text-secondary)' }}>{doc.chunks}</td>
                <td style={{textAlign: 'right'}}>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '4px' }}>
                    {isAdmin && (
                      <button
                        className="icon-btn"
                        title="Ta bort dokument"
                        onClick={(e) => { e.stopPropagation(); handleDeleteDocument(doc); }}
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                    <button className="icon-btn" onClick={(e) => { e.stopPropagation(); openDocViewer(doc); }}>
                      <ArrowRight size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  // Granskning, Bevakningar, and the Document Canvas render exclusively via
  // DemoWorkspace (see the DemoWorkspace const above + demoTabsEnabled()
  // gating below) — dev-gated demo scaffolding, cleanup/verified-ui Task 5.
  const renderDemoWorkspace = () => {
    if (!demoTabsEnabled(import.meta.env.DEV) || !DemoWorkspace) return null;
    return (
      <Suspense fallback={null}>
        <DemoWorkspace
          currentTab={currentTab}
          activeDocument={activeDocument}
          setActiveDocument={setActiveDocument}
        />
      </Suspense>
    );
  };

  // ---- Auth gate: nothing below renders without a session ----
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
      {/* Persistent Sidebar */}
      <nav className="sidebar glass-panel">
        <div className="sidebar-brand">
          <div className="logo">Simons <span>RAG-system</span></div>
        </div>

        {isAdmin && (
          <div className="sidebar-upload">
            <button className="upload-btn" onClick={handleGlobalUpload}>
              <UploadCloud size={18} />
              Ladda upp dokument
            </button>
          </div>
        )}

        <div className="sidebar-menu">
          <button className={`nav-item ${currentTab === 'overview' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('overview'); setActiveDocument(null);}}>
            <LayoutDashboard size={20} /> Hem & Sök
          </button>
          <button className={`nav-item ${currentTab === 'documents' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('documents'); setActiveDocument(null);}}>
            <Folders size={20} /> Dokument
          </button>
          {demoTabsEnabled(import.meta.env.DEV) && (
            <button className={`nav-item ${currentTab === 'review' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('review'); setActiveDocument(null);}}>
              <CheckSquare size={20} /> Granskning
            </button>
          )}
          {demoTabsEnabled(import.meta.env.DEV) && (
            <button className={`nav-item ${currentTab === 'deadlines' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('deadlines'); setActiveDocument(null);}}>
              <Clock size={20} /> Bevakningar
            </button>
          )}
        </div>
        <div className="sidebar-ai-action">
          <button className={`nav-item ai-chat-btn ${currentTab === 'chat' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('chat'); setActiveDocument(null);}}>
            <MessageSquare size={20} /> AI-chatt
          </button>
        </div>
        <div className="sidebar-settings" style={{ marginTop: 'auto', marginBottom: '16px', padding: '0 16px' }}>
          <button className={`nav-item ${currentTab === 'settings' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('settings'); setActiveDocument(null);}}>
            <Settings size={20} /> Systeminställningar
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

      {/* Main Content Area */}
      <main className="main-content-scroll">
        {renderUploadModal()}
        {viewer && <PdfViewer {...viewer} onClose={() => setViewer(null)} />}
        {isProcessing && renderProcessingOverlay()}

        {!isProcessing && activeDocument && renderDemoWorkspace()}

        {!isProcessing && !activeDocument && (
          <div className="tab-container">
            {currentTab === 'overview' && renderOverview()}
            {currentTab === 'documents' && renderDocuments()}
            {currentTab === 'review' && renderDemoWorkspace()}
            {currentTab === 'deadlines' && renderDemoWorkspace()}
            {currentTab === 'settings' && (
              <SettingsView
                settingsConfig={settingsConfig}
                setSettingsConfig={setSettingsConfig}
                activeSettingsTab={activeSettingsTab}
                setActiveSettingsTab={setActiveSettingsTab}
                onSave={saveSettings}
                saveState={settingsSaveState}
                readOnly={!isAdmin}
              />
            )}
            {currentTab === 'chat' && (
              <div className="chat-layout">
                <div className="chat-container">
                  <div className="chat-header">
                    <h2 className="tab-title" style={{ marginBottom: '8px' }}>Chatta med dokument</h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '15px', marginBottom: '30px' }}>Ställ frågor i klartext och få svar direkt från din dokumentdatabas.</p>
                  </div>

                  <ChatMessageList messages={chatMessages} userInitials={userInitials} openDocViewer={openDocViewer} />

                  <div className="chat-input-area">
                    <div className="chat-input-box">
                      <input
                        type="text"
                        placeholder="T.ex. 'Vilka regler gäller för andrahandsuthyrning?'..."
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleChatSubmit()}
                        disabled={chatBusy}
                      />
                      <button className="chat-send-btn" onClick={handleChatSubmit} disabled={chatBusy}>
                        {chatBusy ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
                      </button>
                    </div>
                  </div>
                </div>

                <CitationsPanel citations={latestCitations(chatMessages)} openDocViewer={openDocViewer} />
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
