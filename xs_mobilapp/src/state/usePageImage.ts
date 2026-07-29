import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { PageWidth } from '../api/types'
import { getCachedPage, putCachedPage } from './localStore'

interface PageImageState {
  url: string | null
  loading: boolean
  /** Set only when the page can be shown neither from cache nor network. */
  error: string | null
  fromCache: boolean
}

/**
 * A rasterized page, cache-first.
 *
 * The blob is kept in IndexedDB rather than left to the HTTP cache so that
 * "pages I have already looked at" is a promise the app can actually keep
 * offline, instead of a hope about eviction policy.
 */
export function usePageImage(
  brfId: string,
  docId: string | null,
  page: number,
  width: PageWidth,
): PageImageState {
  const [state, setState] = useState<PageImageState>({
    url: null,
    loading: true,
    error: null,
    fromCache: false,
  })

  useEffect(() => {
    if (!docId) {
      setState({ url: null, loading: false, error: null, fromCache: false })
      return undefined
    }

    let cancelled = false
    let objectUrl: string | null = null

    const publish = (blob: Blob, fromCache: boolean) => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(blob)
      setState({ url: objectUrl, loading: false, error: null, fromCache })
    }

    async function load() {
      setState({ url: null, loading: true, error: null, fromCache: false })

      const cached = await getCachedPage(brfId, docId!, page, width).catch(() => undefined)
      if (cached) {
        publish(cached, true)
        return
      }

      try {
        const response = await fetch(api.pageImageUrl(brfId, docId!, page, width), {
          credentials: 'include',
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const blob = await response.blob()
        if (cancelled) return
        await putCachedPage(brfId, docId!, page, width, blob).catch(() => {
          // A full quota must not stop the page from being shown.
        })
        publish(blob, false)
      } catch {
        if (cancelled) return
        setState({
          url: null,
          loading: false,
          error: navigator.onLine
            ? 'Sidan kunde inte hämtas.'
            : 'Sidan finns inte nedladdad och du är offline.',
          fromCache: false,
        })
      }
    }

    void load()

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [brfId, docId, page, width])

  return state
}
