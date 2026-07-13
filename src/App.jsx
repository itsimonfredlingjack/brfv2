import React, { useState, useRef } from 'react';
import {
  Search as SearchIcon, BellRing, X, UploadCloud, FileText,
  Loader2, CheckCircle2, ChevronLeft, Calendar as CalendarIcon,
  ArrowRight, AlertCircle, LayoutDashboard, Folders, CheckSquare, Clock,
  Trash2, Edit3, ChevronUp, Settings, HelpCircle, LogOut,
  Filter, ArrowDownUp, List, LayoutGrid, MessageSquare, Send, Sparkles
} from 'lucide-react';
import ContextCard from './components/ContextCard';
import DocumentView from './components/DocumentView';
import './App.css';

function App() {
  const [currentTab, setCurrentTab] = useState('overview'); // overview, documents, review, deadlines, search
  const [activeDocument, setActiveDocument] = useState(null); // null or doc ID e.g. 'snorojning'
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  // Chat State
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', content: 'Hej Simon! Jag är kopplad till alla dina dokument (Styrelseprotokoll, stadgar, årsredovisningar etc.). Vad vill du ha hjälp med att hitta eller analysera idag?' }
  ]);

  const handleChatSubmit = () => {
    if (!chatInput.trim()) return;
    setChatMessages([...chatMessages, { role: 'user', content: chatInput }]);
    setChatInput('');
    // Simulate AI response
    setTimeout(() => {
      setChatMessages(prev => [...prev, { role: 'ai', content: 'Jag letar i dina dokument och återkommer strax med ett refererat svar...' }]);
    }, 1000);
  };

  // Document Canvas State
  const [activeId, setActiveId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showDeadlines, setShowDeadlines] = useState(false);
  const [cardTop, setCardTop] = useState(0);
  const [activeData, setActiveData] = useState(null);
  const [activeType, setActiveType] = useState(null);

  const paragraphRefs = useRef({});

  // Mock data
  const cardData = {
    p3: { title: 'Jourperiod startar', description: 'Systemet har automatiskt skapat en bevakning för startdatum av snöröjningsjouren.', sourceDoc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
    p5: { title: 'Regler för halkbekämpning', description: 'Halkbekämpning (saltning) ska utföras i förebyggande syfte eller senast 1 timme efter snöröjning.', sourceDoc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 }
  };

  const timelineData = [
    { id: 't1', date: '15 Nov 2024', title: 'Start snöröjningsjour', description: 'Snöröjningsjour startar årligen den 15 november.', doc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
    { id: 't2', date: '31 Dec 2024', title: 'Budgetrapportering', description: 'Årlig budgetuppföljning och rapportering till styrelsen.', doc: 'ANSTÄLLNINGSAVTAL_VD.pdf', page: 6 },
    { id: 't3', date: '15 Apr 2025', title: 'Slut snöröjningsjour', description: 'Perioden för dygnet runt-jour avslutas.', doc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
  ];

  const documentsData = [
    { id: 'd1', name: 'SNÖRÖJNINGSAVTAL_2024.pdf', date: '2024-10-01', status: 'ready', deadlines: 2 },
    { id: 'd2', name: 'ANSTÄLLNINGSAVTAL_VD.pdf', date: '2024-09-15', status: 'ready', deadlines: 1 },
    { id: 'd3', name: 'HYRESAVTAL_LOKAL_1B.pdf', date: '2024-11-02', status: 'pending', deadlines: 0 },
    { id: 'd4', name: 'LEVERANTÖRSAVTAL_IT.pdf', date: '2024-11-05', status: 'ready', deadlines: 4 },
  ];

  const handleGlobalUpload = () => {
    setShowUploadModal(true);
  };

  const startProcessing = () => {
    setShowUploadModal(false);
    setIsProcessing(true);
    setProcessingStep(0);

    setTimeout(() => setProcessingStep(1), 1000);
    setTimeout(() => setProcessingStep(2), 2500);
    setTimeout(() => setProcessingStep(3), 4000);
    setTimeout(() => {
      setIsProcessing(false);
      setCurrentTab('review');
    }, 5000);
  };

  const navigateToDoc = () => {
    setActiveDocument('snorojning');
  };

  const closeDocument = () => {
    setActiveDocument(null);
    clearActive();
  };

  const clearActive = () => {
    setActiveId(null);
    setActiveData(null);
    setActiveType(null);
    setShowDeadlines(false);
    setSearchQuery('');
  };

  const handleDeadlineToggle = () => {
    if (showDeadlines) {
      clearActive();
    } else {
      setShowDeadlines(true);
      setSearchQuery('');
      activateParagraph('p3', 'deadline');
    }
  };

  const handleSearch = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    setShowDeadlines(false);

    if (query.toLowerCase().includes('salt') || query.toLowerCase().includes('halk')) {
      activateParagraph('p5', 'search');
    } else {
      setActiveId(null);
      setActiveData(null);
      setActiveType(null);
    }
  };

  const activateParagraph = (id, type) => {
    setActiveId(id);
    setActiveType(type);
    setActiveData(cardData[id]);

    setTimeout(() => {
      const element = paragraphRefs.current[id];
      if (element) {
        const rect = element.getBoundingClientRect();
        const parentElement = element.closest('.main-content-scroll');
        if (parentElement) {
          const parentRect = parentElement.getBoundingClientRect();
          setCardTop(rect.top - parentRect.top + (rect.height / 2));
        }
      }
    }, 50);
  };

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
          <div className="upload-box" onClick={startProcessing}>
            <div className="upload-icon-wrapper">
              <UploadCloud size={64} strokeWidth={1} color="var(--text-secondary)" />
            </div>
            <h2 className="upload-title" style={{fontSize: '28px', marginBottom: '10px'}}>Ladda upp PDF</h2>
            <p className="upload-subtitle" style={{fontSize: '16px', color: 'var(--text-secondary)'}}>Dra och släpp ditt avtal eller dokument här för att låta AI:n extrahera text, datum och tidsfrister.</p>

            <div className="upload-features">
              <span><CheckCircle2 size={16} /> Extraherar text</span>
              <span><CheckCircle2 size={16} /> Hittar tidsfrister</span>
              <span><CheckCircle2 size={16} /> Gör sökbart</span>
            </div>

            <button className="primary-btn" style={{marginTop: '40px'}}>Välj fil lokalt</button>
          </div>
        </div>
      </div>
    );
  };

  const renderOverview = () => (
    <div className="tab-content">
      {/* Hero Search Section */}
      <div className="hero-search-container">
        <h1 className="hero-search-title">Vad vill du veta?</h1>
        <p className="hero-search-subtitle">Sök i alla dokument, ställ frågor och få insikter direkt från RAG-systemet.</p>

        <div className="hero-search-box">
          <SearchIcon size={24} color="var(--accent-search)" className="hero-search-icon" />
          <input
            type="text"
            placeholder="T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'"
            className="hero-search-input"
          />
          <button className="hero-search-btn">
            Sök <ArrowRight size={18} />
          </button>
        </div>

        <div className="hero-search-suggestions">
          <span className="suggestion-pill">Styrelseprotokoll 2023</span>
          <span className="suggestion-pill">Underhållsplan</span>
          <span className="suggestion-pill">Årsredovisningar</span>
        </div>
      </div>
      <div className="overview-grid">
        <div className="overview-stats">
          <div className="stat-card glass-panel">
            <span className="stat-value">42</span>
            <span className="stat-label">Dokument</span>
          </div>
          <div className="stat-card glass-panel">
            <span className="stat-value" style={{color: 'var(--accent-date)'}}>3</span>
            <span className="stat-label">Granskningar väntar</span>
          </div>
          <div className="stat-card glass-panel">
            <span className="stat-value">12</span>
            <span className="stat-label">Kommande Tidsfrister</span>
          </div>
        </div>

        <div className="overview-main-sections" style={{ display: 'flex', gap: '30px', marginTop: '40px' }}>

          <div className="documents-section" style={{ flex: 1 }}>
            <h3 className="section-title">Senast aktivitet</h3>
            <div className="documents-grid">
              <div className="document-card glass-panel" onClick={navigateToDoc}>
                <div className="doc-icon"><FileText size={24} color="var(--accent-search)" /></div>
                <div className="doc-info">
                  <h4>SNÖRÖJNINGSAVTAL_2024.pdf</h4>
                  <span>Bearbetad • 2 bevakningar</span>
                </div>
              </div>
              <div className="document-card glass-panel">
                <div className="doc-icon dimmed"><FileText size={24} color="var(--text-secondary)" /></div>
                <div className="doc-info">
                  <h4>ANSTÄLLNINGSAVTAL_VD.pdf</h4>
                  <span>Bearbetad • 1 bevakning</span>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );

  const renderDocuments = () => (
    <div className="tab-content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 className="tab-title" style={{ marginBottom: 0 }}>Alla Dokument</h2>
        <div className="search-input-wrapper" style={{ width: '300px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', padding: '8px 16px', borderRadius: '8px' }}>
          <SearchIcon size={16} color="var(--text-secondary)" />
          <input type="text" placeholder="Sök dokumentnamn..." style={{ background: 'transparent', border: 'none', color: '#fff', width: '100%', outline: 'none', marginLeft: '8px' }} />
        </div>
      </div>

      {/* Toolbar */}
      <div className="documents-toolbar">
        <div className="toolbar-left">
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
              <th>Bevakningar</th>
              <th style={{textAlign: 'right'}}>Åtgärd</th>
            </tr>
          </thead>
          <tbody>
            {documentsData.map(doc => (
              <tr key={doc.id} onClick={navigateToDoc} style={{ cursor: 'pointer' }}>
                <td style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <FileText size={18} color={doc.status === 'ready' ? 'var(--accent-search)' : 'var(--text-secondary)'} />
                  <span style={{ fontWeight: 500 }}>{doc.name}</span>
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>{doc.date}</td>
                <td>
                  <span className={`status-badge ${doc.status}`}>
                    {doc.status === 'ready' ? 'Klar' : 'Väntar på granskning'}
                  </span>
                </td>
                <td style={{ color: doc.deadlines > 0 ? 'var(--accent-date)' : 'var(--text-secondary)' }}>
                  {doc.deadlines} st
                </td>
                <td style={{textAlign: 'right'}}>
                  <button className="icon-btn" onClick={(e) => { e.stopPropagation(); navigateToDoc(); }}>
                    <ArrowRight size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderReview = () => (
    <div className="tab-content flex-center">
      <div className="validation-box glass-panel">
        <div className="validation-header">
          <AlertCircle size={32} color="var(--accent-date)" />
          <h2>Validera Innehåll</h2>
          <p>Systemet har nyligen extraherat följande information. Vänligen granska innan de sparas till den globala tidslinjen.</p>
        </div>

        <div className="validation-items">
          <div className="validation-item">
            <CalendarIcon size={18} color="var(--accent-date)" />
            <div className="v-info">
              <h4>Start av snöröjningsjour (15 nov)</h4>
              <span>Hittat på Sida 2 i SNÖRÖJNINGSAVTAL_2024</span>
            </div>
          </div>
          <div className="validation-item">
            <CalendarIcon size={18} color="var(--accent-date)" />
            <div className="v-info">
              <h4>Slut av snöröjningsjour (15 apr)</h4>
              <span>Hittat på Sida 2 i SNÖRÖJNINGSAVTAL_2024</span>
            </div>
          </div>
          <div className="validation-item">
            <SearchIcon size={18} color="var(--accent-search)" />
            <div className="v-info">
              <h4>Regel för halkbekämpning (saltning)</h4>
              <span>Hittat på Sida 2 i SNÖRÖJNINGSAVTAL_2024</span>
            </div>
          </div>
        </div>

        <div className="validation-actions">
          <button className="icon-btn" onClick={() => setCurrentTab('overview')}>Kassera</button>
          <button className="primary-btn" onClick={() => {
            setCurrentTab('overview');
          }}>Godkänn och Spara</button>
        </div>
      </div>
    </div>
  );

  const renderDeadlines = () => (
    <div className="tab-content" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <h2 className="tab-title" style={{ textAlign: 'center', marginBottom: '10px' }}>Global Tidslinje</h2>
      <p style={{color: 'var(--text-secondary)', marginBottom: '60px', textAlign: 'center', maxWidth: '600px'}}>
        Aggregerad vy över alla tidsfrister och bevakningar i dina uppladdade avtal. Korten är sorterade kronologiskt.
      </p>

      <div className="centered-timeline">
        {timelineData.map((item, index) => {
          const isRight = index % 2 !== 0;
          return (
            <div key={item.id} className={`timeline-row ${isRight ? 'right' : 'left'}`}>
              <div className="timeline-date-label">{item.date}</div>
              <div className="timeline-center-dot"></div>

              <div className="timeline-card-wrapper">
                <div className="timeline-card glass-panel">
                  <div className="card-header deadline">
                    <CalendarIcon size={14} />
                    Bevakning
                  </div>
                  <div className="card-title">{item.title}</div>
                  <div className="card-description">{item.description}</div>
                  <div className="card-footer">
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <FileText size={12} />
                      {item.doc} (Sid {item.page})
                    </span>
                  </div>
                  <button className="open-doc-btn" onClick={navigateToDoc}>
                    Öppna i dokument <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  const renderDocumentCanvas = () => (
    <div className="canvas-wrapper">
      <header className="controls-header glass-panel">
        <button className="icon-btn back-btn" onClick={closeDocument}>
          <ChevronLeft size={18} />
          <span>Stäng dokument</span>
        </button>
        <div className="divider"></div>
        <div className="search-input-wrapper">
          <SearchIcon size={16} color="var(--text-secondary)" />
          <input
            type="text"
            placeholder="Sök inuti dokumentet..."
            value={searchQuery}
            onChange={handleSearch}
          />
          {searchQuery && (
            <X size={16} color="var(--text-secondary)" style={{ cursor: 'pointer' }} onClick={clearActive} />
          )}
        </div>
        <button className={`deadline-toggle ${showDeadlines ? 'active' : ''}`} onClick={handleDeadlineToggle}>
          <BellRing size={16} />
          {showDeadlines ? 'Göm bevakningar' : 'Visa bevakningar'}
        </button>
      </header>

      <div className="canvas-area">
        <DocumentView ref={paragraphRefs} activeId={activeId} searchMode={activeType === 'search'} />
        {activeId && (
          <div className="context-layer">
            <ContextCard type={activeType} data={activeData} topPosition={cardTop} />
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      {/* Persistent Sidebar */}
      <nav className="sidebar glass-panel">
        <div className="sidebar-brand">
          <div className="logo">Simons <span>RAG-system</span></div>
        </div>

        <div className="sidebar-upload">
          <button className="upload-btn" onClick={handleGlobalUpload}>
            <UploadCloud size={18} />
            Ladda upp dokument
          </button>
        </div>

        <div className="sidebar-menu">
          <button className={`nav-item ${currentTab === 'overview' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('overview'); setActiveDocument(null);}}>
            <LayoutDashboard size={20} /> Hem & Sök
          </button>
          <button className={`nav-item ${currentTab === 'documents' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('documents'); setActiveDocument(null);}}>
            <Folders size={20} /> Dokument
          </button>
          <button className={`nav-item ${currentTab === 'review' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('review'); setActiveDocument(null);}}>
            <CheckSquare size={20} /> Granskning
          </button>
          <button className={`nav-item ${currentTab === 'deadlines' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('deadlines'); setActiveDocument(null);}}>
            <Clock size={20} /> Bevakningar
          </button>
          <button className={`nav-item ${currentTab === 'chat' && !activeDocument ? 'active' : ''}`} onClick={() => {setCurrentTab('chat'); setActiveDocument(null);}}>
            <MessageSquare size={20} /> AI-chatt
          </button>
        </div>

        <div className="sidebar-footer">
          {showUserMenu && (
            <div className="user-menu-popover glass-panel">
              <div className="user-menu-item"><Settings size={16} /> Inställningar</div>
              <div className="user-menu-item"><HelpCircle size={16} /> Hjälp & Support</div>
              <div className="user-menu-divider"></div>
              <div className="user-menu-item text-danger"><LogOut size={16} /> Logga ut</div>
            </div>
          )}

          <div className="user-profile" onClick={() => setShowUserMenu(!showUserMenu)}>
            <div className="user-avatar">SR</div>
            <div className="user-info">
              <span className="user-name">Simon R</span>
              <span className="user-email">simon@docintel.se</span>
            </div>
            <ChevronUp size={16} color="var(--text-secondary)" style={{ marginLeft: 'auto', transform: showUserMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="main-content-scroll">
        {renderUploadModal()}
        {isProcessing && renderProcessingOverlay()}

        {!isProcessing && activeDocument && renderDocumentCanvas()}

        {!isProcessing && !activeDocument && (
          <div className="tab-container">
            {currentTab === 'overview' && renderOverview()}
            {currentTab === 'documents' && renderDocuments()}
            {currentTab === 'review' && renderReview()}
            {currentTab === 'deadlines' && renderDeadlines()}
            {currentTab === 'chat' && (
              <div className="chat-container">
                <div className="chat-header">
                  <h2 className="tab-title" style={{ marginBottom: '8px' }}>Chatta med dokument</h2>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '15px', marginBottom: '30px' }}>Ställ frågor i klartext och få svar direkt från din dokumentdatabas.</p>
                </div>

                <div className="chat-messages-area">
                  {chatMessages.map((msg, idx) => (
                    <div key={idx} className={`chat-message ${msg.role}`}>
                      <div className="chat-avatar">
                        {msg.role === 'ai' ? <Sparkles size={16} /> : 'SR'}
                      </div>
                      <div className="chat-content">
                        {msg.content}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="chat-input-area">
                  <div className="chat-input-box">
                    <input
                      type="text"
                      placeholder="T.ex. 'Vilka regler gäller för andrahandsuthyrning?'..."
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleChatSubmit()}
                    />
                    <button className="chat-send-btn" onClick={handleChatSubmit}>
                      <Send size={18} />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
