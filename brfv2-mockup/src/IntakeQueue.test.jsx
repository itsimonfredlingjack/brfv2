import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import IntakeQueue from './components/IntakeQueue';
import { intakeApi, integrationsApi } from './api';
import { datum } from './components/datum';

/**
 * The review queue for incoming post.
 *
 * What is asserted here is not that the component renders. It is that the
 * screen keeps four promises, each of which is easy to break in a refactor and
 * expensive to break in front of a board:
 *
 * 1. A reading is shown as a reading — with the words it was read from, and
 *    with who produced it.
 * 2. A human's category and the engine's guess are both visible, and visibly
 *    different.
 * 3. Nothing goes into the archive without a written reason, and the form
 *    refuses before the backend is asked.
 * 4. A settled item says where it went, not merely that it is settled.
 */

vi.mock('./api', () => ({
  api: {},
  desktopApi: {},
  integrationsApi: { importSourceEvent: vi.fn() },
  intakeApi: {
    queue: vi.fn(),
    fetch: vi.fn(),
    retriage: vi.fn(),
    confirmCategory: vi.fn(),
    resolve: vi.fn(),
    reopen: vi.fn(),
  },
  tasksApi: {},
  watchesApi: {},
}));

const CATEGORY_LABELS = {
  invoice: 'Faktura',
  contract_or_quote: 'Avtal eller offert',
  authority_or_manager: 'Myndighet eller förvaltare',
  decision_or_approval: 'Beslut eller godkännande',
  question_awaiting_reply: 'Fråga som väntar svar',
  information: 'Information',
  unclear: 'Oklart',
};

const RESOLUTION_LABELS = {
  take_in: 'Ta in',
  create_task: 'Skapa uppgift',
  monitor: 'Bevaka',
  already_handled: 'Redan hanterat',
  not_relevant: 'Inte relevant',
};

const FORMAT = {
  mail: {
    extension: '.eml',
    maxAttachments: 10,
    attachmentTypes: ['application/pdf'],
  },
};

const EVENT = {
  id: 'ev1',
  tenant_id: 'brf-a',
  source_type: 'email',
  received_at: '2026-08-01T10:00:00+00:00',
  occurred_at: '2026-02-10T09:00:00+01:00',
  external_ref: '<offert2@snosvangen.example>',
  content_sha256: 'f9bac952a56cfe18b2d7248ca6953cf1e7d8e38e2f46b0261bd6a04be6cf302f',
  provenance: {
    method: 'graph-mailbox-import',
    adapter: 'microsoft-graph',
    origin_filename: 'AAMkAGI2.eml',
    origin_bytes: 4485,
    imported_by: 'user-1',
    imported_at: '2026-08-01T10:00:00+00:00',
  },
  origin: 'anna@snosvangen.example',
  origin_display: 'Anna Lind',
  recipients: ['styrelsen@gjutformen12.example'],
  subject: 'SV: Offert takomläggning',
  body_text: 'Vi godkänner offerten på 148 000 kr och sätter igång vecka 12.',
  attachments: [{
    id: 'att1',
    filename: 'offert-tak.pdf',
    media_type: 'application/pdf',
    bytes: 2048,
    sha256: 'c'.repeat(64),
    document_id: 'doc9',
    ingested: true,
    reused_existing_document: false,
    archived: false,
    archived_by: null,
    archived_at: null,
    archive_note: null,
  }],
  import_status: 'imported',
  review_status: 'open',
  linked_document_ids: [],
  suggested_document_ids: [],
  triage: {
    category: 'decision_or_approval',
    category_label: 'Beslut eller godkännande',
    headline: 'Kan innehålla ett beslut eller godkännande — SV: Offert takomläggning (från Anna Lind)',
    why_it_matters: 'Ett godkännande som bara finns i en inkorg är svårt att belägga senare. belopp nämns (148 000 kr).',
    action_hint: 'Bevara meddelandet så att beslutet går att belägga.',
    awaiting_reply: false,
    contains_decision: true,
    supplier_name: 'Anna Lind',
    signals: [
      {
        kind: 'decision',
        label: 'Kan innehålla ett beslut',
        value: 'godkänner',
        quote: 'Vi godkänner offerten på 148 000 kr och sätter igång vecka 12.',
        source: 'body',
        source_ref: '',
      },
      {
        kind: 'amount',
        label: 'Belopp',
        value: '148000 kr',
        quote: 'Vi godkänner offerten på 148 000 kr och sätter igång vecka 12.',
        source: 'body',
        source_ref: '',
      },
      {
        kind: 'date',
        label: 'Datum i texten',
        value: '2026-09-30',
        quote: 'Svar önskas senast den 30 september 2026.',
        source: 'body',
        source_ref: '',
      },
    ],
    related: [{
      kind: 'document',
      ref_id: 'doc3',
      label: 'Snöröjningsavtal 2026.pdf',
      basis: 'föreslaget av sökningen på ämne och avsändare',
    }],
    suggested_by: 'regelmotor',
    uncertainty: '',
    created_at: '2026-08-01T10:00:00+00:00',
  },
  triage_confirmation: null,
  resolution: null,
  preserved_document_id: null,
  preserved_by: null,
  preserved_at: null,
  preservation_note: null,
  in_reply_to: null,
  references: [],
  thread_key: 'subject:offert takomläggning|gjutformen12.example,snosvangen.example',
  thread_subject: 'Offert takomläggning',
  decided_by: null,
  decided_at: null,
  decision_note: null,
};

