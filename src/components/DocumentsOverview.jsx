import React, { useState, useMemo } from 'react';
import { Upload, Filter, Search, FileText, CheckCircle2, Loader2, ArrowRight } from 'lucide-react';

export default function DocumentsOverview({ documents, openDocument, showToast }) {
  const [docFilter, setDocFilter] = useState('all');
  const [docsSearchQuery, setDocsSearchQuery] = useState('');

  const handleUploadMock = () => {
    showToast('Funktionen Ladda upp är inte tillgänglig i denna mockup.', 'error');
  };

  const filteredDocs = useMemo(() => {
    return documents.filter(d => {
      const q = docsSearchQuery.toLowerCase();
      if (q && !d.name.toLowerCase().includes(q)) return false;

      if (docFilter === 'all') return true;
      if (docFilter === 'needs_review') return d.qa === 'Behöver granskas';
      if (docFilter === 'has_bevakning') return d.bevakningar > 0;
      if (docFilter === 'processing') return d.status === 'Behandlas';
      if (docFilter === 'done') return d.status === 'Färdigbehandlad' && d.qa === 'Granskad';
      return true;
    });
  }, [documents, docFilter, docsSearchQuery]);

  const stats = useMemo(() => {
    return {
      all: documents.length,
      needs_review: documents.filter(d => d.qa === 'Behöver granskas').length,
      has_bevakning: documents.filter(d => d.bevakningar > 0).length,
      processing: documents.filter(d => d.status === 'Behandlas').length,
      done: documents.filter(d => d.status === 'Färdigbehandlad' && d.qa === 'Granskad').length,
    };
  }, [documents]);

  return (
    <div className="tab-content docs-overview">
      <div className="docs-header">
        <div className="docs-header-top">
          <h2>Dokument</h2>
          <button className="primary-action-btn" onClick={handleUploadMock}>
            <Upload size={16} /> <span className="action-label">Ladda upp dokument</span>
          </button>
        </div>

        <div className="docs-filters-container">
          <div className="docs-search-wrapper">
             <Search size={16} className="search-icon" />
             <input 
               type="text" 
               className="docs-search-input" 
               placeholder="Sök dokumentnamn..." 
               value={docsSearchQuery}
               onChange={(e) => setDocsSearchQuery(e.target.value)}
             />
             {docsSearchQuery && (
               <button className="clear-search-btn" onClick={() => setDocsSearchQuery('')} aria-label="Rensa sökning">✕</button>
             )}
          </div>
          <div className="docs-filter-pills">
             <button className={`filter-pill ${docFilter === 'all' ? 'active' : ''}`} onClick={() => setDocFilter('all')}>
               Alla <span className="count">{stats.all}</span>
             </button>
             <button className={`filter-pill ${docFilter === 'needs_review' ? 'active' : ''}`} onClick={() => setDocFilter('needs_review')}>
               Behöver granskas <span className="count warning">{stats.needs_review}</span>
             </button>
             <button className={`filter-pill ${docFilter === 'has_bevakning' ? 'active' : ''}`} onClick={() => setDocFilter('has_bevakning')}>
               Har bevakningar <span className="count">{stats.has_bevakning}</span>
             </button>
             <button className={`filter-pill ${docFilter === 'processing' ? 'active' : ''}`} onClick={() => setDocFilter('processing')}>
               Behandlas <span className="count">{stats.processing}</span>
             </button>
             <button className={`filter-pill ${docFilter === 'done' ? 'active' : ''}`} onClick={() => setDocFilter('done')}>
               Klara <span className="count ok">{stats.done}</span>
             </button>
          </div>
        </div>
      </div>

      <div className="docs-table-container">
        {filteredDocs.length === 0 ? (
          <div className="docs-empty-state">
             <Search size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
             <h3>Inga dokument matchar din sökning</h3>
             <p>Testa att justera filtren eller söka på något annat.</p>
             <button className="secondary-action-btn" onClick={() => { setDocsSearchQuery(''); setDocFilter('all'); }} style={{ marginTop: '16px' }}>
               Rensa sökning och filter
             </button>
          </div>
        ) : (
          <>
            <table className="docs-table desktop-only">
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>Dokumentnamn</th>
                  <th>Uppladdat</th>
                  <th>Systembearbetning</th>
                  <th>Kvalitetskontroll</th>
                  <th>Bevakningar</th>
                  <th style={{ width: '40px' }}><span className="sr-only">Åtgärd</span></th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map(doc => (
                  <tr key={doc.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FileText size={16} color="var(--text-secondary)" /> 
                        <button className="table-link-btn" onClick={() => openDocument(doc.id)}>{doc.name}</button>
                      </div>
                    </td>
                    <td>{doc.date}</td>
                    <td>
                      {doc.status === 'Färdigbehandlad' ? (
                        <span className="status-text muted" title="Färdigbehandlad"><CheckCircle2 size={14}/> Färdigbehandlad</span>
                      ) : (
                        <span className="status-badge muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                      )}
                    </td>
                    <td>
                      {doc.qa === 'Granskad' ? (
                        <span className="status-text ok" title="Granskad"><CheckCircle2 size={14}/> Granskad</span>
                      ) : (
                        <span className="status-badge warning">Behöver granskas</span>
                      )}
                    </td>
                    <td>
                       {doc.bevakningar > 0 ? (
                         <span style={{ fontWeight: '500', color: 'var(--text-primary)' }}>{doc.bevakningar} bevakningar</span>
                       ) : (
                         <span className="muted-text">Inga bevakningar</span>
                       )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                       <button className="icon-action-btn" onClick={() => openDocument(doc.id)} aria-label="Öppna dokument"><ArrowRight size={16} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="docs-mobile-list mobile-only">
               {filteredDocs.map(doc => (
                  <button key={doc.id} className="doc-mobile-card interactive" onClick={() => openDocument(doc.id)}>
                    <div className="doc-card-header">
                       <span className="doc-card-name">{doc.name}</span>
                       <ArrowRight size={16} color="var(--text-muted)" />
                    </div>
                    <div className="doc-card-date">{doc.date}</div>
                    <div className="doc-card-statuses">
                       {doc.status === 'Färdigbehandlad' ? (
                          <span className="status-badge ok-muted">System klar</span>
                       ) : (
                          <span className="status-badge muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                       )}
                       
                       {doc.qa === 'Granskad' ? (
                         <span className="status-badge ok">Granskad</span>
                       ) : (
                         <span className="status-badge warning">Granskning krävs</span>
                       )}

                       {doc.bevakningar > 0 && (
                         <span className="status-badge neutral">{doc.bevakningar} bevakningar</span>
                       )}
                    </div>
                  </button>
               ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
