import React from 'react';
import { createRoot } from 'react-dom/client';
import AppNavigation from './components/AppNavigation';
import Integrations from './components/Integrations';
import { intakeApi, integrationsApi } from './api';
import './theme.css';
import './App.css';

/**
 * Visual harness for Inkommande — design audit, not a product route.
 * Opens via visual-inkommande.html under Vite. `?empty=1` renders the
 * unified empty state (connected mailbox, nothing in the queue).
 *
 * Mounts the real `Integrations` component (not a hand-copied shell) so
 * header/tab/masthead changes there are actually exercised by the screenshot.
 */

const EMPTY_MODE = new URLSearchParams(window.location.search).has('empty');

function eventStub({
  id, subject, origin, originDisplay, body, category, categoryLabel, awaiting = false, at,
}) {
  return {
    id,
    tenant_id: 'brf-a',
    source_type: 'email',
    received_at: at,
    occurred_at: at,
    external_ref: `<${id}@example>`,
    content_sha256: id.padEnd(64, '0'),
    provenance: {
      method: 'eml-upload',
      adapter: 'manual',
      origin_filename: `${id}.eml`,
      origin_bytes: 1200,
      imported_by: 'user-1',
      imported_at: at,
    },
    origin,
    origin_display: originDisplay,
    recipients: ['styrelsen@gjutformen12.example'],
    subject,
    body_text: body,
    attachments: [],
    import_status: 'imported',
    review_status: 'open',
    linked_document_ids: [],
    suggested_document_ids: [],
    triage: {
      category,
      category_label: categoryLabel,
      headline: `${categoryLabel} — ${subject}`,
      why_it_matters: 'Behöver en mänsklig bedömning innan något bevaras.',
      action_hint: 'Läs meddelandet och bestäm vad som ska hända.',
      awaiting_reply: awaiting,
      contains_decision: false,
      supplier_name: originDisplay,
      signals: [],
      related: [],
      suggested_by: 'regelmotor',
      uncertainty: '',
      created_at: at,
    },
    triage_confirmation: null,
    resolution: null,
    preserved_document_id: null,
    preserved_by: null,
    preserved_at: null,
    preservation_note: null,
    in_reply_to: null,
    references: [],
    thread_key: `subject:${subject.toLowerCase()}`,
    thread_subject: subject,
    decided_by: null,
    decided_at: null,
    decision_note: null,
  };
}