const THREAD = {
  key: EVENT.thread_key,
  subject: 'Offert takomläggning',
  category: 'decision_or_approval',
  category_label: 'Beslut eller godkännande',
  category_confirmed: false,
  latest_sender: 'anna@snosvangen.example',
  latest_sender_display: 'Anna Lind',
  first_at: '2026-02-03T08:14:00+01:00',
  latest_at: '2026-02-10T09:00:00+01:00',
  message_count: 2,
  attachment_count: 1,
  awaiting_reply: false,
  open_count: 1,
  resolved: false,
  headline: EVENT.triage.headline,
  why_it_matters: EVENT.triage.why_it_matters,
  action_hint: EVENT.triage.action_hint,
  supplier_name: 'Anna Lind',
  suggested_by: 'regelmotor',
  uncertainty: '',
  signals: EVENT.triage.signals,
  related: EVENT.triage.related,
  events: [EVENT],
};

function mountWith({
  threads = [THREAD],
  mailbox = { hasFetched: false, last_new_count: 0, last_fetched_at: '', last_error: '' },
  counts = { threads: 1, openThreads: 1, openMessages: 1, awaitingReply: 0, unclear: 0 },
  isAdmin = true,
  mailboxConnected = true,
  onOpenDocument = vi.fn(),
} = {}) {
  intakeApi.queue.mockResolvedValue({
    threads,
    categoryLabels: CATEGORY_LABELS,
    resolutionLabels: RESOLUTION_LABELS,
    mailbox,
    counts,
  });
  return render(
    <IntakeQueue
      brfId="brf-a"
      isAdmin={isAdmin}
      mailboxConnected={mailboxConnected}
      format={FORMAT}
      onOpenDocument={onOpenDocument}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

async function waitForQueue() {
  return screen.findByRole('list', { name: 'Trådar i kön' });
}

// ---------------------------------------------------------------------------

describe('the queue, before anything is decided', () => {
  it('keeps the mailbox promise on the decision, not as a page manifesto', async () => {
    mountWith();
    await waitForQueue();
    expect(screen.queryByText(/Brevlådan är råmaterial/)).not.toBeInTheDocument();
    expect(screen.getByText(/Ingenting ändras i brevlådan/)).toBeInTheDocument();
  });

  it('shows a thread as something to choose, not something to decide from', async () => {
    mountWith();
    const list = await screen.findByRole('list', { name: 'Trådar i kön' });
    expect(within(list).getByText('Offert takomläggning')).toBeInTheDocument();
    const meta = within(list).getByText(/Anna Lind/);
    expect(meta).toHaveTextContent(datum('2026-02-10'));
    expect(meta).not.toHaveTextContent('Senast från');
    expect(meta).not.toHaveTextContent('meddelande');
    expect(meta).not.toHaveTextContent('bilag');
    expect(within(list).queryByText('Beslut eller godkännande')).not.toBeInTheDocument();
  });

  it('keeps list rows choose-dense: subject, sender, date — not a decision form', async () => {
    mountWith();
    await waitForQueue();
    const row = document.querySelector('.thread-row');
    expect(row.querySelector('.thread-subject')).toBeTruthy();
    expect(row.querySelector('.thread-meta')).toBeTruthy();
    expect(row.querySelector('.thread-meta').textContent).not.toMatch(/meddelande|bilaga/i);
  });

  it('keeps awaiting-reply discoverable via the filter, not as a list chip', async () => {
    mountWith({
      threads: [{ ...THREAD, awaiting_reply: true }],
      counts: { threads: 1, openThreads: 1, awaitingReply: 1 },
    });
    await waitForQueue();
    expect(screen.queryByText(/ser ut att vänta svar/)).not.toBeInTheDocument();
    const filter = screen.getByLabelText('Filtrera kön');
    expect(filter.querySelector('option[value="awaiting"]')).toHaveTextContent('Väntar svar (1)');
  });

  it('does not restate list metadata in the detail head', async () => {
    mountWith();
    await waitForQueue();
    const detail = document.querySelector('.detail-head');
    expect(detail).toBeTruthy();
    expect(detail).toHaveTextContent('Offert takomläggning');
    expect(detail).not.toHaveTextContent('att ta ställning till');
    expect(detail).not.toHaveTextContent('Beslut eller godkännande');
    expect(detail).not.toHaveTextContent(datum('2026-02-03'));
    expect(detail).not.toHaveTextContent('bilag');
  });

  it('filters to what still needs a decision without hiding the rest', async () => {
    mountWith({
      threads: [THREAD, { ...THREAD, key: 't2', subject: 'Avklarad tråd', resolved: true, open_count: 0 }],
      counts: { threads: 2, openThreads: 1, awaitingReply: 0 },
    });
    await waitForQueue();
    expect(screen.queryByText('Avklarad tråd')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Filtrera kön'), { target: { value: 'all' } });
    expect(await screen.findByText('Avklarad tråd')).toBeInTheDocument();
  });

  // The filter is a named select, the way Fakturor writes its four. What the
  // control must not lose is that all three modes are named and countable
  // without operating it.
  it('names all three modes, with their counts, without being opened', async () => {
    mountWith();
    await waitForQueue();
    const filter = screen.getByLabelText('Filtrera kön');
    expect(filter.querySelector('option[value="open"]')).toHaveTextContent(/^Att avgöra \(\d+\)$/);
    expect(filter.querySelector('option[value="awaiting"]')).toHaveTextContent(/^Väntar svar \(\d+\)$/);
    expect(filter.querySelector('option[value="all"]')).toHaveTextContent(/^Alla trådar \(\d+\)$/);
  });

  it('keeps the filter toolbar as its own row above the list', async () => {
    mountWith();
    await waitForQueue();
    const toolbar = document.querySelector('.intake-toolbar');
    const list = document.querySelector('.intake-list');
    expect(toolbar).toBeTruthy();
    expect(list).toBeTruthy();
    expect(toolbar.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('spares the bare count on a one-message thread, shows it when more remain', async () => {
    mountWith({
      threads: [
        THREAD,
        { ...THREAD, key: 't2', subject: 'Faktura hisservice', open_count: 3 },
      ],
      counts: { threads: 2, openThreads: 2, awaitingReply: 0 },
    });
    const list = await waitForQueue();
    const rows = list.querySelectorAll('.thread-row');
    expect(rows[0].querySelector('.thread-row-state')).toBeNull();
    expect(rows[1].querySelector('.thread-row-state')).toHaveTextContent('3');
  });
});

describe('what the app believes', () => {
  it('shows the reading under a heading that says it is a reading', async () => {
    mountWith();
    expect(await screen.findByText('Vad det ser ut att gälla')).toBeInTheDocument();
    expect(screen.getByText(EVENT.triage.headline)).toBeInTheDocument();
    expect(screen.getByText('bedömt av regelmotor')).toBeInTheDocument();
  });

  it('keeps why and underlag one disclosure away by default', async () => {
    mountWith();
    await waitForQueue();
    expect(screen.getByText(EVENT.triage.headline)).toBeVisible();
    expect(screen.getByText(/Ett godkännande som bara finns i en inkorg/)).not.toBeVisible();
    expect(screen.getByText('Läst ur meddelandet')).not.toBeVisible();
    expect(screen.getByText('Snöröjningsavtal 2026.pdf')).not.toBeVisible();

    fireEvent.click(screen.getByText('Varför och underlag'));

    expect(screen.getByText(/Ett godkännande som bara finns i en inkorg/)).toBeVisible();
    expect(screen.getByText('Läst ur meddelandet')).toBeVisible();
    expect(screen.getByText('Snöröjningsavtal 2026.pdf')).toBeVisible();
  });

  it('names who produced the reading, and never calls a rule engine AI', async () => {
    mountWith();
    expect(await screen.findByText('bedömt av regelmotor')).toBeInTheDocument();
  });

  it('says when a language model was involved', async () => {
    mountWith({
      threads: [{ ...THREAD, suggested_by: 'regelmotor + språkmodell (gemma4:e12b)' }],
    });
    expect(await screen.findByText(/bedömt av regelmotor \+ språkmodell \(gemma4:e12b\)/))
      .toBeInTheDocument();
  });

  it('shows every value next to the words it was read from', async () => {
    mountWith();
    await waitForQueue();
    fireEvent.click(screen.getByText('Varför och underlag'));
    const signals = screen.getByText('Läst ur meddelandet').closest('div');

    // A value without its quote is an unverifiable claim, so each one is
    // asserted together with the sentence behind it.
    expect(within(signals).getByText('148000 kr')).toBeInTheDocument();
    expect(within(signals).getByText('2026-09-30')).toBeInTheDocument();
    expect(within(signals).getAllByText(/Vi godkänner offerten på 148 000 kr/).length)
      .toBeGreaterThan(0);
    expect(within(signals).getByText(/Svar önskas senast den 30 september 2026/))
      .toBeInTheDocument();
    expect(within(signals).getAllByText(/ur mejltexten/).length).toBeGreaterThan(0);
  });

  it('marks a related record as a proposal and states its basis', async () => {
    mountWith();
    await waitForQueue();
    fireEvent.click(screen.getByText('Varför och underlag'));
    const item = screen.getByText('Snöröjningsavtal 2026.pdf').closest('li');
    expect(within(item).getByText('förslag')).toBeInTheDocument();
    expect(within(item).getByText(/föreslaget av sökningen på ämne och avsändare/))
      .toBeInTheDocument();
  });

  it('shows stated uncertainty rather than a confident empty card', async () => {
    mountWith({
      threads: [{
        ...THREAD,
        category: 'unclear',
        category_label: 'Oklart',
        signals: [],
        uncertainty: 'Meddelandet innehåller ingen text som den här läsningen känner igen.',
      }],
    });
    expect(await screen.findByText(/ingen text som den här läsningen känner igen/))
      .toBeInTheDocument();
  });
});

describe('correcting the category', () => {
  it('records the human decision and keeps the suggestion visible beside it', async () => {
    mountWith({
      threads: [{
        ...THREAD,
        category_confirmed: true,
        events: [{
          ...EVENT,
          triage_confirmation: {
            category: 'authority_or_manager',
            category_label: 'Myndighet eller förvaltare',
            confirmed_by: 'user-1',
            confirmed_at: '2026-08-01T11:00:00+00:00',
            note: 'Det är förvaltaren som skrivit.',
          },
        }],
      }],
    });
    const block = (await screen.findByText(/har satt kategorin till/)).closest('p');
    expect(within(block).getByText('Myndighet eller förvaltare')).toBeInTheDocument();
    expect(block).toHaveTextContent('Det är förvaltaren som skrivit.');
    // The engine's guess survives the correction: the pair is the only record
    // of where the reading was wrong.
    expect(within(block).getByText('Beslut eller godkännande')).toBeInTheDocument();
  });

  it('posts exactly the category that was chosen', async () => {
    mountWith();
    await waitForQueue();
    fireEvent.click(screen.getByRole('button', { name: /Rätta kategorin/ }));

    fireEvent.change(screen.getByLabelText('Kategori'), { target: { value: 'invoice' } });
    intakeApi.confirmCategory.mockResolvedValue(EVENT);
    fireEvent.click(screen.getByRole('button', { name: 'Spara kategorin' }));

    await waitFor(() => expect(intakeApi.confirmCategory)
      .toHaveBeenCalledWith('brf-a', 'ev1', 'invoice', ''));
  });
});

describe('fetching', () => {
  it('says when it last looked and what it found', async () => {
    mountWith({
      mailbox: {
        hasFetched: true,
        last_fetched_at: '2026-08-01T10:00:00+00:00',
        last_new_count: 3,
        last_error: '',
      },
    });
    expect(await screen.findByText(/senast .* · 3 nya/i)).toBeInTheDocument();
    expect(screen.queryByText(/frågar efter det som kommit sedan förra gången/))
      .not.toBeInTheDocument();
  });

  it('reports what could not be taken in rather than staying silent', async () => {
    mountWith();
    await waitForQueue();
    intakeApi.fetch.mockResolvedValue({
      seen: 2,
      new: 1,
      alreadyKnown: 0,
      events: [],
      skipped: [{
        external_ref: '<x@fixture.invalid>',
        subject: 'Underlag i kalkylblad',
        sender: 'forvaltare@example.se',
        received_at: '2026-08-01T09:00:00+00:00',
        code: 'unsupported_attachment',
        reason: "Bilagan 'underlag.csv' är text/csv. Den här versionen tar bara emot application/pdf",
      }],
      checkpoint: { hasFetched: true },
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta nytt/ }));

    // The queue is not the mailbox, and says so.
    expect(await screen.findByText(/kunde inte tas in — de ligger kvar i brevlådan/))
      .toBeInTheDocument();
    expect(screen.getByText(/underlag\.csv/)).toBeInTheDocument();
  });

  it('says plainly when there is nothing new', async () => {
    mountWith();
    await waitForQueue();
    intakeApi.fetch.mockResolvedValue({
      seen: 0, new: 0, alreadyKnown: 0, events: [], skipped: [], checkpoint: {},
    });
    fireEvent.click(screen.getByRole('button', { name: /Hämta nytt/ }));
    expect(await screen.findByText(/Inget nytt sedan förra hämtningen/)).toBeInTheDocument();
  });

  it('shows a failed fetch as a failure, not as an empty result', async () => {
    mountWith({
      mailbox: {
        hasFetched: true,
        last_fetched_at: '2026-08-01T10:00:00+00:00',
        last_new_count: 0,
        last_error: 'microsoft-graph: 503 Service Unavailable',
      },
    });
    expect(await screen.findByText(/Senaste försöket gick inte igenom/)).toBeInTheDocument();
    expect(screen.getByText(/Läget är oförändrat/)).toBeInTheDocument();
  });

  it('keeps the manual .eml import usable with nothing connected', async () => {
    mountWith({ mailboxConnected: false });
    expect(await screen.findByText('Importera .eml')).toBeInTheDocument();
    expect(screen.getByText(/Ingen brevlåda är ansluten/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hämta nytt/ })).toBeDisabled();
    expect(intakeApi.fetch).not.toHaveBeenCalled();
  });

  it('keeps the source row as a single toolstrip line', async () => {
    mountWith();
    await waitForQueue();
    const source = document.querySelector('.intake-source');
    expect(source).toBeTruthy();
    expect(source.querySelector('.intake-source-row')).toBeTruthy();
    // No permanent gray manifesto paragraph as a sibling article block
    expect(screen.queryByText(/Brevlådan är råmaterial/)).not.toBeInTheDocument();
  });

  it('puts fetch policy behind Om hämtning, not in the first viewport body', async () => {
    mountWith();
    await waitForQueue();
    const disclosure = screen.getByText('Om hämtning').closest('details');
    expect(disclosure).toBeTruthy();
    expect(disclosure.open).toBe(false);
    expect(screen.queryByText(/halvimporteras/)).not.toBeVisible();
    fireEvent.click(screen.getByText('Om hämtning'));
    expect(screen.getByText(/halvimporteras/)).toBeVisible();
  });

  it('keeps format limits one disclosure away, not in the first viewport', async () => {
    mountWith();
    await screen.findByText('Importera .eml');
    const note = screen.getByText(/application\/pdf som bilaga/);
    expect(note).not.toBeVisible();
    fireEvent.click(screen.getByText(/Om hämtning/));
    expect(note).toBeVisible();
    expect(screen.getByText(/Allt annat avvisas i sin helhet/)).toBeVisible();
  });

  it('surfaces a refusal reason from the backend verbatim', async () => {
    mountWith();
    await waitForQueue();
    integrationsApi.importSourceEvent.mockRejectedValue(
      new Error("Bilagan 'underlag.csv' är text/csv. Den här versionen tar bara emot application/pdf"),
    );
    fireEvent.change(document.getElementById('intake-eml-import'), {
      target: { files: [new File(['x'], 'underlag.eml', { type: 'message/rfc822' })] },
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/underlag\.csv/);
  });
});

describe('the message itself', () => {
  it('demotes the bare address beside a display name, without the brackets', async () => {
    mountWith();
    await waitForQueue();
    const sender = document.querySelector('.message-sender');
    expect(sender).toHaveTextContent('Anna Lind');
    const addr = sender.querySelector('.message-sender-addr');
    expect(addr).toHaveTextContent('anna@snosvangen.example');
    expect(addr.textContent).not.toMatch(/[<>]/);
  });

  it('shows provenance the operator can check the message against', async () => {
    mountWith();
    await waitForQueue();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));

    expect(screen.getByText('graph-mailbox-import / microsoft-graph')).toBeInTheDocument();
    expect(screen.getByText('user-1')).toBeInTheDocument();
    expect(screen.getByText(/f9bac952a56cfe18b2d724/)).toBeInTheDocument();
  });

  it('keeps an attachment as material under review until somebody says otherwise', async () => {
    mountWith();
    await waitForQueue();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));

    const item = screen.getByText('offert-tak.pdf').closest('li');
    expect(within(item).getByText('material under granskning')).toBeInTheDocument();
  });

  it('shows a preserved message as preserved, by whom and why', async () => {
    mountWith({
      threads: [{
        ...THREAD,
        events: [{
          ...EVENT,
          preserved_document_id: 'doc42',
          preserved_by: 'user-1',
          preserved_at: '2026-08-01T11:00:00+00:00',
          preservation_note: 'Godkännandet måste gå att belägga.',
        }],
      }],
    });
    await waitForQueue();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));
    expect(screen.getByText(/Texten är bevarad som dokument/)).toBeInTheDocument();
    expect(screen.getByText(/Godkännandet måste gå att belägga/)).toBeInTheDocument();
  });
});

