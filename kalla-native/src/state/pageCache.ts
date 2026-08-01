import { Directory, File, Paths } from 'expo-file-system'
import { Platform } from 'react-native'

import type { PageWidth } from '../api/types'

/* Rasterized page cache. One directory per tenant (`brf_id`), so a tenant
 * wipe is a single directory delete instead of a key-prefix scan — the
 * filesystem enforces the same isolation boundary xs_mobilapp's IndexedDB
 * key-prefix convention enforces on the web (state/localStore.ts there).
 * Pages are content-addressed by document/page/width and never expire on
 * their own: the backend serves them `Cache-Control: private, no-store`
 * specifically because this on-device copy is the only one allowed to
 * survive, and only until logout or tenant switch.
 *
 * The shipped target is Android; `expo-file-system`'s File/Directory API
 * has no web implementation, and even constructing one at module load time
 * throws under web/SSR. Every constructor call below is therefore lazy and
 * gated on `Platform.OS !== 'web'` — never at module scope. */

let root: Directory | null = null
function rootDir(): Directory {
  if (!root) root = new Directory(Paths.cache, 'kalla-pages')
  return root
}

function tenantDir(brfId: string): Directory {
  return new Directory(rootDir(), brfId)
}

function pageFile(brfId: string, docId: string, page: number, width: PageWidth): File {
  return new File(tenantDir(brfId), `${docId}_${page}_${width}.png`)
}

export interface CachedPage {
  uri: string
  fromCache: boolean
}

/** Cache-first fetch of one rasterized page. On web this just proxies the
 * network URL — the browser's own HTTP cache stands in, purely so `expo
 * start --web` stays usable as a layout-and-motion preview during
 * development. */
export async function getPage(
  brfId: string,
  docId: string,
  page: number,
  width: PageWidth,
  fetchUrl: string,
): Promise<CachedPage> {
  if (Platform.OS === 'web') return { uri: fetchUrl, fromCache: false }

  const file = pageFile(brfId, docId, page, width)
  if (file.exists) return { uri: file.uri, fromCache: true }

  const response = await fetch(fetchUrl, { credentials: 'include' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const bytes = new Uint8Array(await response.arrayBuffer())

  const dir = tenantDir(brfId)
  if (!dir.exists) dir.create({ intermediates: true })
  file.write(bytes)
  return { uri: file.uri, fromCache: false }
}

export async function wipeTenantPages(brfId: string): Promise<void> {
  if (Platform.OS === 'web') return
  const dir = tenantDir(brfId)
  if (dir.exists) dir.delete()
}

export async function wipeAllPages(): Promise<void> {
  if (Platform.OS === 'web') return
  if (rootDir().exists) rootDir().delete()
}
