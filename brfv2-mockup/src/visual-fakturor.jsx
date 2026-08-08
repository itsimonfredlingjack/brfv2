import React from 'react';
import { createRoot } from 'react-dom/client';
import AppNavigation from './components/AppNavigation';
import Invoices from './components/Invoices';
import { integrationsApi, invoicesApi, tasksApi } from './api';
import './theme.css';
import './App.css';

/**
 * Visual harness for the Fakturor depth pass.
 * Not a product route — opens via visual-fakturor.html under Vite.
 * `?empty=1` renders the unified empty state (nothing read in yet).
 *
 * The shell is the REAL AppNavigation (not a hand copy) so sidebar and
 * page-chrome changes are exercised by the screenshots.
 */

const EMPTY_MODE = new URLSearchParams(window.location.search).has('empty');

function queueRow({
  id, supplier, number, invoiceDate, dueDate, amount, overdue = false,
  signal, reviewStatus, reviewLabel, responsible = null, kinds, activity,
}) {
  return {
    id,
    case_key: `fixture:${id}`,
    supplier_name: supplier,
    supplier_ref: `LEV-${number}`,
    invoice_number: number,
    invoice_date: invoiceDate,
    due_date: dueDate,
    total_amount: amount,
    currency: 'SEK',
    open: true,
    overdue,
    signals: signal ? [signal] : [],
    top_signal: signal || null,
    review_status: reviewStatus,
    review_status_label: reviewLabel,
    source_status_label: 'Bokförd i ekonomisystemet',
    responsible,
    observation_kinds: kinds,
    observations: kinds.map((kind, i) => ({
      kind,
      external_ref: `${number}-${i}`,
    })),
    last_activity_at: activity,
  };
}

const CASES = [
  queueRow({
    id: 'case-hisspartner',
    supplier: 'Hisspartner Väst AB',
    number: '4521',
    invoiceDate: '2026-07-01',
    dueDate: '2026-07-31',
    amount: '12400.00',
    overdue: true,
    signal: { kind: 'overdue', label: 'Förfallen', severity: 'warning', detail: 'Förfallodagen passerade för 8 dagar sedan.' },
    reviewStatus: 'new',
    reviewLabel: 'Ny',
    kinds: ['accounting_snapshot', 'email'],
    activity: '2026-08-04T09:12:00+02:00',
  }),
  queueRow({
    id: 'case-stad',
    supplier: 'Städ & Service Mälardalen AB',
    number: '1180',
    invoiceDate: '2026-07-15',
    dueDate: '2026-08-15',
    amount: '8750.00',
    signal: { kind: 'price_change', label: 'Pris avviker', severity: 'warning', detail: '+12 % mot avtalad månadskostnad.' },
    reviewStatus: 'in_review',
    reviewLabel: 'Pågår',
    responsible: 'Karim Holm',
    kinds: ['accounting_snapshot'],
    activity: '2026-08-03T14:20:00+02:00',
  }),
  queueRow({
    id: 'case-elkontoret',
    supplier: 'El-kontoret i Västerås AB',
    number: '22-104',
    invoiceDate: '2026-07-28',
    dueDate: '2026-08-28',
    amount: '23150.00',
    signal: { kind: 'possible_duplicate', label: 'Möjlig dubblett', severity: 'attention', detail: 'Samma belopp och datum som 22-097.' },
    reviewStatus: 'new',
    reviewLabel: 'Ny',
    kinds: ['accounting_snapshot', 'document'],
    activity: '2026-08-02T11:05:00+02:00',
  }),
  queueRow({
    id: 'case-bredband',
    supplier: 'Bredband2 Sverige AB',
    number: 'BB-88231',
    invoiceDate: '2026-07-20',
    dueDate: '2026-08-20',
    amount: '1895.00',
    signal: { kind: 'no_deviation_found', label: 'Ingen avvikelse', severity: 'info', detail: 'Belopp och villkor stämmer mot avtalet.' },
    reviewStatus: 'in_review',
    reviewLabel: 'Pågår',
    responsible: 'Eva Ström',
    kinds: ['accounting_snapshot'],
    activity: '2026-08-01T16:40:00+02:00',
  }),
  queueRow({
    id: 'case-rorvarme',
    supplier: 'Rör & Värme i Stockholm AB',
    number: '7719',
    invoiceDate: '2026-08-01',
    dueDate: '2026-09-02',
    amount: '45200.00',
    signal: { kind: 'missing_contract', label: 'Avtal saknas', severity: 'warning', detail: 'Inget avtal matchar leverantören.' },
    reviewStatus: 'new',
    reviewLabel: 'Ny',
    kinds: ['accounting_snapshot', 'email'],
    activity: '2026-08-05T08:30:00+02:00',
  }),
];