describe('readable detail hierarchy', () => {
  it('keeps message before reading before decision', async () => {
    mountWith();
    await waitForQueue();
    const evidence = document.querySelector('.thread-evidence');
    const messages = evidence.querySelector('.detail-section.messages');
    const reading = evidence.querySelector('.detail-section.reading');
    const decisions = document.querySelector('.thread-decisions');
    expect(messages.compareDocumentPosition(reading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(evidence.compareDocumentPosition(decisions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('marks reading as secondary chrome relative to the message', async () => {
    mountWith();
    await waitForQueue();
    const reading = document.querySelector('.detail-section.reading');
    expect(reading.classList.contains('reading--secondary')).toBe(true);
    expect(reading.querySelector('details.reading-depth')?.open ?? false).toBe(false);
  });
});

describe('detail layout for deciding', () => {
  it('anchors decisions below a scrollable evidence region', async () => {
    mountWith();
    await waitForQueue();

    const evidence = document.querySelector('.thread-evidence');
    const decisions = document.querySelector('.thread-decisions');
    expect(evidence).toBeTruthy();
    expect(decisions).toBeTruthy();
    expect(evidence.querySelector('.detail-section.messages')).toBeTruthy();
    expect(evidence.querySelector('.detail-section.reading')).toBeTruthy();
    expect(evidence.querySelector('.detail-section.decision')).toBeNull();
    expect(decisions.querySelector('.detail-section.decision')).toBeTruthy();
    expect(
      evidence.compareDocumentPosition(decisions) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Spara beslutet' })).toBeInTheDocument();
    expect(screen.getByText('Vad det ser ut att gälla')).toBeVisible();
    expect(screen.getByText(EVENT.triage.headline)).toBeVisible();
  });
});

describe('resolving', () => {
  function openForm() {
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));
  }

  it('offers every outcome the product model has', async () => {
    mountWith();
    await waitForQueue();
    openForm();
    for (const label of Object.values(RESOLUTION_LABELS)) {
      expect(screen.getByRole('checkbox', { name: label })).toBeInTheDocument();
    }
  });

  it('separates the combinable outcomes from the ones that close the item', async () => {
    mountWith();
    await waitForQueue();
    openForm();
    const options = document.querySelector('.resolve-options');
    const divider = options.querySelector('.resolve-divider');
    expect(divider).toBeTruthy();
    expect(divider.previousElementSibling).toHaveTextContent('Bevaka');
    expect(divider.nextElementSibling).toHaveTextContent('Redan hanterat');
    const labels = [...options.querySelectorAll('label')].map((l) => l.textContent);
    expect(labels).toEqual(['Ta in', 'Skapa uppgift', 'Bevaka', 'Redan hanterat', 'Inte relevant']);
  });

  it('refuses to take anything in without a stated reason, before the backend is asked', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Ta in' }));
    const submit = screen.getByRole('button', { name: 'Spara beslutet' });
    expect(submit).toBeDisabled();

    fireEvent.click(submit);
    expect(intakeApi.resolve).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Varför ska posten bevaras\?/), {
      target: { value: 'Godkännandet måste gå att belägga.' },
    });
    expect(submit).toBeEnabled();
  });

  it('preserves the message without adopting its attachments by default', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Ta in' }));
    fireEvent.change(screen.getByLabelText(/Varför ska posten bevaras\?/), {
      target: { value: 'Godkännandet måste gå att belägga.' },
    });
    intakeApi.resolve.mockResolvedValue({ ...EVENT, resolution: { outcomes: [], decided_by: 'user-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Spara beslutet' }));

    await waitFor(() => expect(intakeApi.resolve).toHaveBeenCalledWith('brf-a', 'ev1', {
      outcomes: ['take_in'],
      note: 'Godkännandet måste gå att belägga.',
      attachment_ids: [],
      task: null,
      watch: null,
    }));
  });

  it('sends the attachments a reviewer explicitly chose', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Ta in' }));
    fireEvent.click(screen.getByRole('checkbox', { name: /offert-tak\.pdf/ }));
    fireEvent.change(screen.getByLabelText(/Varför ska posten bevaras\?/), {
      target: { value: 'Offerten hör till underlaget.' },
    });
    intakeApi.resolve.mockResolvedValue({ ...EVENT, resolution: { outcomes: [], decided_by: 'user-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Spara beslutet' }));

    await waitFor(() => expect(intakeApi.resolve).toHaveBeenCalledWith(
      'brf-a', 'ev1', expect.objectContaining({ attachment_ids: ['att1'] }),
    ));
  });

  it('combines preserving with taking work on, in one act', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Ta in' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Skapa uppgift' }));
    fireEvent.change(screen.getByLabelText('Rubrik'), {
      target: { value: 'Beställ takomläggning' },
    });
    fireEvent.change(screen.getByLabelText('Ansvarig'), { target: { value: 'Bo' } });
    fireEvent.change(screen.getByLabelText(/Varför ska posten bevaras\?/), {
      target: { value: 'Godkännandet måste gå att belägga.' },
    });
    intakeApi.resolve.mockResolvedValue({ ...EVENT, resolution: { outcomes: [], decided_by: 'user-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Spara beslutet' }));

    await waitFor(() => expect(intakeApi.resolve).toHaveBeenCalledWith(
      'brf-a', 'ev1', expect.objectContaining({
        outcomes: ['take_in', 'create_task'],
        task: { title: 'Beställ takomläggning', responsible: 'Bo', due_date: '' },
      }),
    ));
  });

  it('offers the dates it read, as something to press rather than a prefilled guess', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bevaka' }));
    // The chip says the date the way a person says it; what it *sets* is the
    // machine form the date field needs.
    const chip = screen.getByRole('button', { name: '30 sep.' });
    expect(screen.getByLabelText('Datum')).toHaveValue('');

    fireEvent.click(chip);
    expect(screen.getByLabelText('Datum')).toHaveValue('2026-09-30');
  });

  it('will not let a card say both "inte relevant" and something else', async () => {
    mountWith();
    await waitForQueue();
    openForm();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Ta in' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Inte relevant' }));

    expect(screen.getByRole('checkbox', { name: 'Inte relevant' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Ta in' })).not.toBeChecked();
  });

  it('says that the mailbox is untouched, on the form where it matters', async () => {
    mountWith();
    await waitForQueue();
    openForm();
    expect(screen.getByText(/Ingenting ändras i brevlådan/)).toBeInTheDocument();
  });
});

