import { describe, expect, it } from 'vitest'

import type { Watch, WatchBoard, WatchKind, WatchStatus } from '../api/types'
import {
  BUCKET_ORDER,
  UNASSIGNED,
  boardIsEmpty,
  bucketLabel,
  dueSentence,
  kindLabel,
  responsibleLabel,
  statusLabel,
} from './watches'

/** Every kind and status the backend defines (backend/app/watches/models.py). */
const ALL_KINDS: WatchKind[] = [
  'notice_deadline',
  'expiry',
  'warranty',
  'inspection',
  'recurring_obligation',
]

const ALL_STATUSES: WatchStatus[] = ['proposed', 'approved', 'dismissed', 'done']

function watch(overrides: Partial<Watch> = {}): Watch {
  return {
    id: 'w-1',
    tenant_id: 'gjutformen-12',
    kind: 'notice_deadline',
    status: 'approved',
    title: 'Säg upp eller ompröva städavtalet senast 2026-09-30',
    due_date: '2026-09-30',
    derived_due_date: '2026-09-30',
    derivation: '2026-12-31 minus tre månaders uppsägningstid',
    recurrence: 'none',
    responsible: 'Anna Ek',
    remind_lead_days: 30,
    citations: [],
    source_document_id: 'doc-1',
    source_document_name: 'Städavtal 2024',
    created_at: '2026-07-01T09:00:00+00:00',
    decided_by: null,
    decided_at: null,
    decision_note: null,
    succeeded_by: null,
    kind_label: 'Uppsägning',
    status_label: 'bevakas',
    remind_at: '2026-08-31',
    bucket: 'later',
    days_left: 60,
    next_due_after: null,
    ...overrides,
  }
}

function board(overrides: Partial<WatchBoard> = {}): WatchBoard {
  return {
    today: '2026-08-01',
    proposed: [],
    buckets: { overdue: [], soon: [], later: [], recurring: [] },
    bucketLabels: {
      overdue: 'Försenat',
      soon: 'Snart',
      later: 'Senare',
      recurring: 'Återkommande',
    },
    kindLabels: {
      notice_deadline: 'Uppsägning',
      expiry: 'Avtalet upphör',
      warranty: 'Garanti',
      inspection: 'Besiktning eller kontroll',
      recurring_obligation: 'Återkommande skyldighet',
    },
    statusLabels: {
      proposed: 'väntar på godkännande',
      approved: 'bevakas',
      dismissed: 'avfärdad',
      done: 'avklarad',
    },
    settled: [],
    unresolved: [],
    ...overrides,
  }
}

describe('dueSentence', () => {
  it('säger hur långt bort datumet är, inte bara vilket det är', () => {
    expect(dueSentence(watch({ days_left: 60 }))).toBe('30 september 2026 · om 60 dagar')
    expect(dueSentence(watch({ days_left: 0 }))).toBe('30 september 2026 · i dag')
    expect(dueSentence(watch({ days_left: -12 }))).toBe('30 september 2026 · 12 dagar sedan')
  })

  it('böjer dagen i singular', () => {
    expect(dueSentence(watch({ days_left: 1 }))).toContain('om 1 dag')
    expect(dueSentence(watch({ days_left: -1 }))).toContain('1 dag sedan')
    expect(dueSentence(watch({ days_left: 2 }))).toContain('2 dagar')
  })

  it('faller tillbaka på enbart datumet när servern inte räknat', () => {
    expect(dueSentence(watch({ days_left: null }))).toBe('30 september 2026')
  })

  it('visar den dag avtalet menar, oavsett tidszon', () => {
    // 'YYYY-MM-DD' är ett almanacksdatum. Läst som UTC-midnatt blir det dagen
    // innan väster om London — en dag som inte står i något avtal.
    expect(dueSentence(watch({ due_date: '2026-01-01', days_left: null }))).toBe('1 januari 2026')
  })
})

describe('etiketter', () => {
  it('använder serverns ord, inte klientens', () => {
    const value = board({
      bucketLabels: {
        overdue: 'Passerat',
        soon: 'Nära',
        later: 'Längre fram',
        recurring: 'Cykliskt',
      },
    })
    expect(BUCKET_ORDER.map((bucket) => bucketLabel(value, bucket))).toEqual([
      'Passerat',
      'Nära',
      'Längre fram',
      'Cykliskt',
    ])
  })

  it('har svenska ord för varje sort och status backenden definierar', () => {
    // Om backenden slutar skicka etiketten ska skärmen inte visa 'expiry'.
    const bare = board({ kindLabels: {}, statusLabels: {} })
    for (const kind of ALL_KINDS) {
      const label = kindLabel(bare, watch({ kind, kind_label: '' }))
      expect(label, kind).not.toBe(kind)
      expect(label.length, kind).toBeGreaterThan(3)
    }
    for (const status of ALL_STATUSES) {
      const label = statusLabel(bare, watch({ status, status_label: '' }))
      expect(label, status).not.toBe(status)
    }
  })
})

describe('responsibleLabel', () => {
  it('säger rakt ut att ingen är utsedd', () => {
    expect(responsibleLabel(watch({ responsible: '' }))).toBe(UNASSIGNED)
    expect(responsibleLabel(watch({ responsible: '   ' }))).toBe(UNASSIGNED)
    expect(responsibleLabel(watch({ responsible: 'Anna Ek' }))).toBe('Anna Ek')
  })
})

describe('boardIsEmpty', () => {
  it('skiljer på tomt och på att hinkarna är tomma', () => {
    expect(boardIsEmpty(board())).toBe(true)
    expect(boardIsEmpty(board({ proposed: [watch({ status: 'proposed' })] }))).toBe(false)
    expect(
      boardIsEmpty(
        board({
          unresolved: [
            {
              id: 'u-1',
              tenant_id: 'gjutformen-12',
              what: 'Garantitiden löper från slutbesiktningen.',
              why: 'Slutbesiktningens datum står inte i handlingen.',
              citations: [],
              source_document_id: 'doc-2',
              source_document_name: 'Entreprenadkontrakt',
              created_at: '2026-07-01T09:00:00+00:00',
            },
          ],
        }),
      ),
    ).toBe(false)
  })
})
