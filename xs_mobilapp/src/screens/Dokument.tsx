import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { back } from '../app/router'
import { KallaSheet } from '../components/KallaSheet'
import type { KallaTarget } from '../components/KallaSheet'
import { Notice } from '../components/Notice'
import { ChevronLeft } from '../components/icons'
import type { DocumentMeta, Extraction } from '../api/types'
import { formatDate } from '../lib/format'
import { metaCache } from '../state/localStore'

export function Dokument({ brfId, documentId }: { brfId: string; documentId: string }) {
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [meta, setMeta] = useState<DocumentMeta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [target, setTarget] = useState<KallaTarget | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const cachedDocs = await metaCache.documents.read(brfId).catch(() => undefined)
      const cachedMeta = cachedDocs?.find((d) => d.id === documentId)
      if (cachedMeta && !cancelled) setMeta(cachedMeta)

      const cached = await metaCache.extraction.read(brfId, documentId).catch(() => undefined)
      if (cached && !cancelled) {
        setExtraction(cached)
        setMeta(cached.document)
      }

      try {
        const fresh = await api.getExtraction(brfId, documentId)
        if (cancelled) return
        setExtraction(fresh)
        setMeta(fresh.document)
        await metaCache.extraction.write(brfId, documentId, fresh).catch(() => {})
      } catch {
        if (cancelled) return
        if (!cached) setError('Dokumentet kunde inte hämtas.')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [brfId, documentId])

  const open = (page: number) => {
    if (!meta) return
    setTarget({ documentId, documentName: meta.name, page, citation: null })
  }

  return (
    <>
      <div className="screen">
        <button
          type="button"
          className="backlink"
          onClick={back}
        >
          <ChevronLeft size={16} />
          Bibliotek
        </button>

        {error && !meta ? (
          <div style={{ marginTop: 'var(--s5)' }}>
            <Notice tone="error" title="Kunde inte öppna dokumentet">
              {error}
            </Notice>
          </div>
        ) : (
          <>
            <h1 className="screen__title" style={{ marginTop: 'var(--s4)' }}>
              {meta?.name ?? 'Dokument'}
            </h1>
            <p className="screen__lede">
              {meta
                ? `${meta.pages} ${meta.pages === 1 ? 'sida' : 'sidor'} · uppladdat ${formatDate(meta.uploaded_at)}${
                    meta.source === 'scanned' ? ' · skannat original' : ''
                  }`
                : 'Läser in…'}
            </p>

            <div style={{ marginTop: 'var(--s5)' }}>
              <button type="button" className="btn btn--primary" onClick={() => open(1)} disabled={!meta}>
                Öppna dokumentet
              </button>
            </div>

            {extraction && (
              <section style={{ marginTop: 'var(--s6)' }}>
                <div className="label">Gå till sida</div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(56px, 1fr))',
                    gap: 'var(--s2)',
                    marginTop: 'var(--s3)',
                  }}
                >
                  {extraction.pages.map((page) => (
                    <button
                      key={page.number}
                      type="button"
                      className="pager__btn"
                      style={{ width: '100%' }}
                      onClick={() => open(page.number)}
                      aria-label={`Öppna sida ${page.number}`}
                    >
                      {page.number}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>

      {target && <KallaSheet brfId={brfId} target={target} onClose={() => setTarget(null)} />}
    </>
  )
}
