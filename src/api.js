// Thin client for the FastAPI backend (proxied at /api by Vite).

async function request(path, options = {}) {
  const res = await fetch(path, options);
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
  return res.json();
}

export const api = {
  health: () => request('/api/health'),
  listDocuments: () => request('/api/documents'),
  uploadDocument: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/api/documents', { method: 'POST', body: form });
  },
  deleteDocument: (id) => request(`/api/documents/${id}`, { method: 'DELETE' }),
  getExtraction: (id) => request(`/api/documents/${id}/extraction`),
  pdfUrl: (id) => `/api/documents/${id}/pdf`,
  ask: (question) =>
    request('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),
  getSettings: () => request('/api/settings'),
  putSettings: (settings) =>
    request('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),
  reset: () => request('/api/reset', { method: 'POST' }),
};
