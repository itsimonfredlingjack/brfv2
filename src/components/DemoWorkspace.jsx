import React, { useState, useRef, useEffect } from 'react';
import {
  Search as SearchIcon, BellRing, X, FileText, Circle,
  CheckCircle2, ChevronLeft, ChevronRight, Calendar as CalendarIcon,
  ArrowRight, AlertCircle,
} from 'lucide-react';
import ContextCard from './ContextCard';
import DocumentView from './DocumentView';
import { qaDocuments as qaDocumentsSeed, timelineData, cardData } from '../demoData';

// Dev-gated demo scaffolding (cleanup/verified-ui Task 5).
//
// Granskning (QA review), Bevakningar (timeline), and the Document Canvas
// they both open are pre-existing design-template tabs that render
// fabricated, pipeline-shaped data (src/demoData.js) — none of it came from
// the real retrieval/verification pipeline. A fresh-context adversarial
// verifier found them production-reachable after the rest of the cleanup
// phase (C1-C4) was confirmed clean. Simon's resolution: keep them for
// dev-server demos, hide them from production.
//
// This component is the code-splitting boundary that makes that hiding
// real, not just cosmetic: App.jsx only ever reaches it through
// `React.lazy(() => import('./components/DemoWorkspace'))`, itself wrapped
// in a literal `import.meta.env.DEV` check (not the demoTabsEnabled()
// helper — a raw literal is what lets Vite/esbuild dead-code-eliminate the
// whole import() call, and therefore this module's chunk, out of a
// production build; demoTabsEnabled() is still the source of truth for
// every *rendering* decision, here and in App.jsx). Verified by grepping
// `dist/` for demo markers after `npm run build` — see
// docs/evidence/verified-ui-restore.md.
//
// src/no-fabrication.test.js's "demoData allowlist" tests enforce both
// halves of this boundary: demoData.js may only be imported from here (and
// from DocumentView.jsx, which this component itself imports), and this
// component may never be statically imported by anything — only dynamically,
// only from App.jsx.
function DemoWorkspace({ currentTab, activeDocument, setActiveDocument }) {
  // ---- Granskning (QA review) state ----
  const [qaDocuments, setQaDocuments] = useState(qaDocumentsSeed);
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

  // ---- Document Canvas state ----
  const [activeId, setActiveId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showDeadlines, setShowDeadlines] = useState(false);
  const [cardTop, setCardTop] = useState(0);
  const [activeData, setActiveData] = useState(null);
  const [activeType, setActiveType] = useState(null);

  const paragraphRefs = useRef({});

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
              <h2 style={{ fontSize: '24px', marginBottom: '8px' }}>
                {doc.title}
                <span className="demo-badge">Demo — exempeldata</span>
              </h2>
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
      <h2 className="tab-title" style={{ textAlign: 'center', marginBottom: '10px' }}>
        Global Tidslinje
        <span className="demo-badge">Demo — exempeldata</span>
      </h2>
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
        <span className="demo-badge">Demo — exempeldata</span>
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

  if (activeDocument) return renderDocumentCanvas();
  if (currentTab === 'review') return renderReview();
  if (currentTab === 'deadlines') return renderDeadlines();
  return null;
}

export default DemoWorkspace;
