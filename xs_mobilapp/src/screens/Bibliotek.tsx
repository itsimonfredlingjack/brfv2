import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { navigate } from '../app/router'
import { Notice } from '../components/Notice'
import { ChevronRight, DocIcon } from '../components/icons'
import type { DocumentMeta } from '../api/types'
import { formatDate } from '../lib/format'
import { metaCache } from '../state/localStore'
import { useOnline } from '../state/useOnline'

export function Bibliotek({ brfId }: { brfId: string }) {
  const online = useOnline()
  const [documents, setDocuments] = useState<DocumentMeta[] | null>(null)
  const [stale, setStale] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const cached = await metaCache.documents.read(brfId).catch(() => undefined)
      if (cached && !cancelled) {
        setDocuments(cached)
        setStale(true)
      }
      try {
        const fresh = await api.listDocuments(brfId)
        if (cancelled) return
        setDocuments(fresh)
        setStale(false)
        await metaCache.documents.write(brfId, fresh).catch(() => {})
      } catch {
        if (cancelled) return
        if (!cached) setError('Dokumentlistan kunde inte hämtas.')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [brfId])

  if (documents === null && !error) {
    return (
      <div className="screen">
        <h1 className="screen__title">Bibliotek</h1>
        <div className="list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 76 }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="screen">
      <h1 className="screen__title">Bibliotek</h1>
      <p className="screen__lede">
        {documents?.length
          ? `${documents.length} dokument i föreningen.`
          : 'Föreningens dokument.'}
        {stale && !online && ' Visas från telefonens kopia.'}
      </p>

      {error && (
        <div style={{ marginTop: 'var(--s5)' }}>
          <Notice tone="error" title="Kunde inte hämta biblioteket">
            {error}
          </Notice>
        </div>
      )}

      {documents !== null && documents.length === 0 && (
        <div className="empty">
          <div className="empty__title">Föreningen har inga dokument ännu.</div>
          <p className="empty__body">
            En administratör laddar upp stadgar, protokoll och avtal i webbappen. Därefter går de
            att fråga om här.
          </p>
        </div>
      )}

      <div className="list">
        {documents?.map((document) => (
          <button
            key={document.id}
            type="button"
            className="row"
            onClick={() => navigate(`/dokument/${document.id}`)}
          >
            <DocIcon className="row__chevron" />
            <span className="row__body">
              <span className="row__title">{document.name}</span>
              <span className="row__meta">
                {document.pages} {document.pages === 1 ? 'sida' : 'sidor'} ·{' '}
                {formatDate(document.uploaded_at)}
              </span>
            </span>
            {document.source === 'scanned' && <span className="chip chip--scanned">skannat</span>}
            <ChevronRight className="row__chevron" />
          </button>
        ))}
      </div>
    </div>
  )
}
