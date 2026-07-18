import React, { useState } from 'react';
import { ArrowLeft, CheckCircle2, Loader2, FileText, ArrowRight, ZoomOut, ZoomIn, Search, Check, Calendar, ThumbsDown, MessageCircle } from 'lucide-react';
import DocumentChat from './DocumentChat';
import { MOCK_TEXT_EXTRACTION } from '../data/MockData';

export default function DocumentWorkspace({ 
  document, 
  bevakningar, 
  closeDocument, 
  onApprovePage, 
  onMarkBevakningDone,
  showToast
}) {
  const [workspaceTab, setWorkspaceTab] = useState('read'); // 'read', 'review', 'chat'
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [reportMenuOpen, setReportMenuOpen] = useState(false);
  
  // Mobile segment controls
  const [mobileQASegment, setMobileQASegment] = useState('pdf'); // 'pdf' | 'text'
  const [mobileReadSegment, setMobileReadSegment] = useState('pdf'); // 'pdf' | 'info'

  const handleApprove = () => {
    onApprovePage(document.id);
    showToast('Sidan har godkänts.');
  };

  const handleReport = (reason) => {
    setReportMenuOpen(false);
    showToast(`Problem rapporterat: ${reason}`, 'error');
  };

  return (
    <div className="workspace-container">
      <header className="workspace-header">
        <div className="workspace-header-left">
          <button className="icon-action-btn" onClick={closeDocument} title="Tillbaka till listan" aria-label="Tillbaka">
            <ArrowLeft size={20} />
          </button>
          <div className="workspace-doc-info">
            <h1 className="workspace-doc-title">{document.name}</h1>
            <div className="workspace-doc-meta">
              {document.status === 'Färdigbehandlad' ? (
                <span className="status-text ok"><CheckCircle2 size={12}/> Färdigbehandlad</span>
              ) : (
                <span className="status-text muted"><Loader2 size={12} className="spin"/> Behandlas</span>
              )}
              <span className="meta-divider">·</span>
              <span className="status-text">{document.pages} sidor</span>
            </div>
          </div>
        </div>
        
        <div className="workspace-tabs" role="tablist">
          <button 
            className={`workspace-tab ${workspaceTab === 'read' ? 'active' : ''}`} 
            onClick={() => setWorkspaceTab('read')}
            role="tab"
            aria-selected={workspaceTab === 'read'}
            aria-label="Läs dokument"
          >
            <FileText size={16}/> <span className="tab-label">Läs</span>
          </button>
          <button 
            className={`workspace-tab ${workspaceTab === 'review' ? 'active' : ''}`} 
            onClick={() => setWorkspaceTab('review')}
            role="tab"
            aria-selected={workspaceTab === 'review'}
            aria-label="Kvalitetskontroll"
          >
            <CheckCircle2 size={16}/> <span className="tab-label">Granska</span>
            {document.qa === 'Behöver granskas' && <span className="tab-badge warning" aria-label="Kräver granskning">!</span>}
          </button>
          <button 
            className={`workspace-tab ${workspaceTab === 'chat' ? 'active' : ''}`} 
            onClick={() => setWorkspaceTab('chat')}
            role="tab"
            aria-selected={workspaceTab === 'chat'}
            aria-label="Fråga dokumentet"
          >
            <MessageCircle size={16}/> <span className="tab-label">Fråga</span>
          </button>
        </div>

        <div className="workspace-header-right desktop-only">
           <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Dokument 1 av 1</span>
        </div>
      </header>

      <div className="workspace-content">
        {/* READ MODE */}
        {workspaceTab === 'read' && (
          <div className="workspace-split read-mode">
            
            {/* Mobile Segmented Control */}
            <div className="mobile-only segment-control">
              <button className={`segment-btn ${mobileReadSegment === 'pdf' ? 'active' : ''}`} onClick={() => setMobileReadSegment('pdf')}>PDF</button>
              <button className={`segment-btn ${mobileReadSegment === 'info' ? 'active' : ''}`} onClick={() => setMobileReadSegment('info')}>Information</button>
            </div>

            <div className={`pdf-viewer-container ${mobileReadSegment === 'info' ? 'mobile-hidden' : ''}`}>
              <div className="pdf-toolbar">
                <div className="pdf-nav">
                   <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                   <span>Sida {pdfPage} av {document.pages}</span>
                   <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(document.pages, pdfPage + 1))} disabled={pdfPage === document.pages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
                </div>
                <div className="pdf-actions">
                   <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.max(50, z - 10))} title="Zooma ut" aria-label="Zooma ut"><ZoomOut size={16}/></button>
                   <span style={{ fontSize: '12px', width: '40px', textAlign: 'center' }}>{pdfZoom}%</span>
                   <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.min(200, z + 10))} title="Zooma in" aria-label="Zooma in"><ZoomIn size={16}/></button>
                   <div className="divider"></div>
                   <button className="icon-action-btn" onClick={() => showToast('Sökning inuti PDF är ej implementerad i mockupen.', 'error')} title="Sök i dokument" aria-label="Sök"><Search size={16}/></button>
                </div>
              </div>
              
              <div className="pdf-canvas">
                <div className="mock-pdf-page" style={{ transform: `scale(${pdfZoom / 100})` }}>
                  {document.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                    <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'serif', color: '#000', fontSize: '14px', lineHeight: 1.6 }}>
                      {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                    </div>
                  ) : (
                    <div className="mock-pdf-placeholder">
                      <FileText size={48} color="#ccc" style={{ marginBottom: '16px' }}/>
                      <div>Visar sida {pdfPage} av {document.name}</div>
                      <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>(Detta är en mockad PDF-visare)</div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className={`workspace-sidepanel ${mobileReadSegment === 'pdf' ? 'mobile-hidden' : ''}`}>
              <div className="panel-section">
                <h3>Dokumentinformation</h3>
                <div className="info-grid">
                  <div className="info-item">
                    <span className="info-label">Laddades upp</span>
                    <span className="info-value">{document.date}</span>
                  </div>
                  <div className="info-item">
                    <span className="info-label">Systembearbetning</span>
                    <span className="info-value">
                      {document.status === 'Färdigbehandlad' ? <span className="status-text ok">Färdigbehandlad</span> : <span className="status-text muted">Behandlas</span>}
                    </span>
                  </div>
                  <div className="info-item">
                    <span className="info-label">Kvalitetskontroll</span>
                    <span className="info-value">
                      {document.qa === 'Granskad' ? <span className="status-text ok">Granskad</span> : <span className="status-text warning">Behöver granskas</span>}
                    </span>
                  </div>
                </div>
              </div>

              <div className="panel-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <h3>Bevakningar i dokumentet</h3>
                  {bevakningar.length > 0 && (
                    <span className="status-badge warning" style={{ background: 'transparent', border: '1px solid var(--status-warning)', color: 'var(--status-warning)' }}>
                      {bevakningar.length}
                    </span>
                  )}
                </div>
                
                <div className="bevakning-list">
                  {bevakningar.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Inga bevakningar funna.</div>
                  ) : (
                    bevakningar.map(b => (
                      <div key={b.id} className={`bevakning-card ${b.done ? 'done' : ''}`}>
                        <div className="bevakning-header">
                          <div className="bevakning-date"><Calendar size={14}/> {b.date}</div>
                          {b.done && <span className="status-badge ok" style={{ padding: '2px 6px', fontSize: '10px' }}>Klar</span>}
                        </div>
                        <div className="bevakning-title">{b.title}</div>
                        <div className="bevakning-desc">{b.desc}</div>
                        <div className="bevakning-actions">
                          <button className="small-action-btn" onClick={() => { setPdfPage(b.page); setMobileReadSegment('pdf'); }}>Sida {b.page}</button>
                          {!b.done && <button className="small-action-btn ok" onClick={() => onMarkBevakningDone(b.id)}><Check size={14}/> Markera klar</button>}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* REVIEW MODE */}
        {workspaceTab === 'review' && (
          <div className="workspace-split review-mode">
            
            {/* Mobile Segmented Control */}
            <div className="mobile-only segment-control">
              <button className={`segment-btn ${mobileQASegment === 'pdf' ? 'active' : ''}`} onClick={() => setMobileQASegment('pdf')}>Original</button>
              <button className={`segment-btn ${mobileQASegment === 'text' ? 'active' : ''}`} onClick={() => setMobileQASegment('text')}>Extraherad text</button>
            </div>

            <div className={`pdf-viewer-container half ${mobileQASegment === 'text' ? 'mobile-hidden' : ''}`}>
              <div className="pdf-toolbar">
                 <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Original (PDF)</span>
                 <div className="pdf-nav">
                   <button className="icon-action-btn" onClick={() => setPdfPage(Math.max(1, pdfPage - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                   <span>Sid {pdfPage} / {document.pages}</span>
                   <button className="icon-action-btn" onClick={() => setPdfPage(Math.min(document.pages, pdfPage + 1))} disabled={pdfPage === document.pages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
                </div>
              </div>
              <div className="pdf-canvas">
                <div className="mock-pdf-page" style={{ transform: 'scale(0.8)', transformOrigin: 'top center' }}>
                  {document.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
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

            <div className={`extraction-container half ${mobileQASegment === 'pdf' ? 'mobile-hidden' : ''}`}>
              <div className="pdf-toolbar extraction-toolbar desktop-only">
                <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Extraherad text</span>
              </div>
              <div className="extraction-content">
                {document.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
                  <div className="extracted-text-box">
                    {MOCK_TEXT_EXTRACTION.d1[pdfPage]}
                  </div>
                ) : (
                  <div className="extracted-text-box empty">
                     Text extraheras eller mockdata saknas för denna fil/sida.
                  </div>
                )}
              </div>
              
              {/* Sticky QA Actions on Mobile */}
              <div className="extraction-actions sticky-bottom">
                 <button className="primary-action-btn ok" onClick={handleApprove}>
                   <CheckCircle2 size={16}/> <span className="action-label">Godkänn sida</span>
                 </button>
                 <div style={{ position: 'relative' }}>
                   <button className="primary-action-btn warning" onClick={() => setReportMenuOpen(!reportMenuOpen)} aria-haspopup="true" aria-expanded={reportMenuOpen}>
                     <ThumbsDown size={16}/> <span className="action-label">Rapportera problem</span>
                   </button>
                   {reportMenuOpen && (
                     <div className="report-menu popover-top">
                       <button onClick={() => handleReport('Saknad text')}>Saknad text</button>
                       <button onClick={() => handleReport('Felaktigt tecken / Skräptecken')}>Felaktigt tecken / Skräptecken</button>
                       <button onClick={() => handleReport('Fel styckeordning')}>Fel styckeordning</button>
                       <button onClick={() => handleReport('Låg läsbarhet i PDF')}>Låg läsbarhet i PDF</button>
                     </div>
                   )}
                 </div>
              </div>
            </div>
          </div>
        )}

        {/* CHAT MODE */}
        {workspaceTab === 'chat' && (
          <div className="workspace-split chat-mode">
            <div className="pdf-viewer-container half desktop-only">
              <div className="pdf-toolbar">
                 <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Referensvy</span>
              </div>
              <div className="pdf-canvas">
                <div className="mock-pdf-page" style={{ transform: 'scale(0.8)', transformOrigin: 'top center' }}>
                  {document.id === 'd1' && MOCK_TEXT_EXTRACTION.d1[pdfPage] ? (
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

            <DocumentChat selectedDocument={document} setPdfPage={setPdfPage} />
          </div>
        )}

      </div>
    </div>
  );
}
