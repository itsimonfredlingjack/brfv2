import React from 'react';
import { createRoot } from 'react-dom/client';
import AppNavigation from './components/AppNavigation';
import Tasks from './components/Tasks';
import { tasksApi } from './api';
import './theme.css';
import './App.css';

/**
 * Visual harness for Uppgifter — design audit, not a product route.
 * Opens via visual-uppgifter.html under Vite. `?empty=1` renders the
 * unified empty state (no active work yet).
 */

const EMPTY_MODE = new URLSearchParams(window.location.search).has('empty');

const CIT = { document_name: 'Städavtal 2025.pdf', page: 2, quote: 'Uppsägning ska ske senast 3 månader före avtalstidens utgång.', approximate: false };

function task({
  id, title, status, statusLabel, overdue = false, responsible, dueDate, daysLeft,
  originKind, originLabel, description, sourceDoc, createdBy, createdAt,
}) {
  return {
    id, title, status, status_label: statusLabel, overdue, responsible,
    due_date: dueDate, days_left: daysLeft, description,
    origin: { kind_label: originKind, label: originLabel },
    source_document_name: sourceDoc, created_by: createdBy, created_at: createdAt,
    citations: sourceDoc ? [CIT] : [], activity: [], last_activity_at: createdAt,
  };
}

const ACTIVE = [
  task({
    id: 't1', title: 'Ring Hisspartner om utryckningen 12 juli', status: 'in_progress', statusLabel: 'Pågår',
    overdue: true, responsible: 'Eva Ström', dueDate: '2026-08-06', daysLeft: -2,
    originKind: 'Faktura', originLabel: 'Hisspartner Väst AB — 4521', createdBy: 'Eva Ström', createdAt: '2026-08-05T13:21:00+02:00',
  }),
  task({
    id: 't2', title: 'Säga upp städavtalet innan fristen', status: 'open', statusLabel: 'Öppen',
    overdue: false, responsible: 'Karim Holm', dueDate: '2026-08-20', daysLeft: 12,
    originKind: 'Bevakning', originLabel: 'Uppsägningsfrist städavtal', sourceDoc: 'Städavtal 2025.pdf',
    createdBy: 'Karim Holm', createdAt: '2026-08-01T10:00:00+02:00',
  }),
  task({
    id: 't3', title: 'Svara medlem om jourtid för snöröjning', status: 'open', statusLabel: 'Öppen',
    overdue: false, responsible: '', dueDate: null, daysLeft: null,
    originKind: 'Post', originLabel: 'Fråga från medlem', createdBy: 'Anna Lindqvist', createdAt: '2026-08-02T09:15:00+02:00',
  }),
];

tasksApi.list = async () => ({
  today: '2026-08-08',
  statusLabels: { open: 'Öppen', in_progress: 'Pågår', done: 'Klar', blocked: 'Blockerad', cancelled: 'Avbruten' },
  active: EMPTY_MODE ? [] : ACTIVE,
  done: [],
  cancelled: [],
  counts: EMPTY_MODE
    ? { active: 0, overdue: 0, unassigned: 0 }
    : { active: 3, overdue: 1, unassigned: 1 },
});
tasksApi.update = async () => ({ title: 'Uppgift', status_label: 'Öppen', responsible: '', due_date: null });
tasksApi.comment = async () => ({});

function Shell() {
  return (
    <div className="app-shell">
      <AppNavigation
        navigationVisible
        mobileMenuOpen={false}
        onToggleMobileMenu={() => {}}
        onCloseMobileMenu={() => {}}
        currentTab="tasks"
        onNavigate={() => {}}
        desktopState={{ mode: 'desktop' }}
        activeMembership={{ role: 'admin' }}
        activeBrfId="brf-a"
        activeBrfName="Brf Gjutformen 12"
        memberships={[{ brf_id: 'brf-a', name: 'Brf Gjutformen 12', role: 'admin' }]}
        onSwitchTenant={() => {}}
        user={{ name: 'Anna Lindqvist', email: 'anna@gjutformen12.example' }}
        onOpenDesktopSettings={() => {}}
        onLogout={() => {}}
      >
        <main className="main-content">
          <div className="tab-content tab-content--wide">
            <Tasks brfId="brf-a" isAdmin />
          </div>
        </main>
      </AppNavigation>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Shell />);
