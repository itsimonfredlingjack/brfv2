import { beforeEach, describe, expect, it } from 'vitest'

import type { JournalEntry } from './localStore'
import {
  RETENTION_DAYS,
  clearJournal,
  getCachedPage,
  getEntry,
  listEntries,
  metaCache,
  newEntryId,
  putCachedPage,
  saveEntry,
  tenantKey,
  wipeEverything,
  wipeTenant,
} from './localStore'

/* The backend's adversarial isolation suite proves BRF A can never reach BRF
 * B's content. Everything below exists so this client cannot hand that leak
 * straight back through a cache. */

const DAY_MS = 24 * 60 * 60 * 1000

function entry(brfId: string, overrides: Partial<JournalEntry> = {}): JournalEntry {
  return {
    id: newEntryId(),
    brfId,
    question: 'Vad gäller för andrahandsuthyrning?',
    createdAt: Date.now(),
    answer: 'Styrelsens skriftliga samtycke krävs.',
    refusal: false,
    refusalReason: null,
    warning: null,
    citations: [],
    rejected: [],
    provider: 'scripted',
    model: 'test',
    ...overrides,
  }
}

const blob = (text: string) => new Blob([text], { type: 'image/png' })

beforeEach(async () => {
  await wipeEverything()
})

describe('tenantKey', () => {
  it('prefixes every key with the tenant id', () => {
    expect(tenantKey('gjutformen-12', 'page', 'doc1', 4, 1080)).toBe(
      'gjutformen-12::page::doc1::4::1080',
    )
  })
})

describe('journal', () => {
  it('stores and reads back an answer', async () => {
    const saved = entry('brf-a')
    await saveEntry(saved)
    expect(await getEntry('brf-a', saved.id)).toMatchObject({ id: saved.id, answer: saved.answer })
  })

  it('lists newest first', async () => {
    const old = entry('brf-a', { createdAt: Date.now() - 60_000, question: 'äldre' })
    const recent = entry('brf-a', { question: 'nyare' })
    await saveEntry(old)
    await saveEntry(recent)

    const list = await listEntries('brf-a')
    expect(list.map((e) => e.question)).toEqual(['nyare', 'äldre'])
  })

  it('prunes answers past the retention window on read', async () => {
    const expired = entry('brf-a', { createdAt: Date.now() - (RETENTION_DAYS + 1) * DAY_MS })
    const fresh = entry('brf-a')
    await saveEntry(expired)
    await saveEntry(fresh)

    expect(await listEntries('brf-a')).toHaveLength(1)
    // Pruning is a delete, not a filter — the text must be gone from disk.
    expect(await getEntry('brf-a', expired.id)).toBeUndefined()
  })
})

describe('tenant isolation', () => {
  it('never lists one förening’s answers under another', async () => {
    await saveEntry(entry('brf-a', { question: 'A-fråga' }))
    await saveEntry(entry('brf-b', { question: 'B-fråga' }))

    expect((await listEntries('brf-a')).map((e) => e.question)).toEqual(['A-fråga'])
    expect((await listEntries('brf-b')).map((e) => e.question)).toEqual(['B-fråga'])
  })

  it('does not resolve an answer id across tenants', async () => {
    const a = entry('brf-a')
    await saveEntry(a)
    expect(await getEntry('brf-b', a.id)).toBeUndefined()
  })

  it('keeps page images per tenant even for identical document ids', async () => {
    // Document ids are per-tenant, so a collision is possible in principle —
    // and must not produce A's page inside B.
    await putCachedPage('brf-a', 'doc-1', 1, 1080, blob('SIDA-FRAN-A'))
    await putCachedPage('brf-b', 'doc-1', 1, 1080, blob('SIDA-FRAN-B'))

    const fromB = await getCachedPage('brf-b', 'doc-1', 1, 1080)
    expect(await fromB!.text()).toBe('SIDA-FRAN-B')
  })

  it('caches page images per width', async () => {
    await putCachedPage('brf-a', 'doc-1', 1, 720, blob('liten'))
    await putCachedPage('brf-a', 'doc-1', 1, 1440, blob('stor'))
    expect(await (await getCachedPage('brf-a', 'doc-1', 1, 720))!.text()).toBe('liten')
    expect(await (await getCachedPage('brf-a', 'doc-1', 1, 1440))!.text()).toBe('stor')
  })
})

describe('wipeTenant — what a förening switch must leave behind', () => {
  it('removes answers, page images and metadata for that tenant only', async () => {
    await saveEntry(entry('brf-a'))
    await saveEntry(entry('brf-b'))
    await putCachedPage('brf-a', 'doc-1', 1, 1080, blob('A'))
    await putCachedPage('brf-b', 'doc-1', 1, 1080, blob('B'))
    await metaCache.documents.write('brf-a', [])
    await metaCache.documents.write('brf-b', [])

    await wipeTenant('brf-a')

    expect(await listEntries('brf-a')).toHaveLength(0)
    expect(await getCachedPage('brf-a', 'doc-1', 1, 1080)).toBeUndefined()
    expect(await metaCache.documents.read('brf-a')).toBeUndefined()

    // The förening being switched TO is untouched.
    expect(await listEntries('brf-b')).toHaveLength(1)
    expect(await getCachedPage('brf-b', 'doc-1', 1, 1080)).toBeDefined()
  })

  it('does not wipe a tenant whose id merely shares a prefix', async () => {
    await saveEntry(entry('brf-a'))
    await saveEntry(entry('brf-a-2'))

    await wipeTenant('brf-a')

    expect(await listEntries('brf-a')).toHaveLength(0)
    expect(await listEntries('brf-a-2')).toHaveLength(1)
  })
})

describe('wipeEverything — what logout must leave behind', () => {
  it('removes every tenant’s answers, pages and metadata', async () => {
    await saveEntry(entry('brf-a'))
    await saveEntry(entry('brf-b'))
    await putCachedPage('brf-a', 'doc-1', 1, 1080, blob('A'))
    await putCachedPage('brf-b', 'doc-9', 3, 720, blob('B'))
    await metaCache.extraction.write('brf-a', 'doc-1', { document: {}, pages: [], chunks: [] } as never)

    await wipeEverything()

    expect(await listEntries('brf-a')).toHaveLength(0)
    expect(await listEntries('brf-b')).toHaveLength(0)
    expect(await getCachedPage('brf-a', 'doc-1', 1, 1080)).toBeUndefined()
    expect(await getCachedPage('brf-b', 'doc-9', 3, 720)).toBeUndefined()
    expect(await metaCache.extraction.read('brf-a', 'doc-1')).toBeUndefined()
  })
})

describe('clearJournal', () => {
  it('clears answers but keeps the offline page cache usable', async () => {
    await saveEntry(entry('brf-a'))
    await putCachedPage('brf-a', 'doc-1', 1, 1080, blob('A'))

    await clearJournal('brf-a')

    expect(await listEntries('brf-a')).toHaveLength(0)
    expect(await getCachedPage('brf-a', 'doc-1', 1, 1080)).toBeDefined()
  })
})
