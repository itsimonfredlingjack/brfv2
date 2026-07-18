import React, { useState, useEffect, useRef } from 'react';
import { Home as HomeIcon, FileText, Settings, Menu, Sparkles, X } from 'lucide-react';
import './App.css';

import { MOCK_DOCUMENTS, MOCK_BEVAKNINGAR } from './data/MockData';
import Home from './components/Home';
import DocumentsOverview from './components/DocumentsOverview';
import DocumentWorkspace from './components/DocumentWorkspace';
import GlobalChat from './components/GlobalChat';
import SettingsPlaceholder from './components/SettingsPlaceholder';
import MockToast from './components/MockToast';

function App() {
  const [currentTab, setCurrentTab] = useState('home');
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState(null); // { message, type }
  
  // Local state for honest mock interactions
  const [documents, setDocuments] = useState(MOCK_DOCUMENTS);
  const [bevakningar, setBevakningar] = useState(MOCK_BEVAKNINGAR);

  const [globalChatQuery, setGlobalChatQuery] = useState('');

  const menuRef = useRef(null);
  const menuBtnRef = useRef(null);

  // Close menu on escape or click outside
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && mobileMenuOpen) {
        closeMobileMenu();
      }
    };
    const handleClickOutside = (e) => {
      if (mobileMenuOpen && menuRef.current && !menuRef.current.contains(e.target) && !menuBtnRef.current.contains(e.target)) {
        closeMobileMenu();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [mobileMenuOpen]);

  // Trap focus when mobile menu is open
  useEffect(() => {
    if (mobileMenuOpen && menuRef.current) {
      const focusable = menuRef.current.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusable.length) {
        focusable[0].focus();
      }
      document.body.style.overflow = 'hidden'; // prevent scrolling
    } else {
      document.body.style.overflow = '';
    }
  }, [mobileMenuOpen]);

  const closeMobileMenu = () => {
    setMobileMenuOpen(false);
    if (menuBtnRef.current) {
      menuBtnRef.current.focus();
    }
  };

  const showToast = (message, type = 'success') => {
    setToastMessage({ message, type });
  };

  const navigateTo = (tab) => {
    setCurrentTab(tab);
    setSelectedDocumentId(null);
    closeMobileMenu();
  };

  const openDocument = (id) => {
    setSelectedDocumentId(id);
    setCurrentTab('docs');
    closeMobileMenu();
  };

  const handleGlobalChatQuery = (query) => {
    setGlobalChatQuery(query);
    navigateTo('ai');
  };

  const handleApprovePage = (docId) => {
    setDocuments(prev => prev.map(d => d.id === docId ? { ...d, qa: 'Granskad' } : d));
  };

  const handleMarkBevakningDone = (bevId) => {
    setBevakningar(prev => prev.map(b => b.id === bevId ? { ...b, done: true } : b));
    showToast('Bevakning markerad som klar.');
  };

  const selectedDocument = documents.find(d => d.id === selectedDocumentId);
  const docBevakningar = bevakningar.filter(b => b.docId === selectedDocumentId);

  return (
    <div className="app-shell">
      {/* Mobile Header */}
      <header className="mobile-header mobile-only">
        <div className="mobile-header-content">
          <button 
            ref={menuBtnRef}
            className="icon-action-btn" 
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Öppna meny"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav-drawer"
          >
            <Menu size={24} />
          </button>
          <div className="logo">
            <div className="logo-box">B</div>
            <span>BRFv2 Mockup</span>
          </div>
          <div style={{ width: 24 }}></div>
        </div>
      </header>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div className="mobile-drawer-overlay mobile-only" aria-hidden="true"></div>
      )}

      {/* Sidebar Navigation */}
      <aside 
        id="mobile-nav-drawer"
        ref={menuRef}
        className={`sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}
        aria-hidden={!mobileMenuOpen && window.innerWidth <= 768}
      >
        <div className="logo desktop-only">
          <div className="logo-box">B</div>
          <span>BRFv2 Mockup</span>
        </div>

        {mobileMenuOpen && (
          <button className="icon-action-btn mobile-close-btn" onClick={closeMobileMenu} aria-label="Stäng meny">
            <X size={24} />
          </button>
        )}

        <nav className="nav-menu">
          <div className="nav-group">
            <span className="nav-label">ARBETSYTA</span>
            <button className={`nav-item ${currentTab === 'home' && !selectedDocumentId ? 'active' : ''}`} onClick={() => navigateTo('home')}>
              <HomeIcon size={18} /> Hem
            </button>
            <button className={`nav-item ${currentTab === 'docs' ? 'active' : ''}`} onClick={() => navigateTo('docs')}>
              <FileText size={18} /> Dokument
              {documents.filter(d => d.qa === 'Behöver granskas').length > 0 && (
                <span className="nav-badge warning">{documents.filter(d => d.qa === 'Behöver granskas').length}</span>
              )}
            </button>
            <button className={`nav-item ${currentTab === 'ai' ? 'active' : ''}`} onClick={() => navigateTo('ai')}>
              <Sparkles size={18} /> AI-chatt
            </button>
          </div>

          <div className="nav-group">
            <span className="nav-label">ADMINISTRATION</span>
            <button className={`nav-item ${currentTab === 'settings' ? 'active' : ''}`} onClick={() => navigateTo('settings')}>
              <Settings size={18} /> Inställningar
            </button>
          </div>
        </nav>

        <div className="account-info">
          <div className="avatar">SO</div>
          <div className="account-text">
            <div className="name">Simon Ordförande</div>
            <div className="email">Brf Gjutformen 12</div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className={`main-content ${selectedDocumentId ? 'workspace-active' : ''}`}>
        {!selectedDocumentId && currentTab === 'home' && (
          <Home 
            setGlobalChatQuery={handleGlobalChatQuery} 
            documents={documents}
            openDocument={openDocument} 
          />
        )}
        {!selectedDocumentId && currentTab === 'docs' && (
          <DocumentsOverview 
            documents={documents} 
            openDocument={openDocument}
            showToast={showToast}
          />
        )}
        {!selectedDocumentId && currentTab === 'ai' && (
          <GlobalChat 
            openDocument={openDocument} 
            initialQuery={globalChatQuery}
          />
        )}
        {!selectedDocumentId && currentTab === 'settings' && (
          <SettingsPlaceholder />
        )}

        {selectedDocumentId && selectedDocument && (
          <DocumentWorkspace 
            document={selectedDocument}
            bevakningar={docBevakningar}
            closeDocument={() => setSelectedDocumentId(null)}
            onApprovePage={handleApprovePage}
            onMarkBevakningDone={handleMarkBevakningDone}
            showToast={showToast}
          />
        )}
      </main>

      {toastMessage && (
        <MockToast 
          message={toastMessage.message} 
          type={toastMessage.type} 
          onClose={() => setToastMessage(null)} 
        />
      )}
    </div>
  );
}

export default App;
