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
  score: number | null
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
  | 'citation_contradicted'

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

/* ---------------------------------------------------------- bevakningar
 *
 * Mirrors backend/app/watches/models.py. A watch is a dated obligation the
 * engine proposes and a human takes on; this client only ever renders one.
 * There is deliberately no type for a decision payload and none for a scan —
 * see api/client.ts.
 */

export type WatchKind =
  | 'notice_deadline'
  | 'expiry'
  | 'warranty'
  | 'inspection'
  | 'recurring_obligation'

export type WatchStatus = 'proposed' | 'approved' | 'dismissed' | 'done'

export type Recurrence = 'none' | 'monthly' | 'quarterly' | 'yearly' | 'biennial' | 'triennial'

/** Where a watch sits relative to the server's today. */
export type WatchBucket = 'overdue' | 'soon' | 'later' | 'recurring'

export interface Watch {
  id: string
  tenant_id: string
  kind: WatchKind
  status: WatchStatus

  /** Already written as an instruction, not as a category. Rendered as-is. */
  title: string
  /** `YYYY-MM-DD`. A calendar day, not an instant — see lib/format. */
  due_date: string

  /** What the contract's own arithmetic produced. Kept even after a human
   * moves the date; the two together are the audit trail. */
  derived_due_date: string
  derivation: string

  recurrence: Recurrence
  /** Empty means nobody is named yet. The view says "ej utsedd" — never blank,
   * and never in a way that suggests somebody has it. */
  responsible: string
  remind_lead_days: number

  /** Same type, same verbatim verification and same rects as an answer's. */
  citations: Citation[]
  source_document_id: string
  source_document_name: string

  created_at: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  succeeded_by: string | null

  /* Computed server-side, so the desktop and the phone cannot disagree about
   * what "snart" means — it is a function of each watch's own reminder lead
   * time, not of a window this client invents. */
  kind_label: string
  status_label: string
  remind_at: string
  bucket: WatchBucket
  days_left: number | null
  next_due_after: string | null
}

/** A time limit that was read but could not be dated. Not a watch: giving it a
 * date would mean inventing one. It is a real answer, and the missing fact is
 * usually one only a person has. */
export interface UnresolvedObligation {
  id: string
  tenant_id: string
  what: string
  why: string
  citations: Citation[]
  source_document_id: string
  source_document_name: string
  created_at: string
}

export interface WatchBoard {
  /** The day the buckets and `days_left` were computed against. */
  today: string
  proposed: Watch[]
  buckets: Record<WatchBucket, Watch[]>
  bucketLabels: Record<WatchBucket, string>
  kindLabels: Record<string, string>
  statusLabels: Record<string, string>
  settled: Watch[]
  unresolved: UnresolvedObligation[]
}

/* ------------------------------------------------------------- uppgifter
 *
 * Mirrors backend/app/tasks/models.py. A task is where a human turned a
 * finding, a watch or a piece of incoming post into work: owner, deadline,
 * status, an append-only history, and the original evidence carried along.
 *
 * There is deliberately no type for a create, an update or a comment payload.
 * The engine cannot create a task — creating one *is* the decision — and
 * neither can this client: see api/client.ts.
 */

export type TaskStatus = 'open' | 'in_progress' | 'blocked' | 'done' | 'cancelled'

export type TaskOriginKind =
  | 'finding'
  | 'watch'
  | 'source_event'
  /** The invoice case as a whole, as opposed to one finding inside it. */
  | 'invoice_case'
  | 'manual'

export type TaskEventKind =
  | 'created'
  | 'status_changed'
  | 'assigned'
  | 'due_changed'
  | 'noted'
  | 'edited'

export interface TaskOrigin {
  kind: TaskOriginKind
  /** The finding, watch or source event this came out of. Empty for work that
   * started in a meeting rather than in a document. */
  ref_id: string
  /** What that thing said at the time — a copy, so a re-run finding or a
   * re-dated watch cannot silently re-describe work already taken on. */
  label: string
  kind_label: string
}

/** One thing that happened to a task. Written once, never edited. */
export interface TaskEvent {
  id: string
  at: string
  by: string
  kind: TaskEventKind
  /** The change in plain values rather than two snapshots to diff. Both empty
   * for a plain comment. */
  from_value: string
  to_value: string
  note: string
  kind_label: string
}

export interface Task {
  id: string
  tenant_id: string

  title: string
  description: string
  status: TaskStatus
  /** Empty means nobody is named yet. The view says "ej utsedd" — never blank,
   * and never in a way that suggests somebody has it. */
  responsible: string
  /** `YYYY-MM-DD`, or null for work nobody has scheduled. Unscheduled is not
   * the same as urgent, and not the same as late. */
  due_date: string | null

  origin: TaskOrigin
  /** Carried from the origin when the task was created, so the passage behind
   * the work still opens at the right page months later. */
  citations: Citation[]
  source_document_id: string
  source_document_name: string

  created_by: string
  created_at: string
  /** Append-only, oldest first. The audit trail and the activity feed at once;
   * there is no second log to keep in step with it. */
  activity: TaskEvent[]

  /* Computed server-side, for the same reason the watch board's buckets are:
   * the desktop and the phone must not be able to disagree about what counts
   * as overdue. */
  status_label: string
  active: boolean
  overdue: boolean
  days_left: number | null
  last_activity_at: string
}

export interface TaskBoard {
  /** The day `overdue` and `days_left` were computed against. */
  today: string
  /** Already ordered by the server: overdue first, then by date, undated last.
   * This client renders that order and never re-sorts it. */
  active: Task[]
  done: Task[]
  cancelled: Task[]
  statusLabels: Record<string, string>
  originLabels: Record<string, string>
  /** `unassigned` is the number that quietly grows: work taken on that nobody
   * has been named for. */
  counts: { active: number; overdue: number; unassigned: number }
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
