import React, { useState, useRef, useEffect } from 'react';
import {
  Search as SearchIcon, BellRing, X, UploadCloud, FileText, Circle,
  Loader2, CheckCircle2, ChevronLeft, ChevronRight, Calendar as CalendarIcon,
  ArrowRight, AlertCircle, LayoutDashboard, Folders, CheckSquare, Clock,
  Trash2, Edit3, ChevronUp, Settings, HelpCircle, LogOut,
  Filter, ArrowDownUp, List, LayoutGrid, MessageSquare, Send, Sparkles
} from 'lucide-react';
import ContextCard from './components/ContextCard';
import DocumentView from './components/DocumentView';
import SettingsView from './components/SettingsView';
import './App.css';

function App() {
  const [currentTab, setCurrentTab] = useState('overview'); // overview, documents, review, deadlines, search
  const [activeDocument, setActiveDocument] = useState(null); // null or doc ID e.g. 'snorojning'
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  // Settings State
  const [activeSettingsTab, setActiveSettingsTab] = useState('dokument');
  const [settingsConfig, setSettingsConfig] = useState({
    // Dokument
    allowedFormats: ['pdf', 'docx', 'jpg'],
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
    aiModel: 'gpt-4o',
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

  // QA Dashboard State
  const [activeQaDoc, setActiveQaDoc] = useState(0);
  const [qaActiveSubTab, setQaActiveSubTab] = useState('pages');
  const [qaActivePage, setQaActivePage] = useState(1);
  const [showPageDropdown, setShowPageDropdown] = useState(false);
  const dropdownRef = useRef(null);
  
  const originalScrollRef = useRef(null);
  const extractedScrollRef = useRef(null);
  const isSyncScrolling = useRef(false);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowPageDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSyncScroll = (fromRef, toRef) => {
    if (isSyncScrolling.current) {
      isSyncScrolling.current = false;
      return;
    }
    if (fromRef.current && toRef.current) {
      isSyncScrolling.current = true;
      const percentage = fromRef.current.scrollTop / (fromRef.current.scrollHeight - fromRef.current.clientHeight);
      toRef.current.scrollTop = percentage * (toRef.current.scrollHeight - toRef.current.clientHeight);
    }
  };

  const togglePageStatus = (docId, pageNum) => {
    setQaDocuments(prevDocs => prevDocs.map(doc => {
      if (doc.id !== docId) return doc;
      
      const newPagesContent = doc.pagesContent.map(p => {
        if (p.pageNum !== pageNum) return p;
        const nextStatus = p.status === 'approved' ? 'unchecked' : 'approved';
        return { ...p, status: nextStatus };
      });

      // Recalculate dynamic metrics
      const approvedCount = newPagesContent.filter(p => p.status === 'approved').length;
      const warningCount = newPagesContent.filter(p => p.status === 'warning').length;
      const total = doc.pages;
      
      const nextProblemsCount = warningCount; // Problem upptäckta matches warning status count

      return {
        ...doc,
        problemsCount: nextProblemsCount,
        pagesContent: newPagesContent
      };
    }));
  };

  const [qaDocuments, setQaDocuments] = useState([
    {
      id: 0,
      title: 'SNÖRÖJNINGSAVTAL_2024.pdf',
      health: 98,
      pages: 3,
      ocrPages: 1,
      chunks: 45,
      problemsCount: 0,
      textCoverage: '100%',
      warnings: [],
      date: '2024-10-01',
      pagesContent: [
        {
          pageNum: 1,
          isOcr: false,
          status: 'approved',
          originalMock: {
            header: 'AVTAL OM SNÖRÖJNING 2024',
            meta: 'Datum: 2024-10-01 | Referens: SNÖ-BRF-99',
            paragraphs: [
              'Detta avtal har ingåtts mellan Bostadsrättsföreningen Lappen (nedan kallad Föreningen) och Snösvängen AB (nedan kallad Entreprenören).',
              '§1. OMFATTNING',
              'Entreprenören åtar sig att utföra snöröjning, maskinell sopning samt halkbekämpning på Föreningens gemensamma körytor, gångbanor samt entréer i enlighet med överenskommet schema.'
            ]
          },
          extractedText: `AVTAL OM SNÖRÖJNING 2024\nDatum: 2024-10-01 | Referens: SNÖ-BRF-99\n\nDetta avtal har ingåtts mellan Bostadsrättsföreningen Lappen (nedan kallad Föreningen) och Snösvängen AB (nedan kallad Entreprenören).\n\n§1. OMFATTNING\nEntreprenören åtar sig att utföra snöröjning, maskinell sopning samt halkbekämpning på Föreningens gemensamma körytor, gångbanor samt entréer i enlighet med överenskommet schema.`
        },
        {
          pageNum: 2,
          isOcr: true,
          status: 'unchecked',
          originalMock: {
            header: '§2. PRISER OCH JOURTIDER',
            meta: 'Utrustning och Timers',
            paragraphs: [
              'Aktiviteter debiteras enligt följande prislista:',
              '- Maskinell snöröjning (traktor): 1 250 kr/tim',
              '- Manuell skottning (trappor & entréer): 450 kr/tim',
              '- Halkbekämpning (salt/sand): 350 kr/säck',
              'Jourperioden löper oavkortat från 15 november till 15 april.'
            ]
          },
          extractedText: `§2. PRISER OCH JOURTIDER\nUtrustning och Timers\n\nAktiviteter debiteras enligt följande prislista:\n- Maskinell snöröjning (traktor): 1 250 kr/tim\n- Manuell skottning (trappor & entréer): 450 kr/tim\n- Halkbekämpning (salt/sand): 350 kr/säck\n\nJourperioden löper oavkortat från 15 november till 15 april.`
        },
        {
          pageNum: 3,
          isOcr: false,
          status: 'unchecked',
          originalMock: {
            header: '§3. UPPFÖLJNING & SIGNATUR',
            meta: 'Särskilda avtalsvillkor',
            paragraphs: [
              'Eventuella anmärkningar mot utfört arbete skall anmälas senast 24 timmar efter slutfört pass.',
              'Underskrivet elektroniskt:',
              'Brf Lappen: Simon R. (Styrelseordförande)',
              'Snösvängen AB: Gunnar S. (VD)'
            ]
          },
          extractedText: `§3. UPPFÖLJNING & SIGNATUR\nSärskilda avtalsvillkor\n\nEventuella anmärkningar mot utfört arbete skall anmälas senast 24 timmar efter slutfört pass.\n\nUnderskrivet elektroniskt:\nBrf Lappen: Simon R. (Styrelseordförande)\nSnösvängen AB: Gunnar S. (VD)`
        }
      ]
    },
    {
      id: 1,
      title: 'STYRELSEPROTOKOLL_MARS.pdf',
      health: 65,
      pages: 2,
      ocrPages: 2,
      chunks: 12,
      problemsCount: 2,
      textCoverage: '89%',
      warnings: ['Sida 2: Otydlig tabellstruktur identifierad under parsing', 'Sida 2: Innehåller handskrivna anteckningar i marginalen som kan ha förbisetts'],
      date: '2024-03-12',
      pagesContent: [
        {
          pageNum: 1,
          isOcr: true,
          status: 'approved',
          originalMock: {
            header: 'STYRELSEPROTOKOLL - BRF LAPPEN',
            meta: 'Mötesdatum: 2024-03-12 | Närvarande: Simon, Karin, Johan',
            paragraphs: [
              'Mötet öppnades kl 19:00 av ordförande Simon.',
              '§1. FÖREGÅENDE PROTOKOLL',
              'Protokollet från februarmötet lades till handlingarna utan anmärkningar.'
            ]
          },
          extractedText: `STYRELSEPROTOKOLL - BRF LAPPEN\nMötesdatum: 2024-03-12 | Närvarande: Simon, Karin, Johan\n\nMötet öppnades kl 19:00 av ordförande Simon.\n\n§1. FÖREGÅENDE PROTOKOLL\nProtokollet från februarmötet lades till handlingarna utan anmärkningar.`
        },
        {
          pageNum: 2,
          isOcr: true,
          status: 'warning',
          originalMock: {
            header: '§2. BESLUT OM UNDERHÅLL OCH BUDGET',
            meta: 'Protokollfört ekonomibeslut',
            isTable: true,
            tableRows: [
              { col1: 'Åtgärd', col2: 'Budget', col3: 'Status' },
              { col1: 'Fasadmålning', col2: '150 000 kr', col3: 'Beviljad' },
              { col1: 'OVK-besiktning', col2: '22 000 kr', col3: 'Påbörjad' },
              { col1: 'Stamspolning', col2: '85 000 kr', col3: 'Skjuten' }
            ]
          },
          extractedText: `§2. BESLUT OM UNDERHÅLL OCH BUDGET\nProtokollfört ekonomibeslut\n\n[PARSING ERROR - MERGED TABLE CELL VALUES]\nÅtgärdBudgetStatus\nFasadmålning150 000 krBeviljad\nOVK-besiktning22 000 krPåbörjad\nStamspolning85 000 krSkjuten`
        }
      ]
    },
    {
      id: 2,
      title: 'STADGAR_BRF_LAPPEN.pdf',
      health: 100,
      pages: 2,
      ocrPages: 0,
      chunks: 120,
      problemsCount: 0,
      textCoverage: '100%',
      warnings: [],
      date: '2023-11-20',
      pagesContent: [
        {
          pageNum: 1,
          isOcr: false,
          status: 'unchecked',
          originalMock: {
            header: 'STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN LAPPEN',
            meta: 'Registrerad hos Bolagsverket: 2023-11-20',
            paragraphs: [
              'Föreningens firma är Bostadsrättsföreningen Lappen. Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att upplåta bostadslägenheter under nyttjanderätt.',
              '§1. MEDLEMSKAP',
              'Medlemskap i föreningen kan sökas av fysisk eller juridisk person som förvärvat bostadsrätt i föreningens fastighet.'
            ]
          },
          extractedText: `STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN LAPPEN\nRegistrerad hos Bolagsverket: 2023-11-20\n\nFöreningens firma är Bostadsrättsföreningen Lappen. Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att upplåta bostadslägenheter under nyttjanderätt.\n\n§1. MEDLEMSKAP\nMedlemskap i föreningen kan sökas av fysisk eller juridisk person som förvärvat bostadsrätt i föreningens fastighet.`
        },
        {
          pageNum: 2,
          isOcr: false,
          status: 'unchecked',
          originalMock: {
            header: '§2. AVGIFTER & ÖVERLÅTELSE',
            meta: 'Ekonomiska förpliktelser',
            paragraphs: [
              'Årsavgiften fastställs av styrelsen och fördelas på bostadsrätterna efter lägenheternas andelstal.',
              'Överlåtelseavgift och pantsättningsavgift får tas ut efter beslut av styrelsen.'
            ]
          },
          extractedText: `§2. AVGIFTER & ÖVERLÅTELSE\nEkonomiska förpliktelser\n\nÅrsavgiften fastställs av styrelsen och fördelas på bostadsrätterna efter lägenheternas andelstal.\n\nÖverlåtelseavgift och pantsättningsavgift får tas ut efter beslut av styrelsen.`
        }
      ]
    }
  ]);

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

  const renderReview = () => {
    const doc = qaDocuments[activeQaDoc];
    const activePageNum = qaActivePage > doc.pages ? 1 : qaActivePage;
    const currentPage = doc.pagesContent ? doc.pagesContent[activePageNum - 1] : null;

    return (
      <div className="qa-container">
        <div className="qa-sidebar glass-panel">
          <h3 style={{ margin: '0 0 16px 0', fontSize: '14px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Granskning (QA)</h3>
          <div className="qa-doc-list">
            {qaDocuments.map((d, index) => (
              <div 
                key={d.id} 
                className={`qa-list-item ${activeQaDoc === index ? 'active' : ''}`}
                onClick={() => {
                  setActiveQaDoc(index);
                  setQaActivePage(1);
                }}
              >
                <div className="qa-list-header">
                  <span className="qa-doc-title">{d.title}</span>
                  {d.warnings.length > 0 ? (
                    <AlertCircle size={14} color="var(--accent-date)" />
                  ) : (
                    <CheckCircle2 size={14} color="#4ade80" />
                  )}
                </div>
                <div className="qa-list-meta">
                  {d.date}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="qa-main glass-panel">
          <div className="qa-main-header">
            <div>
              <h2 style={{ fontSize: '24px', marginBottom: '8px' }}>{doc.title}</h2>
              <div style={{ display: 'flex', gap: '16px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                <span>ID: {doc.id}</span>
                <span>Inläst: {doc.date}</span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button className="toolbar-btn" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: '#ef4444' }} onClick={() => alert('Fel rapportat till systemadministratör.')}>
                Rapportera fel
              </button>
              <button className="primary-btn" style={{ padding: '8px 16px', fontSize: '13px' }} onClick={() => alert('Dokumentet har markerats som granskat och godkänt.')}>
                Markera dokumentet som granskat
              </button>
            </div>
          </div>

          <div className="qa-metrics-grid">
            <div className="qa-metric-box">
              <span className="qa-metric-value">{doc.pages}</span>
              <span className="qa-metric-label">Sidor</span>
            </div>
            <div className="qa-metric-box">
              <span className="qa-metric-value" style={{ color: doc.problemsCount > 0 ? 'var(--accent-date)' : 'inherit'}}>{doc.problemsCount}</span>
              <span className="qa-metric-label">Problem Upptäckta</span>
            </div>
          </div>

          {doc.warnings.length > 0 && (
            <div className="qa-warnings-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: 'var(--accent-date)', fontWeight: 'bold' }}>
                <AlertCircle size={16} /> Parsing-varningar
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px', color: 'var(--text-primary)', fontSize: '14px' }}>
                {doc.warnings.map((w, i) => <li key={i} style={{ marginBottom: '4px' }}>{w}</li>)}
              </ul>
            </div>
          )}

          <div className="qa-subtabs">
            <button className={`qa-subtab ${qaActiveSubTab === 'pages' ? 'active' : ''}`} onClick={() => setQaActiveSubTab('pages')}>Jämför original & text</button>
            <button className={`qa-subtab ${qaActiveSubTab === 'chunks' ? 'active' : ''}`} onClick={() => setQaActiveSubTab('chunks')}>Chunking-karta</button>
            <button className={`qa-subtab ${qaActiveSubTab === 'search' ? 'active' : ''}`} onClick={() => setQaActiveSubTab('search')}>Test-sök</button>
          </div>

          <div className="qa-content-area">
            {qaActiveSubTab === 'pages' && currentPage && (
              <div className="qa-split-container">
                {/* Stable Page Dock */}
                <div className="qa-page-dock-container" ref={dropdownRef}>
                  <div className={`qa-page-dock ${currentPage.status === 'approved' ? 'approved' : ''}`}>
                    <button 
                      className="qa-page-dock-nav-btn" 
                      disabled={activePageNum === 1} 
                      onClick={() => setQaActivePage(activePageNum - 1)}
                    >
                      <ChevronLeft size={16} />
                    </button>
                    
                    <div className="qa-page-dock-center">
                      <span 
                        className="qa-page-dock-text" 
                        onClick={() => setShowPageDropdown(!showPageDropdown)}
                        title="Översikt (Alla sidor)"
                      >
                        Sida {activePageNum} av {doc.pages}
                      </span>
                      <button 
                        className="qa-page-dock-toggle-btn"
                        onClick={() => togglePageStatus(doc.id, activePageNum)}
                        title={currentPage.status === 'approved' ? 'Markera som ogodkänd' : 'Markera sida som granskad'}
                      >
                        {currentPage.status === 'approved' ? (
                          <CheckCircle2 size={16} fill="#4ade80" color="#fff" />
                        ) : (
                          <Circle size={16} color="var(--text-secondary)" />
                        )}
                      </button>
                    </div>

                    <button 
                      className="qa-page-dock-nav-btn" 
                      disabled={activePageNum === doc.pages} 
                      onClick={() => setQaActivePage(activePageNum + 1)}
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {/* Filmstrip Popover */}
                  {showPageDropdown && (
                    <div className="qa-filmstrip-overlay glass-panel">
                      <div className="qa-filmstrip-header">
                        <h4>Sidöversikt</h4>
                        <span className="qa-filmstrip-subtitle">Klicka på en sida för att hoppa till den</span>
                      </div>
                      <div className="qa-filmstrip-grid">
                        {doc.pagesContent.map((p) => (
                          <div 
                            key={p.pageNum} 
                            className={`qa-page-card ${p.pageNum === activePageNum ? 'active' : ''}`}
                            onClick={() => {
                              setQaActivePage(p.pageNum);
                              setShowPageDropdown(false);
                            }}
                          >
                            <div className="qa-page-card-header">
                              <span className="qa-page-card-title">Sida {p.pageNum}</span>
                              <span className={`qa-page-indicator-dot ${p.status}`} style={{ opacity: 1, transform: 'none' }} />
                            </div>
                            <div className="qa-page-card-status-text">
                              {p.status === 'approved' && 'Granskad'}
                              {p.status === 'warning' && 'Behöver kontroll'}
                              {p.status === 'unchecked' && 'Inte granskad'}
                            </div>
                            {p.isOcr && (
                              <div className="qa-page-card-meta">
                                Texten lästes in via OCR
                              </div>
                            )}
                            <button 
                              className={`qa-page-card-check-btn ${p.status === 'approved' ? 'checked' : ''}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                togglePageStatus(doc.id, p.pageNum);
                              }}
                            >
                              <CheckCircle2 size={16} />
                              <span>{p.status === 'approved' ? 'Avmarkera' : 'Markera som granskad'}</span>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="qa-split-workspace">
                  {/* Left: Original Mock PDF Rendering */}
                  <div className="qa-split-pane original">
                    <div className="qa-pane-title">Original PDF (Visualisering)</div>
                    <div className="qa-pdf-page-mock" ref={originalScrollRef} onScroll={() => handleSyncScroll(originalScrollRef, extractedScrollRef)}>
                      {currentPage.originalMock.isTable ? (
                        <div className="qa-pdf-table-wrapper">
                          <h4 className="qa-pdf-doc-header">{currentPage.originalMock.header}</h4>
                          <span className="qa-pdf-doc-meta">{currentPage.originalMock.meta}</span>
                          <table className="qa-pdf-table">
                            <thead>
                              <tr>
                                <th>{currentPage.originalMock.tableRows[0].col1}</th>
                                <th>{currentPage.originalMock.tableRows[0].col2}</th>
                                <th>{currentPage.originalMock.tableRows[0].col3}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {currentPage.originalMock.tableRows.slice(1).map((row, index) => (
                                <tr key={index}>
                                  <td>{row.col1}</td>
                                  <td>{row.col2}</td>
                                  <td>{row.col3}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="qa-pdf-text-wrapper">
                          <h4 className="qa-pdf-doc-header">{currentPage.originalMock.header}</h4>
                          <span className="qa-pdf-doc-meta">{currentPage.originalMock.meta}</span>
                          <div className="qa-pdf-paragraphs">
                            {currentPage.originalMock.paragraphs.map((p, i) => (
                              <p key={i} className="qa-pdf-paragraph">{p}</p>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right: Extracted Monospace Text */}
                  <div className="qa-split-pane extracted">
                    <div className="qa-pane-title">Extraherad Text (OCR / Parser)</div>
                    <textarea 
                      ref={extractedScrollRef} 
                      onScroll={() => handleSyncScroll(extractedScrollRef, originalScrollRef)}
                      className="qa-extracted-text-area" 
                      readOnly 
                      value={currentPage.extractedText}
                    />
                  </div>
                </div>
              </div>
            )}
            
            {qaActiveSubTab === 'chunks' && (
              <div className="qa-mock-content">
                <div className="qa-chunk-block">
                  <div className="qa-chunk-meta">Chunk #1 • Sida 1 • 45 tokens</div>
                  <div className="qa-chunk-text">AVTAL OM SNÖRÖJNING 2024 Parter: Brf Lappen och Snösvängen AB.</div>
                </div>
                <div className="qa-chunk-block">
                  <div className="qa-chunk-meta">Chunk #2 • Sida 1 • 112 tokens</div>
                  <div className="qa-chunk-text">Detta avtal löper från 2024-10-15 tills vidare. Uppsägningstid är 3 månader. Entreprenören ansvarar för...</div>
                </div>
              </div>
            )}

            {qaActiveSubTab === 'search' && (
              <div className="qa-mock-content">
                <div className="search-input-wrapper" style={{ width: '100%', marginBottom: '16px' }}>
                  <SearchIcon size={16} />
                  <input type="text" placeholder="Gör en provsökning i dokumentets vektor-index..." className="toolbar-search-input" />
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '13px', textAlign: 'center', marginTop: '40px' }}>
                  Skriv en sökterm för att se vilka chunks som matchar bäst (Cosine Similarity).
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

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
          {showUserMenu && (
            <div className="user-menu-popover glass-panel">
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
            {currentTab === 'settings' && (
              <SettingsView 
                settingsConfig={settingsConfig} 
                setSettingsConfig={setSettingsConfig}
                activeSettingsTab={activeSettingsTab}
                setActiveSettingsTab={setActiveSettingsTab}
              />
            )}
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