describe('a resolved item', () => {
  const settled = {
    ...EVENT,
    review_status: 'approved',
    preserved_document_id: 'doc42',
    resolution: {
      outcomes: [
        { kind: 'take_in', label: 'Meddelandets text bevarad som dokument', ref_id: 'doc42', ref_label: 'E-post 2026-02-10 — SV- Offert takomläggning.pdf' },
        { kind: 'create_task', label: 'Skapa uppgift', ref_id: 'task7', ref_label: 'Beställ takomläggning (att göra)' },
      ],
      decided_by: 'user-1',
      decided_at: '2026-08-01T11:00:00+00:00',
      note: 'Godkännandet måste gå att belägga.',
    },
  };

  /** Resolved threads live behind the all-threads filter, collapsed.
   *
   * The filter is reached after the queue has loaded, not before it. It used
   * to be drawn while the fetch was still out — a control offering to narrow
   * something nobody had seen yet — and now it only exists once there is a
   * queue with something in it. Same three options, one await earlier. */
  async function showResolved() {
    const filter = await screen.findByLabelText('Filtrera kön');
    fireEvent.change(filter, { target: { value: 'all' } });
    const list = await waitForQueue();
    fireEvent.click(within(list).getByText('Offert takomläggning'));
  }

  it('says where it went, not merely that it is handled', async () => {
    mountWith({ threads: [{ ...THREAD, resolved: true, open_count: 0, events: [settled] }] });
    await showResolved();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));

    expect(screen.getByText('Meddelandets text bevarad som dokument')).toBeInTheDocument();
    expect(screen.getByText(/E-post 2026-02-10/)).toBeInTheDocument();
    expect(screen.getByText(/Beställ takomläggning \(att göra\)/)).toBeInTheDocument();
  });

  it('opens the preserved document through the app’s own navigation', async () => {
    const onOpenDocument = vi.fn();
    mountWith({
      threads: [{ ...THREAD, resolved: true, open_count: 0, events: [settled] }],
      onOpenDocument,
    });
    await showResolved();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));
    fireEvent.click(screen.getAllByRole('button', { name: 'Öppna dokumentet' })[0]);

    expect(onOpenDocument).toHaveBeenCalledWith('doc42', 1);
  });

  it('can be reopened, and says that what it produced stays', async () => {
    mountWith({ threads: [{ ...THREAD, resolved: true, open_count: 0, events: [settled] }] });
    await showResolved();
    fireEvent.click(screen.getByText('SV: Offert takomläggning'));

    expect(screen.getByText(/Det som redan skapats står kvar/)).toBeInTheDocument();
    intakeApi.reopen.mockResolvedValue({ ...EVENT, resolution: null });
    fireEvent.click(screen.getByRole('button', { name: /Öppna i kön igen/ }));
    await waitFor(() => expect(intakeApi.reopen).toHaveBeenCalledWith('brf-a', 'ev1'));
  });
});