const LABELS = {
  reviewStatus: {
    new: 'Ny',
    in_review: 'Pågår',
    waiting: 'Väntar på svar',
    done: 'Klar',
  },
  reviewStatusCaveats: {
    new: '”Ny” betyder att ingen i föreningen tagit ställning ännu. Det säger inget om fakturans innehåll.',
    in_review: '”Pågår” är föreningens egen arbetsmarkering — ingenting har skickats till ekonomisystemet.',
    waiting: '”Väntar på svar” betyder att föreningen ställt en fråga och inväntar svar innan ställningstagande.',
    done: '”Klar” betyder att föreningen är färdig med sin granskning. Ekonomisystemets status är oförändrad.',
  },
  engineVersion: '2026.08',
};

const CASE_DETAIL = {
  case: {
    ...CASES[0],
    identity_basis: 'Samma fakturanummer och leverantör i ekonomisystemet och i mejlet den kom med.',
    vat_amount: '2480.00',
    period_start: '2026-07-01',
    period_end: '2026-07-31',
    source_status: { retrieved_at: '2026-08-04T09:10:00+02:00' },
    review_status_caveat: LABELS.reviewStatusCaveats.new,
    analysis_outdated: false,
    analysis_engine_version: '2026.08',
    analysis_run_id: 'run-1',
    comments: [
      { id: 'c1', note: 'Ringde Hisspartner 5/8 — utryckningen den 12 juli var ett larm som visade sig vara ett test. De skickar kredit.', by: 'Eva Ström', at: '2026-08-05T13:20:00+02:00' },
    ],
    timeline: [
      { id: 't1', kind: 'import', kind_label: 'Inläsning', summary: 'Faktura 4521 lästes in ur ekonomisystemet', note: '', by: 'systemet', at: '2026-08-01T09:10:00+02:00', human: false },
      { id: 't2', kind: 'analysis', kind_label: 'Granskning', summary: 'Granskning klar: en signal (förfallen)', note: 'Regelversion 2026.08', by: 'systemet', at: '2026-08-01T09:10:04+02:00', human: false },
      { id: 't3', kind: 'comment', kind_label: 'Kommentar', summary: 'Eva Ström kommenterade ärendet', note: 'Utryckningen var ett test, kredit utlovad.', by: 'Eva Ström', at: '2026-08-05T13:20:00+02:00', human: true },
      { id: 't4', kind: 'status', kind_label: 'Ansvarig', summary: 'Ansvarig satt till Eva Ström', note: '', by: 'Eva Ström', at: '2026-08-05T13:21:00+02:00', human: true },
    ],
  },
  invoice: {
    lines: [
      { description: 'Periodiskt underhåll, juli', quantity: 1, unit_price: '8500.00', amount: '8500.00' },
      { description: 'Akut utryckning 12 juli', quantity: 1, unit_price: '3900.00', amount: '3900.00' },
    ],
    retrieved_at: '2026-08-04T09:10:00+02:00',
    source_dataset: 'fixture',
    external_ref: '4521',
    content_sha256: '9f2c41aa07d24f3a8bb15c6e0d9f3a7c5e1b2d4a6f8c0e2a4b6d8f0a2c4e6a8c0e2a',
  },
  supplier: {
    supplier_name: 'Hisspartner Väst AB',
    invoice_count: 14,
    amount_low: '9800.00',
    amount_high: '14200.00',
    currency: 'SEK',
    org_numbers: ['556123-8890'],
    deviation_count: 1,
    responsibles: ['Eva Ström'],
    previous: [
      { id: 'case-hiss-juni', invoice_number: '4402', invoice_date: '2026-06-01', total_amount: '9800.00', currency: 'SEK', review_status_label: 'Klar' },
      { id: 'case-hiss-maj', invoice_number: '4288', invoice_date: '2026-05-01', total_amount: '9800.00', currency: 'SEK', review_status_label: 'Klar' },
    ],
    documents: [{ id: 'doc-hissavtal', name: 'Hissavtal 2024–2028.pdf' }],
    aliases: [],
  },
  labels: LABELS,
  tasks: [
    { id: 'task-1', title: 'Ring Hisspartner om utryckningen 12 juli', status_label: 'Öppen', responsible: 'Eva Ström', due_date: '2026-08-10' },
  ],
  sourceEvent: {
    origin: 'ekonomi@hisspartner.example',
    origin_display: 'Hisspartner Väst AB',
    subject: 'Faktura 4521 — hisservice juli',
    body_text: 'Hej,\n\nBifogat faktura för periodiskt underhåll samt en akut utryckning den 12 juli.\n\nVänliga hälsningar,\nHisspartner Ekonomi',
    occurred_at: '2026-08-01T08:55:00+02:00',
    received_at: '2026-08-01T08:55:00+02:00',
  },
  documents: [],
  analyses: [],
  findings: [],
};

