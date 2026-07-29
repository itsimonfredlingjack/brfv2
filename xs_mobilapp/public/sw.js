/* Källa service worker — app shell only.
 *
 * Two rules, both load-bearing:
 *
 *   1. SAME ORIGIN ONLY. A cross-origin request in this app is a bug or an
 *      attack, never a feature. Anything else is passed straight through
 *      untouched and never cached.
 *   2. NEVER TOUCH /api. Documents, answers and page images are tenant data
 *      with their own tenant-namespaced store in IndexedDB, which logout
 *      wipes. A second, invisible cache here would sit outside that wipe —
 *      exactly the cross-tenant residue the app is built to avoid.
 */

/* Cache name carries the release, taken from the ?v= this worker was
 * registered with (src/main.tsx). Without it every release would reuse one
 * cache name, the activate handler below would never find an old cache to
 * delete, and superseded hashed assets would accumulate forever. */
const VERSION = new URL(self.location.href).searchParams.get('v') || 'dev'
const CACHE = `kalla-shell-${VERSION}`
const BASE = new URL('./', self.location).pathname

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(BASE)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith('kalla-shell-') && name !== CACHE)
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return // rule 1
  if (url.pathname.startsWith('/api/')) return // rule 2

  // Navigations: network first so a deploy is picked up, shell fallback so a
  // cold launch offline still opens the app.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(CACHE).then((cache) => cache.put(BASE, copy))
          return response
        })
        .catch(() => caches.match(BASE).then((hit) => hit ?? Response.error())),
    )
    return
  }

  // Hashed build assets: cache first, they never change under a given name.
  event.respondWith(
    caches.match(request).then((hit) => {
      if (hit) return hit
      return fetch(request).then((response) => {
        if (response.ok && response.type === 'basic') {
          const copy = response.clone()
          caches.open(CACHE).then((cache) => cache.put(request, copy))
        }
        return response
      })
    }),
  )
})
