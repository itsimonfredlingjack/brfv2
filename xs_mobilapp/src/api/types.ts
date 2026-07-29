/* Mirrors backend/app/schemas.py. Kept deliberately narrow: this client
 * renders what the backend verified and never re-decides any of it. */

export type Role = 'member' | 'admin'

export interface User {
  id: string
  email: string
  name?: string
}

export interface Membership {
  brf_id: string
  name: string
  role: Role
}

export interface MeResponse {
  user: User
  memberships: Membership[]
}

export interface LoginResponse extends MeResponse {
  token: string
}

export interface DocumentMeta {
  id: string
  name: string
  pages: number
  words: number
  chunks: number
  uploaded_at: string
  source: 'digital' | 'scanned'
  corpus_origin: string
}

export interface PageDims {
  number: number
  width: number
  height: number
  words: number
}

export interface Extraction {
  document: DocumentMeta
  pages: PageDims[]
  chunks: { id: string; page: number; preview: string; words: number }[]
}

export interface Citation {
  document_id: string
  document_name: string
  page: number
  quote: string
  quotes: string[]
  chunk_id: string
  /** [x0, y0, x1, y1] in PDF points, TOP-LEFT origin. */
  rects: number[][]
  score: number
  approximate: boolean
  corpus_origin: string | null
}

export type RefusalReason =
  | 'no_documents'
  | 'low_relevance'
  | 'insufficient_data'
  | 'grounding_failed'
  | 'provider_error'
  | 'numeric_grounding_failed'

export type RejectReason =
  | 'quote_not_found'
  | 'provenance_mismatch'
  | 'bbox_out_of_bounds'
  | 'unknown_chunk'
  | 'too_many_spans'

export interface RejectedCitation {
  chunk_id: string
  quote: string
  reason: RejectReason
}

export interface AskResponse {
  answer: string
  refusal: boolean
  refusal_reason: RefusalReason | null
  warning: string | null
  citations: Citation[]
  rejected_citations: RejectedCitation[]
  provider: string
  model: string
}

export interface Health {
  status: string
  mode: string
  llm_provider: string
  embedding_provider: string
  tenants: number
  llm: {
    provider: string
    model: string
    display_name: string
    runtime_label: string
    ready: boolean
  }
}

/** Page widths the backend will rasterize — a closed allowlist (main.py). */
export const PAGE_WIDTHS = [720, 1080, 1440] as const
export type PageWidth = (typeof PAGE_WIDTHS)[number]
