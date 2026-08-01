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

/* The backend also returns a bearer `token` for programmatic clients (eval,
 * tests). It is deliberately NOT declared here: this app authenticates with
 * the httpOnly session cookie, and leaving the field off the type makes
 * "no token ever touches JavaScript" something the compiler enforces rather
 * than something a comment asks for. */
export type LoginResponse = MeResponse

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

/* --------------------------------------------------------- granskningsfynd
 *
 * Mirrors backend/app/integrations/models.py. A finding is something a human
 * decides on; this client only ever renders one. Nothing here re-derives a
 * verdict, and there is deliberately no type for a decision payload — see
 * api/client.ts.
 */

export type Verdict = 'matches' | 'possible_deviation' | 'cannot_be_verified'

export type FindingStatus = 'open' | 'approved' | 'dismissed' | 'corrected'

/** How the cited document was tied to the invoice's supplier. `partial` is
 * the weak one — the backend's own WEAK_STRENGTHS. */
export type AnchorStrength = 'org_number' | 'exact' | 'alias' | 'legal_form' | 'partial'

export interface VerifiedFact {
  label: string
  value: string
  /** `invoice` is a normalised field off the invoice; `document` is a value
   * read out of a passage that verified verbatim. Nothing inferred lands
   * here — that is what `suggestion` is for. */
  source: 'invoice' | 'document'
  /** Index into the finding's own `citations`, when there is one. */
  citation_index: number | null
}

export interface AliasProposal {
  invoice_name: string
  document_name: string
  document_id: string
  basis: string
}

export interface ReviewFinding {
  id: string
  tenant_id: string
  finding_type: string
  created_at: string

  invoice_id: string | null
  source_event_id: string | null

  verdict: Verdict
  /** Swedish, from the backend. The client keeps a fallback map but never a
   * second opinion. */
  verdict_label: string

  verified_facts: VerifiedFact[]
  suggestion: string
  suggested_by: string
  uncertainty: string | null

  /** Same type, same verification and same rects as an answer's citations. */
  citations: Citation[]

  anchor_strength: AnchorStrength | null
  anchor_note: string | null
  alias_proposal: AliasProposal | null

  status: FindingStatus
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
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