describe('a member who is not an administrator', () => {
  it('may read the queue and may not act on it', async () => {
    mountWith({ isAdmin: false });
    await waitForQueue();

    // Reading is the point of showing it; the acts are admin-only in the
    // backend, and the UI must not offer what the route will refuse.
    expect(screen.queryByRole('button', { name: /Hämta nytt/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Importera .eml')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('SV: Offert takomläggning'));
    expect(screen.getByRole('checkbox', { name: 'Ta in' })).toBeDisabled();
  });
});

describe('the keyboard flow', () => {
  const TWO_THREADS = [
    THREAD,
    { ...THREAD, key: 't2', subject: 'Faktura hisservice', open_count: 3 },
  ];
  const TWO_COUNTS = { threads: 2, openThreads: 2, openMessages: 4, awaitingReply: 0, unclear: 0 };

  it('"/" lands on the filter, unless the user is typing', async () => {
    mountWith();
    await waitForQueue();
    const filter = screen.getByLabelText('Filtrera kön');
    fireEvent.keyDown(window, { key: '/' });
    expect(document.activeElement).toBe(filter);

    document.activeElement.blur();
    fireEvent.keyDown(document.querySelector('#intake-eml-import'), { key: '/' });
    expect(document.activeElement).not.toBe(filter);
  });

  it('moves the mark with the arrow keys', async () => {
    mountWith({ threads: TWO_THREADS, counts: TWO_COUNTS });
    const list = await waitForQueue();
    const rows = list.querySelectorAll('.thread-row');
    rows[0].focus();

    fireEvent.keyDown(list, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(rows[1]);
    expect(rows[1]).toHaveAttribute('aria-current', 'true');

    fireEvent.keyDown(list, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(rows[0]);
    expect(rows[0]).toHaveAttribute('aria-current', 'true');
  });

  it('does not move past the ends of the list', async () => {
    mountWith();
    const list = await waitForQueue();
    const row = list.querySelector('.thread-row');
    row.focus();
    fireEvent.keyDown(list, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(row);
    fireEvent.keyDown(list, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(row);
  });

  it('Enter steps into the detail, Escape steps back to the marked row', async () => {
    mountWith();
    const list = await waitForQueue();
    const row = list.querySelector('.thread-row');
    row.focus();

    fireEvent.keyDown(list, { key: 'Enter' });
    const detail = document.querySelector('.intake-detail');
    expect(document.activeElement).toBe(detail);

    fireEvent.keyDown(detail, { key: 'Escape' });
    expect(document.activeElement).toBe(row);
  });
});
