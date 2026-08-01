import AsyncStorage from '@react-native-async-storage/async-storage'

import type { Citation, DocumentMeta, Extraction, RefusalReason, RejectedCitation, RetrievalHit } from '../api/types'

/* On-device state. Every key is prefixed with the tenant's brf_id, and
 * logging out or switching förening wipes that prefix before the next
 * screen renders. The backend's adversarial isolation suite proves BRF A
 * can never reach BRF B's content server-side; an un-namespaced client
 * cache would hand that leak straight back. Treat the prefix as a security
 * boundary, not tidiness. Ported from xs_mobilapp/src/state/localStore.ts. */

const JOURNAL_PREFIX = 'kalla.journal.'
const META_DOCS_PREFIX = 'kalla.meta.documents.'
const META_EXTRACTION_PREFIX = 'kalla.meta.extraction.'

/** Answers older than this are pruned on read. They contain verbatim
 * document text, so they are personal data sitting on someone's phone. */
export const RETENTION_DAYS = 30
const RETENTION_MS = RETENTION_DAYS * 24 * 60 * 60 * 1000

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
  retrieval: RetrievalHit[]
  provider: string
  model: string
}

export function newEntryId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

const entryKey = (brfId: string, id: string) => `${JOURNAL_PREFIX}${brfId}::${id}`

export async function saveEntry(entry: JournalEntry): Promise<void> {
  await AsyncStorage.setItem(entryKey(entry.brfId, entry.id), JSON.stringify(entry))
}

/** Newest first, expired entries removed as a side effect of reading. */
export async function listEntries(brfId: string): Promise<JournalEntry[]> {
  const allKeys = await AsyncStorage.getAllKeys()
  const prefix = `${JOURNAL_PREFIX}${brfId}::`
  const mine = allKeys.filter((k) => k.startsWith(prefix))
  if (mine.length === 0) return []

  const pairs = await AsyncStorage.multiGet(mine)
  const cutoff = Date.now() - RETENTION_MS
  const kept: JournalEntry[] = []
  const expired: string[] = []

  for (const [key, raw] of pairs) {
    if (!raw) continue
    try {
      const value = JSON.parse(raw) as JournalEntry
      if (typeof value.createdAt !== 'number') continue
      if (value.createdAt < cutoff) expired.push(key)
      else kept.push(value)
    } catch {
      expired.push(key)
    }
  }

  if (expired.length) await AsyncStorage.multiRemove(expired)
  return kept.sort((a, b) => b.createdAt - a.createdAt)
}

export async function getEntry(brfId: string, id: string): Promise<JournalEntry | undefined> {
  const raw = await AsyncStorage.getItem(entryKey(brfId, id))
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as JournalEntry
  } catch {
    return undefined
  }
}

async function wipePrefix(prefix: string): Promise<void> {
  const allKeys = await AsyncStorage.getAllKeys()
  const mine = allKeys.filter((k) => k.startsWith(prefix))
  if (mine.length) await AsyncStorage.multiRemove(mine)
}

export async function clearJournal(brfId: string): Promise<void> {
  await wipePrefix(`${JOURNAL_PREFIX}${brfId}::`)
}

// --------------------------------------------------------------- meta cache

/** Document list and extraction, cached so Bibliotek and already-seen pages
 * stay readable with no connection. */
export const metaCache = {
  documents: {
    read: async (brfId: string): Promise<DocumentMeta[] | undefined> => {
      const raw = await AsyncStorage.getItem(`${META_DOCS_PREFIX}${brfId}`)
      return raw ? (JSON.parse(raw) as DocumentMeta[]) : undefined
    },
    write: (brfId: string, docs: DocumentMeta[]) =>
      AsyncStorage.setItem(`${META_DOCS_PREFIX}${brfId}`, JSON.stringify(docs)),
  },
  extraction: {
    read: async (brfId: string, docId: string): Promise<Extraction | undefined> => {
      const raw = await AsyncStorage.getItem(`${META_EXTRACTION_PREFIX}${brfId}::${docId}`)
      return raw ? (JSON.parse(raw) as Extraction) : undefined
    },
    write: (brfId: string, docId: string, value: Extraction) =>
      AsyncStorage.setItem(`${META_EXTRACTION_PREFIX}${brfId}::${docId}`, JSON.stringify(value)),
  },
}

// -------------------------------------------------------------------- wipes

/** Everything this device holds for one förening except page images (see
 * pageCache.wipeTenant) — runs on tenant switch. */
export async function wipeTenantJournalAndMeta(brfId: string): Promise<void> {
  await Promise.all([
    wipePrefix(`${JOURNAL_PREFIX}${brfId}::`),
    AsyncStorage.removeItem(`${META_DOCS_PREFIX}${brfId}`),
    wipePrefix(`${META_EXTRACTION_PREFIX}${brfId}::`),
  ])
}

/** Everything, for every förening — runs on logout, unconditionally, even if
 * the logout request to the server failed. */
export async function wipeEverythingJournalAndMeta(): Promise<void> {
  const allKeys = await AsyncStorage.getAllKeys()
  const mine = allKeys.filter(
    (k) => k.startsWith(JOURNAL_PREFIX) || k.startsWith(META_DOCS_PREFIX) || k.startsWith(META_EXTRACTION_PREFIX),
  )
  if (mine.length) await AsyncStorage.multiRemove(mine)
}
