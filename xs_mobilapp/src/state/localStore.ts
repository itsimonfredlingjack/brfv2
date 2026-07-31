import { clear, createStore, del, entries, get, keys, set } from 'idb-keyval'

import type { Citation, DocumentMeta, Extraction, RefusalReason, RejectedCitation } from '../api/types'

/* On-device state. Three stores, one rule:
 *
 *   EVERY key is prefixed with the tenant's brf_id, and logging out or
 *   switching förening wipes that prefix before the next screen renders.
 *
 * The backend's adversarial isolation suite proves BRF A can never reach BRF
 * B's content. An un-namespaced client cache would hand that leak straight
 * back. Treat the prefix as a security boundary, not as tidiness — there is a
 * test that fails if it slips (localStore.test.ts).
 */

const journalStore = createStore('kalla-journal', 'entries')
const pageStore = createStore('kalla-pages', 'blobs')
const metaStore = createStore('kalla-meta', 'json')

const ALL_STORES = [journalStore, pageStore, metaStore]

/** Answers older than this are pruned on read. They contain verbatim
 * document text, so they are personal data sitting on someone's phone. */
export const RETENTION_DAYS = 30
const RETENTION_MS = RETENTION_DAYS * 24 * 60 * 60 * 1000

export const tenantKey = (brfId: string, ...parts: (string | number)[]) =>
  [brfId, ...parts].join('::')

const belongsTo = (key: IDBValidKey, brfId: string): key is string =>
  typeof key === 'string' && key.startsWith(`${brfId}::`)

// ------------------------------------------------------------------ journal

export interface JournalEntry {
  id: string
  brfId: string
  question: string
  createdAt: number
  answer: string
  refusal: boolean
  refusalReason: RefusalReason | null
  warning: string | null
  citations: Citation[]
  rejected: RejectedCitation[]
  provider: string
  model: string
}

export function newEntryId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export async function saveEntry(entry: JournalEntry): Promise<void> {
  await set(tenantKey(entry.brfId, 'answer', entry.id), entry, journalStore)
}

/** Newest first, expired entries removed as a side effect of reading. */
export async function listEntries(brfId: string): Promise<JournalEntry[]> {
  const all = await entries<string, JournalEntry>(journalStore)
  const cutoff = Date.now() - RETENTION_MS
  const kept: JournalEntry[] = []
  const expired: string[] = []

  for (const [key, value] of all) {
    if (!belongsTo(key, brfId)) continue
    if (!value || typeof value.createdAt !== 'number') continue
    if (value.createdAt < cutoff) expired.push(key)
    else kept.push(value)
  }

  await Promise.all(expired.map((key) => del(key, journalStore)))
  return kept.sort((a, b) => b.createdAt - a.createdAt)
}

export function getEntry(brfId: string, id: string): Promise<JournalEntry | undefined> {
  return get<JournalEntry>(tenantKey(brfId, 'answer', id), journalStore)
}

export async function clearJournal(brfId: string): Promise<void> {
  await wipeStorePrefix(journalStore, brfId)
}

// --------------------------------------------------------------- page cache

/* Stored as raw bytes rather than as a Blob. Blob-in-IndexedDB has a
 * patchier structured-clone history than ArrayBuffer (and is unclonable
 * under jsdom, which would have left the isolation tests below unable to
 * inspect what they are asserting about). Reconstructing the Blob on read
 * costs nothing. */
interface CachedPage {
  bytes: ArrayBuffer
  type: string
}

export async function getCachedPage(
  brfId: string,
  docId: string,
  page: number,
  width: number,
): Promise<Blob | undefined> {
  const record = await get<CachedPage>(tenantKey(brfId, 'page', docId, page, width), pageStore)
  if (!record?.bytes) return undefined
  return new Blob([record.bytes], { type: record.type || 'image/png' })
}

export async function putCachedPage(
  brfId: string,
  docId: string,
  page: number,
  width: number,
  blob: Blob,
): Promise<void> {
  const record: CachedPage = { bytes: await blob.arrayBuffer(), type: blob.type }
  await set(tenantKey(brfId, 'page', docId, page, width), record, pageStore)
}

// --------------------------------------------------------------- meta cache

/** Document list and extraction, cached so Bibliotek and already-seen pages
 * stay readable with no connection. */
export const metaCache = {
  documents: {
    read: (brfId: string) => get<DocumentMeta[]>(tenantKey(brfId, 'documents'), metaStore),
    write: (brfId: string, docs: DocumentMeta[]) =>
      set(tenantKey(brfId, 'documents'), docs, metaStore),
  },
  extraction: {
    read: (brfId: string, docId: string) =>
      get<Extraction>(tenantKey(brfId, 'extraction', docId), metaStore),
    write: (brfId: string, docId: string, value: Extraction) =>
      set(tenantKey(brfId, 'extraction', docId), value, metaStore),
  },
}

// -------------------------------------------------------------------- wipes

async function wipeStorePrefix(store: ReturnType<typeof createStore>, brfId: string) {
  const all = await keys(store)
  await Promise.all(all.filter((k) => belongsTo(k, brfId)).map((k) => del(k, store)))
}

/** Everything this device holds for one förening. Runs on tenant switch. */
export async function wipeTenant(brfId: string): Promise<void> {
  await Promise.all(ALL_STORES.map((store) => wipeStorePrefix(store, brfId)))
}

/** Everything, for every förening. Runs on logout — unconditionally, even if
 * the logout request to the server failed. */
export async function wipeEverything(): Promise<void> {
  await Promise.all(ALL_STORES.map((store) => clear(store)))
}
