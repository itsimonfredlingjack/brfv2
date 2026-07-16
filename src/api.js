// Thin client for the FastAPI backend (proxied at /api by Vite).
// All requests send cookies (credentials: 'include') so the HttpOnly session
// cookie set by /api/auth/login authenticates every tenant-scoped call.
// Tenant routes are /api/brf/:brfId/... — the caller passes the active brfId.

async function request(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep statusText */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

const jsonBody = (method, obj) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(obj),
});

export const api = {
  health: () => request('/api/health'),

  // ---- auth ----
  login: (email, password) => request('/api/auth/login', jsonBody('POST', { email, password })),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),

  // ---- tenant-scoped ----
  listDocuments: (brfId) => request(`/api/brf/${brfId}/documents`),
  uploadDocument: (brfId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/api/brf/${brfId}/documents`, { method: 'POST', body: form });
  },
  deleteDocument: (brfId, id) => request(`/api/brf/${brfId}/documents/${id}`, { method: 'DELETE' }),
  getExtraction: (brfId, id) => request(`/api/brf/${brfId}/documents/${id}/extraction`),
  pdfUrl: (brfId, id) => `/api/brf/${brfId}/documents/${id}/pdf`,
  ask: (brfId, question) => request(`/api/brf/${brfId}/ask`, jsonBody('POST', { question })),
  getSettings: (brfId) => request(`/api/brf/${brfId}/settings`),
  putSettings: (brfId, settings) => request(`/api/brf/${brfId}/settings`, jsonBody('PUT', settings)),

  // dev only
  reset: () => request('/api/reset', { method: 'POST' }),
};
