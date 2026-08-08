import React from 'react';
import { createRoot } from 'react-dom/client';
import AppNavigation from './components/AppNavigation';
import Watches from './components/Watches';
import { watchesApi } from './api';
import './theme.css';
import './App.css';

/**
 * Visual harness for Bevakningar — design audit, not a product route.
 * Opens via visual-bevakningar.html under Vite. `?empty=1` renders the
 * unified empty state (nothing watched or proposed yet).
 */

const EMPTY_MODE = new URLSearchParams(window.location.search).has('empty');

const CIT = { document_name: 'Hissavtal 2024–2028.pdf', page: 4, quote: 'Avtalet löper till och med den 31 december 2026.', approximate: false };

const BOARD = {
  today: '2026-08-08',
  bucketLabels: { overdue: 'Försenat', soon: 'Snart', later: 'Längre fram', recurring: 'Återkommande' },
  buckets: {
    overdue: [
      {
        id: 'w1', title: 'Säga upp städavtal i tid', kind_label: 'Uppsägningsfrist', status_label: 'Bevakas',
        due_date: '2026-08-01', derived_due_date: '2026-08-01', days_left: -7,
        responsible: 'Eva Ström', remind_at: '2026-07-25', remind_lead_days: 7, recurrence: 'none',
        source_document_name: 'Städavtal 2025.pdf', derivation: 'Uppsägning senast 3 månader före avtalstidens utgång (2026-11-01).',
        citations: [CIT], decision_note: '',
      },
    ],
    soon: [
      {
        id: 'w2', title: 'OVK-besiktning ska vara genomförd', kind_label: 'Myndighetskrav', status_label: 'Bevakas',
        due_date: '2026-09-15', derived_due_date: '2026-09-15', days_left: 38,
        responsible: 'Karim Holm', remind_at: '2026-09-01', remind_lead_days: 14, recurrence: 'none',
        source_document_name: 'OVK-protokoll 2023.pdf', derivation: 'Nästa besiktning inom 3 år från föregående (2023-09-15).',
        citations: [CIT], decision_note: '',
      },
    ],
    later: [
      {
        id: 'w3', title: 'Hissavtal löper ut', kind_label: 'Avtalstid', status_label: 'Bevakas',
        due_date: '2026-12-31', derived_due_date: '2026-12-31', days_left: 145,
        responsible: '', remind_at: '2026-11-30', remind_lead_days: 30, recurrence: 'none',
        source_document_name: 'Hissavtal 2024–2028.pdf', derivation: 'Avtalet gäller till och med den 31 december 2026.',
        citations: [CIT], decision_note: '',
      },
    ],
    recurring: [
      {
        id: 'w4', title: 'Årlig brandskyddskontroll', kind_label: 'Återkommande kontroll', status_label: 'Bevakas',
        due_date: '2027-03-01', derived_due_date: '2027-03-01', days_left: 205,
        responsible: 'Eva Ström', remind_at: '2027-02-01', remind_lead_days: 28, recurrence: 'yearly', next_due_after: '2028-03-01',
        source_document_name: 'Brandskyddsavtal.pdf', derivation: 'Kontroll varje år enligt avtalets punkt 4.',
        citations: [CIT], decision_note: '',
      },
    ],
  },
  proposed: EMPTY_MODE ? [] : [
    {
      id: 'p1', title: 'Besiktning av lekplats', kind_label: 'Säkerhetskontroll', due_date: '2026-10-01',
      derived_due_date: '2026-10-01', responsible: '', remind_lead_days: 14,
      source_document_name: 'Lekplatsbesiktning 2025.pdf', derivation: 'Årlig kontroll enligt föregående protokolls rekommendation.',
      citations: [CIT],
    },
  ],
  unresolved: EMPTY_MODE ? [] : [
    {
      id: 'u1', what: 'Garantitid för fasadrenovering', why: 'Villkoret anger "5 år från slutbesiktning", men inget slutbesiktningsdatum finns i arkivet.',
      source_document_name: 'Entreprenadavtal fasad.pdf', citations: [CIT],
    },
  ],
  settled: [],
};

watchesApi.board = async () => (EMPTY_MODE
  ? { ...BOARD, buckets: { overdue: [], soon: [], later: [], recurring: [] } }
  : BOARD);
watchesApi.decide = async () => ({ watch: { due_date: '2026-08-08', responsible: 'Eva Ström' } });
watchesApi.remove = async () => ({});
watchesApi.scan = async () => ({ documentsRead: 12, proposed: [] });

function Shell() {
  return (
    <div className="app-shell">
      <AppNavigation
        navigationVisible
        mobileMenuOpen={false}
        onToggleMobileMenu={() => {}}
        onCloseMobileMenu={() => {}}
        currentTab="watches"
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
            <Watches brfId="brf-a" isAdmin />
          </div>
        </main>
      </AppNavigation>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Shell />);