const THREADS = [
  {
    key: 't1',
    subject: 'Angående ert avtal om vinterväghållning och snöröjning 2025/2026',
    category: 'contract_or_quote',
    category_label: 'Avtal eller offert',
    category_confirmed: false,
    latest_sender: 'kundtjanst@fastighetsservice.example',
    latest_sender_display: 'Fastighetsservice & Trädgårdsentreprenad i Mälardalen Aktiebolag',
    first_at: '2026-08-04T09:12:00+02:00',
    latest_at: '2026-08-04T09:12:00+02:00',
    message_count: 1,
    attachment_count: 0,
    awaiting_reply: false,
    open_count: 1,
    resolved: false,
    headline: 'Avtal eller offert — vinterväghållning',
    why_it_matters: 'Avtalsfrågor bör behållas om de påverkar föreningen. Ett avtal som bara finns i inkorgen är svårt att belägga senare.',
    action_hint: 'Läs och bestäm om posten ska bevaras.',
    supplier_name: 'Fastighetsservice & Trädgårdsentreprenad i Mälardalen Aktiebolag',
    suggested_by: 'regelmotor',
    uncertainty: '',
    signals: [
      { kind: 'date', value: '2025-11-01', source: 'body', quote: 'avtalet om vinterväghållning och snöröjning för säsongen 2025/2026' },
      { kind: 'supplier', value: 'Fastighetsservice & Trädgårdsentreprenad i Mälardalen Aktiebolag', source: 'from', quote: 'kundtjanst@fastighetsservice.example' },
    ],
    related: [{ kind: 'document', ref_id: 'doc-snorojning', label: 'Snöröjningsavtal 2025.pdf', basis: 'föreslaget av sökningen på ämne och avsändare' }],
    events: [eventStub({
      id: 'ev1', subject: 'Angående ert avtal om vinterväghållning och snöröjning 2025/2026',
      origin: 'kundtjanst@fastighetsservice.example', originDisplay: 'Fastighetsservice & Trädgårdsentreprenad i Mälardalen Aktiebolag',
      body: 'Hej styrelsen,\n\nVi återkommer gällande avtalet om vinterväghållning och snöröjning för säsongen 2025/2026. Vänligen återkom med eventuella synpunkter.\n\nMed vänlig hälsning,\nKundtjänst',
      category: 'contract_or_quote', categoryLabel: 'Avtal eller offert', at: '2026-08-04T09:12:00+02:00',
    })],
  },
  {
    key: 't2',
    subject: 'Faktura 4521 — hisservice augusti',
    category: 'invoice',
    category_label: 'Faktura',
    category_confirmed: false,
    latest_sender: 'ekonomi@hisspartner.example',
    latest_sender_display: 'Hisspartner Väst AB',
    first_at: '2026-08-03T14:20:00+02:00',
    latest_at: '2026-08-03T14:20:00+02:00',
    message_count: 1,
    attachment_count: 1,
    awaiting_reply: false,
    open_count: 1,
    resolved: false,
    headline: 'Faktura — hisservice',
    why_it_matters: 'Fakturor granskas innan de blir underlag.',
    action_hint: 'Ta ställning till fakturan.',
    supplier_name: 'Hisspartner Väst AB',
    suggested_by: 'regelmotor',
    uncertainty: '',
    signals: [],
    related: [],
    events: [eventStub({
      id: 'ev2', subject: 'Faktura 4521 — hisservice augusti', origin: 'ekonomi@hisspartner.example', originDisplay: 'Hisspartner Väst AB',
      body: 'Hej,\n\nBifogat faktura för periodiskt underhåll.\n\nVänliga hälsningar', category: 'invoice', categoryLabel: 'Faktura', at: '2026-08-03T14:20:00+02:00',
    })],
  },
  {
    key: 't3',
    subject: 'Påminnelse: OVK-besiktning maj 2026',
    category: 'authority_or_manager',
    category_label: 'Myndighet eller förvaltare',
    category_confirmed: false,
    latest_sender: 'info@driftia.example',
    latest_sender_display: 'Driftia Fastighetsservice AB',
    first_at: '2026-08-02T11:05:00+02:00',
    latest_at: '2026-08-02T11:05:00+02:00',
    message_count: 1,
    attachment_count: 0,
    awaiting_reply: true,
    open_count: 1,
    resolved: false,
    headline: 'Myndighet eller förvaltare — OVK',
    why_it_matters: 'Tidsbundna krav behöver synas i kön.',
    action_hint: 'Bekräfta vad som ska bevakas.',
    supplier_name: 'Driftia Fastighetsservice AB',
    suggested_by: 'regelmotor',
    uncertainty: '',
    signals: [],
    related: [],
    events: [eventStub({
      id: 'ev3', subject: 'Påminnelse: OVK-besiktning maj 2026', origin: 'info@driftia.example', originDisplay: 'Driftia Fastighetsservice AB',
      body: 'Hej styrelsen,\n\nDetta är en påminnelse om kommande OVK. Vi återkommer med tider.\n\nMvh Driftia',
      category: 'authority_or_manager', categoryLabel: 'Myndighet eller förvaltare', awaiting: true, at: '2026-08-02T11:05:00+02:00',
    })],
  },
  {
    key: 't4',
    subject: 'Fråga om jourtid för snöröjning',
    category: 'question_awaiting_reply',
    category_label: 'Fråga som väntar svar',
    category_confirmed: false,
    latest_sender: 'medlem@gjutformen12.example',
    latest_sender_display: 'Medlem i föreningen',
    first_at: '2026-08-01T16:40:00+02:00',
    latest_at: '2026-08-01T16:40:00+02:00',
    message_count: 1,
    attachment_count: 0,
    awaiting_reply: false,
    open_count: 1,
    resolved: false,
    headline: 'Fråga som väntar svar',
    why_it_matters: 'Medlemsfrågor kan kräva svar från styrelsen.',
    action_hint: 'Bestäm om det ska bli en uppgift.',
    supplier_name: 'Medlem i föreningen',
    suggested_by: 'regelmotor',
    uncertainty: '',
    signals: [],
    related: [],
    events: [eventStub({
      id: 'ev4', subject: 'Fråga om jourtid för snöröjning', origin: 'medlem@gjutformen12.example', originDisplay: 'Medlem i föreningen',
      body: 'Hej!\n\nVilken jourtid gäller för snöröjning i vinter?\n\nTack', category: 'question_awaiting_reply', categoryLabel: 'Fråga som väntar svar',
      awaiting: false, at: '2026-08-01T16:40:00+02:00',
    })],
  },
];

intakeApi.queue = async () => ({
  threads: EMPTY_MODE ? [] : THREADS,
  categoryLabels: {
    invoice: 'Faktura',
    contract_or_quote: 'Avtal eller offert',
    authority_or_manager: 'Myndighet eller förvaltare',
    decision_or_approval: 'Beslut eller godkännande',
    question_awaiting_reply: 'Fråga som väntar svar',
    information: 'Information',
    unclear: 'Oklart',
  },
  resolutionLabels: {
    take_in: 'Ta in',
    create_task: 'Skapa uppgift',
    monitor: 'Bevaka',
    already_handled: 'Redan hanterat',
    not_relevant: 'Inte relevant',
  },
  counts: EMPTY_MODE
    ? { threads: 0, openThreads: 0, openMessages: 0, awaitingReply: 0, unclear: 0 }
    : { threads: 4, openThreads: 4, openMessages: 4, awaitingReply: 1, unclear: 0 },
  mailbox: EMPTY_MODE
    ? { hasFetched: false, last_new_count: 0, last_fetched_at: '', last_error: '' }
    : { hasFetched: false, last_new_count: 0, last_fetched_at: '', last_error: '' },
});
intakeApi.fetch = async () => ({ seen: 0, new: 0, alreadyKnown: 0, items: [], skipped: [], checkpoint: {} });
intakeApi.resolve = async () => ({});
intakeApi.confirmCategory = async () => ({});
intakeApi.reopen = async () => ({});
intakeApi.retriage = async () => ({});

integrationsApi.listSourceEvents = async () => (EMPTY_MODE ? [] : THREADS.flatMap((t) => t.events));
integrationsApi.format = async () => ({
  mail: { extension: '.eml', maxAttachments: 10, attachmentTypes: ['application/pdf'] },
});
integrationsApi.connections = async () => ({
  'microsoft-graph': { connection: { status: EMPTY_MODE ? 'connected' : 'not_connected' } },
});
integrationsApi.importSourceEvent = async () => ({ subject: 'Importerat' });

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
        currentTab="integrations"
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
            <Integrations brfId="brf-a" isAdmin />
          </div>
        </main>
      </AppNavigation>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Shell />);
