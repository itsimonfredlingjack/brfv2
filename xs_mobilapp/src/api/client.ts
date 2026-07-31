import type {
  AskResponse,
  DocumentMeta,
  Extraction,
  Health,
  LoginResponse,
  MeResponse,
  PageWidth,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class OfflineError extends Error {
  constructor() {
    super('Ingen uppkoppling.')
    this.name = 'OfflineError'
  }
}

/** Generation runs on a self-hosted 12B; a slow answer is normal, not a
 * failure. This must stay comfortably longer than the backend's own patience
 * so the app never abandons a request the server is still working on. */
const ASK_TIMEOUT_MS = 180_000
const DEFAULT_TIMEOUT_MS = 20_000

async function request<T>(path: string, options: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let response: Response
  try {
    response = await fetch(path, {
      credentials: 'include',
      signal: controller.signal,
      ...options,
    })
  } catch (err) {
    if (!navigator.onLine) throw new OfflineError()
    throw new ApiError(err instanceof Error ? err.message : 'Nätverksfel.', 0)
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(detail || `HTTP ${response.status}`, response.status)
  }

  if (response.status === 204) return null as T
  return (await response.json()) as T
}

const jsonBody = (method: string, value: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value),
})

/* Path segments are encoded, never interpolated raw. `brfId` and `docId`
 * reach here from route parameters, i.e. from whatever a deep link put in the
 * address bar — a segment containing `/`, `?` or `..` would otherwise
 * re-point the request at a different endpoint. */
const seg = (value: string | number) => encodeURIComponent(String(value))

export const api = {
  health: () => request<Health>('/api/health'),

  login: (email: string, password: string) =>
    request<LoginResponse>('/api/auth/login', jsonBody('POST', { email, password })),

  logout: () => request<{ status: string }>('/api/auth/logout', { method: 'POST' }),

  me: () => request<MeResponse>('/api/auth/me'),

  listDocuments: (brfId: string) => request<DocumentMeta[]>(`/api/brf/${seg(brfId)}/documents`),

  getExtraction: (brfId: string, docId: string) =>
    request<Extraction>(`/api/brf/${seg(brfId)}/documents/${seg(docId)}/extraction`),

  ask: (brfId: string, question: string) =>
    request<AskResponse>(`/api/brf/${seg(brfId)}/ask`, jsonBody('POST', { question }), ASK_TIMEOUT_MS),

  pageImageUrl: (brfId: string, docId: string, page: number, width: PageWidth) =>
    `/api/brf/${seg(brfId)}/documents/${seg(docId)}/page/${seg(page)}?w=${seg(width)}`,
}
