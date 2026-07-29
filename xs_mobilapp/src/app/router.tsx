import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'

/* A ~60-line router. The app has seven routes and one sheet; a routing
 * library would be more code than the thing it routes. Real history entries,
 * so the OS back gesture always means back. */

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')

const NAV_EVENT = 'kalla:navigate'
const listeners = new Set<() => void>()

function emit() {
  for (const fn of listeners) fn()
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  window.addEventListener('popstate', fn)
  window.addEventListener(NAV_EVENT, fn)
  return () => {
    listeners.delete(fn)
    window.removeEventListener('popstate', fn)
    window.removeEventListener(NAV_EVENT, fn)
  }
}

function currentPath(): string {
  const path = window.location.pathname
  const stripped = path.startsWith(BASE) ? path.slice(BASE.length) : path
  return stripped === '' ? '/' : stripped
}

/* Scroll restoration.
 *
 * Going forward starts a screen at the top; coming BACK should return you to
 * where you were looking. Losing your place in the answer list every time you
 * close an answer is the kind of small friction that makes an app feel like a
 * web page. */
if (typeof history !== 'undefined' && 'scrollRestoration' in history) {
  history.scrollRestoration = 'manual'
}

const scrollPositions = new Map<string, number>()
let entryCounter = 0

function entryKey(): string {
  const state = window.history.state as { key?: string } | null
  if (state?.key) return state.key
  const key = `e${entryCounter += 1}`
  window.history.replaceState({ ...(state ?? {}), key }, '')
  return key
}

function rememberScroll() {
  scrollPositions.set(entryKey(), window.scrollY)
}

export function navigate(to: string, options: { replace?: boolean } = {}) {
  rememberScroll()
  const url = `${BASE}${to}`
  const key = `e${entryCounter += 1}`
  if (options.replace) window.history.replaceState({ key }, '', url)
  else window.history.pushState({ key }, '', url)
  emit()
  window.dispatchEvent(new Event(NAV_EVENT))
}

export function back() {
  rememberScroll()
  window.history.back()
}

interface RouterValue {
  path: string
  navigate: typeof navigate
  back: typeof back
}

const RouterContext = createContext<RouterValue | null>(null)

export function RouterProvider({ children }: { children: ReactNode }) {
  const path = useSyncExternalStore(subscribe, currentPath, () => '/')

  useEffect(() => {
    // Restore where this history entry was left, or start at the top for a
    // screen being opened for the first time. rAF so it lands after the new
    // screen has actually laid out and is tall enough to scroll.
    const remembered = scrollPositions.get(entryKey()) ?? 0
    const frame = requestAnimationFrame(() => window.scrollTo(0, remembered))
    return () => cancelAnimationFrame(frame)
  }, [path])

  const value = useMemo(() => ({ path, navigate, back }), [path])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext)
  if (!value) throw new Error('useRouter utanför RouterProvider')
  return value
}

/**
 * Match `/dokument/:id` style patterns. Returns the params, or null.
 */
export function matchRoute(pattern: string, path: string): Record<string, string> | null {
  const patternParts = pattern.split('/').filter(Boolean)
  const pathParts = path.split('/').filter(Boolean)
  if (patternParts.length !== pathParts.length) return null

  const params: Record<string, string> = {}
  for (let i = 0; i < patternParts.length; i += 1) {
    const p = patternParts[i]!
    const actual = pathParts[i]!
    if (p.startsWith(':')) params[p.slice(1)] = decodeURIComponent(actual)
    else if (p !== actual) return null
  }
  return params
}

/** An anchor that keeps real link semantics (middle-click, long-press). */
export function Link({
  to,
  children,
  className,
  ...rest
}: { to: string; children: ReactNode; className?: string } & Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  'href'
>) {
  const onClick = useCallback(
    (event: React.MouseEvent<HTMLAnchorElement>) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
      event.preventDefault()
      navigate(to)
    },
    [to],
  )
  return (
    <a href={`${BASE}${to}`} onClick={onClick} className={className} {...rest}>
      {children}
    </a>
  )
}
