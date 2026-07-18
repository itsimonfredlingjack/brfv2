import React, { useState } from 'react';
import { Search, Sparkles, Clock, FileText, CheckCircle2, Loader2, Play } from 'lucide-react';

export default function Home({ setGlobalChatQuery, documents, openDocument }) {
  const [localSearch, setLocalSearch] = useState('');

  const handleSearchSubmit = () => {
    if (localSearch.trim()) {
      setGlobalChatQuery(localSearch);
    }
  };

  return (
    <div className="tab-content">
      <div className="dashboard-hero">
        <h1 className="hero-title">Välkommen till din BRF-arbetsyta</h1>
        <p className="hero-subtitle">Sök i stadgar, avtal och protokoll eller granska nya dokument.</p>
        
        <div className="search-bar-large">
          <Search className="search-icon" size={24} />
          <input 
            type="text" 
            placeholder="Sök dokument..." 
            value={localSearch}
            onChange={e => setLocalSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearchSubmit()}
          />
          <button className="search-submit-btn" onClick={handleSearchSubmit} aria-label="Sök med AI">
            <Sparkles size={18} className="desktop-only" />
            <Play size={18} className="mobile-only" fill="currentColor" />
          </button>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-card">
          <div className="card-header">
            <h2 className="card-title">Senaste dokument</h2>
            <button className="text-link">Visa alla</button>
          </div>
          <div className="recent-docs-list">
            {documents.slice(0, 3).map(doc => (
              <button 
                key={doc.id} 
                className="recent-doc-row interactive" 
                onClick={() => openDocument(doc.id)}
              >
                <div className="doc-icon"><FileText size={20} /></div>
                <div className="doc-info">
                  <span className="doc-name truncate">{doc.name}</span>
                  <span className="doc-date"><Clock size={12}/> {doc.date}</span>
                </div>
                <div className="doc-status-col desktop-only">
                  {doc.status === 'Färdigbehandlad' ? (
                    <span className="status-badge ok"><CheckCircle2 size={12}/> Bearbetad</span>
                  ) : (
                    <span className="status-badge muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="dashboard-card">
          <div className="card-header">
            <h2 className="card-title">Att göra</h2>
          </div>
          <div className="todo-list">
             <button className="todo-item warning interactive" onClick={() => {/* Filter to needs review */}}>
                <span className="todo-count">2</span>
                <span className="todo-text">Dokument väntar på kvalitetskontroll</span>
             </button>
             <button className="todo-item interactive" onClick={() => {/* Filter to bevakningar */}}>
                <span className="todo-count">1</span>
                <span className="todo-text">Aktiv bevakning förfaller inom 30 dagar</span>
             </button>
          </div>
        </div>
      </div>
    </div>
  );
}