invoicesApi.workspace = async () => ({
  cases: EMPTY_MODE ? [] : CASES,
  counts: EMPTY_MODE
    ? { open: 0, withSignal: 0, overdue: 0, unassigned: 0, amountOpen: '0.00' }
    : { open: 5, withSignal: 4, overdue: 1, unassigned: 3, amountOpen: '91395.00' },
  labels: LABELS,
  responsibles: ['Karim Holm', 'Eva Ström'],
  sources: ['fixture'],
});

invoicesApi.case = async () => CASE_DETAIL;
invoicesApi.importInvoice = async () => CASE_DETAIL.case;
invoicesApi.refresh = async () => ({ source: 'Syntetiskt underlag.' });
invoicesApi.update = async () => ({});
invoicesApi.comment = async () => ({});
invoicesApi.analysis = async () => ({ run: { replaced: [] } });

integrationsApi.connections = async () => ({ fortnox: { connection: { status: 'not_connected' } } });
integrationsApi.availableInvoices = async () => ({ invoices: [] });
integrationsApi.decideFinding = async () => ({});
integrationsApi.addSupplierAlias = async () => ({});
integrationsApi.deleteSupplierAlias = async () => ({});

tasksApi.forOrigin = async () => ({ tasks: [] });
tasksApi.create = async () => ({ task: { title: '', responsible: '' } });

function Shell() {
  return (
    <div className="app-shell">
      <div className="mock-banner-compact">
        <span className="mock-badge-inline">PILOT</span>
        Verifierad pilotslinga: förening, dokument, uppladdning, AI-svar, källor och PDF-markering använder den riktiga tjänsten. Sök, dokumentchatt, kvalitetskontroll och inställningar ingår inte i piloten.
      </div>
      <AppNavigation
        navigationVisible
        mobileMenuOpen={false}
        onToggleMobileMenu={() => {}}
        onCloseMobileMenu={() => {}}
        currentTab="invoices"
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
          <div className="tab-content">
            <Invoices brfId="brf-a" isAdmin />
          </div>
        </main>
      </AppNavigation>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Shell />);
