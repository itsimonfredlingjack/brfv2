async function request(path, options = {}) {
  const response = await fetch(path, { credentials: 'include', ...options });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Keep statusText when the response is not JSON.
    }

    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

const jsonBody = (method, value) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(value),
});

export const api = {
  health: () => request('/api/health'),
  login: (email, password) => request('/api/auth/login', jsonBody('POST', { email, password })),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),

  listDocuments: (brfId) => request(`/api/brf/${brfId}/documents`),
  uploadDocument: (brfId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/api/brf/${brfId}/documents`, { method: 'POST', body: form });
  },
  deleteDocument: (brfId, documentId) => request(
    `/api/brf/${brfId}/documents/${documentId}`,
    { method: 'DELETE' },
  ),
  getExtraction: (brfId, documentId) => request(
    `/api/brf/${brfId}/documents/${documentId}/extraction`,
  ),
  pdfUrl: (brfId, documentId) => `/api/brf/${brfId}/documents/${documentId}/pdf`,
  ask: (brfId, question) => request(
    `/api/brf/${brfId}/ask`,
    jsonBody('POST', { question }),
  ),
  getSettings: (brfId) => request(`/api/brf/${brfId}/settings`),
  putSettings: (brfId, settings) => request(
    `/api/brf/${brfId}/settings`,
    jsonBody('PUT', settings),
  ),
};
