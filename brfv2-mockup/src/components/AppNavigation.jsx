import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  LogOut,
  Menu,
  Settings,
  X,
} from 'lucide-react';
import { NAV_ITEMS, NAV_GROUPS } from '../appWorkspaces';
import TraffMark from './TraffMark';

const roleLabel = (role) => (role === 'admin' ? 'Admin' : 'Medlem');

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

export default function AppNavigation({
  children,
  navigationVisible,
  mobileMenuOpen,
  onToggleMobileMenu,
  onCloseMobileMenu,
  currentTab,
  onNavigate,
  desktopState,
  activeMembership,
  activeBrfId,
  activeBrfName,
  memberships,
  onSwitchTenant,
  user,
  onOpenDesktopSettings,
  onLogout,
}) {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const [showUserMenu, setShowUserMenu] = useState(false);
  const mobileMenuBtnRef = React.useRef(null);
  const sidebarRef = React.useRef(null);

  React.useEffect(() => {
    if (!isMobile && mobileMenuOpen) {
      onCloseMobileMenu();
    }
  }, [isMobile, mobileMenuOpen, onCloseMobileMenu]);

  React.useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isMobile || !mobileMenuOpen) return;
      if (e.key === 'Escape') {
        onCloseMobileMenu();
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
          } else if (document.activeElement === lastElement) {
            firstElement.focus();
            e.preventDefault();
          }
        }
      }
    };
    if (isMobile && mobileMenuOpen) {
      document.addEventListener('keydown', handleKeyDown);
      setTimeout(() => {
        const firstFocusable = sidebarRef.current?.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (firstFocusable) firstFocusable.focus();
      }, 50);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isMobile, mobileMenuOpen, onCloseMobileMenu]);

  const userInitials = (user?.name || '')
    .split(' ')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase())
    .slice(0, 2)
    .join('') || '?';

  const selectTab = (tab) => {
    onNavigate(tab);
    onCloseMobileMenu();
  };

  // A group label only prints when the group has at least one visible item —
  // on clients where the desktop workspaces are hidden, their groups vanish
  // with them rather than heading nothing.
  const visibleNavRows = NAV_ITEMS
    .filter((item) => !item.desktopOnly || desktopState)
    .map((item, index, visible) => ({
      ...item,
      groupLabel:
        item.group !== visible[index - 1]?.group
          ? NAV_GROUPS.find((g) => g.id === item.group)?.label ?? null
          : null,
    }));

  return (
    <>
      {navigationVisible && (
        <header className="mobile-top-nav">
          <div className="sidebar-brand-inline">
            <TraffMark size={18} />
            <div className="logo">
              <span className="logo-name">Träff</span>
            </div>
          </div>
          <button ref={mobileMenuBtnRef} className="icon-action-btn mobile-menu-btn" onClick={onToggleMobileMenu} aria-label="Meny" aria-expanded={mobileMenuOpen}>
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>
      )}

      <div className="main-layout">
        {navigationVisible && isMobile && mobileMenuOpen && (
          <div className="sidebar-backdrop" onClick={onCloseMobileMenu} aria-hidden="true" />
        )}

        {navigationVisible && (
          <nav
            ref={sidebarRef}
            className={`sidebar ${mobileMenuOpen ? 'open' : ''}`}
            aria-hidden={isMobile && !mobileMenuOpen ? 'true' : undefined}
            inert={isMobile && !mobileMenuOpen ? true : undefined}
          >
            <div className="sidebar-brand desktop-only">
              {/* Sized to the wordmark's cap, not to the block beside it. */}
              <TraffMark size={19} />
              <div className="logo">
                <span className="logo-name">Träff</span>
                <span className="logo-qualifier">BRF &amp; styrelse</span>
              </div>
            </div>

            <div className="sidebar-menu">
              {visibleNavRows.map(({ id, label, icon: Icon, groupLabel }) => (
                <React.Fragment key={id}>
                  {groupLabel && <div className="sidebar-section-label">{groupLabel}</div>}
                  <button
                    className={`nav-item ${currentTab === id ? 'active' : ''}`}
                    onClick={() => selectTab(id)}
                    aria-current={currentTab === id ? 'page' : undefined}
                  >
                    <Icon size={16} /> <span className="nav-item-label">{label}</span>
                  </button>
                </React.Fragment>
              ))}
            </div>

            <div className="sidebar-footer">
              {activeMembership && (
                <div className={`active-brf-panel ${memberships.length > 1 ? 'switchable' : 'static'}`}>
                  <span className="active-brf-tile" aria-hidden="true">
                    {(activeBrfName || '?').replace(/^Brf\s+/i, '').charAt(0).toUpperCase()}
                  </span>
                  <span className="active-brf-body">
                    <span className="active-brf-eyebrow">Aktiv förening</span>
                    {memberships.length > 1 ? (
                      <span className="active-brf-select-wrap">
                        <select
                          id="tenant-select"
                          className="active-brf-select"
                          value={String(activeBrfId ?? '')}
                          onChange={(e) => onSwitchTenant(e.target.value)}
                          aria-label="Byt aktiv förening"
                          title="Byt aktiv förening"
                        >
                          {memberships.map((membership) => (
                            <option key={membership.brf_id} value={String(membership.brf_id)}>{membership.name}</option>
                          ))}
                        </select>
                        <ChevronDown size={13} className="active-brf-select-chevron" aria-hidden="true" />
                      </span>
                    ) : (
                      <span className="active-brf-name-static" title={activeBrfName}>{activeBrfName}</span>
                    )}
                    {/* The role is a sentence about the signed-in person, not a
                        chip floating beside a name with nothing to attach to. */}
                    <span className={`active-brf-role ${activeMembership.role}`}>
                      {roleLabel(activeMembership.role)}
                    </span>
                  </span>
                </div>
              )}

              {showUserMenu && (
                <div className="user-menu-popover glass-panel">
                  {desktopState && (
                    <div
                      className="user-menu-item"
                      role="button"
                      tabIndex={0}
                      onClick={() => { onOpenDesktopSettings(); setShowUserMenu(false); }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onOpenDesktopSettings();
                          setShowUserMenu(false);
                        }
                      }}
                    >
                      <Settings size={16} /> Appinställningar
                    </div>
                  )}
                  <div className="user-menu-item text-danger" onClick={onLogout}><LogOut size={16} /> Logga ut</div>
                </div>
              )}

              <div className="user-profile" onClick={() => setShowUserMenu(!showUserMenu)}>
                <div className="user-avatar">{userInitials}</div>
                <div className="user-info">
                  <span className="user-name">{user?.name || user?.email}</span>
                  <span className="user-email">{user?.email}</span>
                </div>
                <ChevronUp size={14} color="var(--muted-foreground)" style={{ marginLeft: 'auto', flexShrink: 0, transform: showUserMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </div>
            </div>
          </nav>
        )}

        {children}
      </div>
    </>
  );
}
