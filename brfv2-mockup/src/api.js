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

// Incoming source events, read-only invoice snapshots and review findings.
// Tenant-scoped like everything else in `api`: the brf_id in the path is what
// the backend resolves an authenticated membership against.
export const integrationsApi = {
  format: (brfId) => request(`/api/brf/${brfId}/integrations/format`),

  // Live connections. Configuring where to read and signing in to it are two
  // separate calls because they are two separate human acts — an administrator
  // may point the installation at a mailbox today and sign in tomorrow.
  connections: (brfId) => request(`/api/brf/${brfId}/integrations/connections`),
  configureGraph: (brfId, config) => request(
    `/api/brf/${brfId}/integrations/connections/microsoft-graph`,
    jsonBody('PUT', config),
  ),
  configureFortnox: (brfId, config) => request(
    `/api/brf/${brfId}/integrations/connections/fortnox`,
    jsonBody('PUT', config),
  ),
  beginLogin: (brfId, provider) => request(
    `/api/brf/${brfId}/integrations/connections/${provider}/login`,
    { method: 'POST' },
  ),
  pollLogin: (brfId, provider) => request(
    `/api/brf/${brfId}/integrations/connections/${provider}/login/poll`,
    { method: 'POST' },
  ),
  // An operator pastes the bare code as often as the whole redirect address.
  // The backend pulls `code` and `state` out of either, so whatever was pasted
  // goes in as `code` and nothing is parsed here.
  completeLogin: (brfId, provider, pasted) => request(
    `/api/brf/${brfId}/integrations/connections/${provider}/login/complete`,
    jsonBody('POST', { code: pasted, state: '' }),
  ),
  disconnect: (brfId, provider) => request(
    `/api/brf/${brfId}/integrations/connections/${provider}`,
    { method: 'DELETE' },
  ),

  listMailboxMessages: (brfId, { limit = 25, onlyWithAttachments = true } = {}) => request(
    `/api/brf/${brfId}/integrations/mailbox/messages`
    + `?limit=${limit}&onlyWithAttachments=${onlyWithAttachments}`,
  ),
  importMailboxMessage: (brfId, messageId) => request(
    `/api/brf/${brfId}/integrations/mailbox/messages/${encodeURIComponent(messageId)}/import`,
    { method: 'POST' },
  ),

  listSourceEvents: (brfId) => request(`/api/brf/${brfId}/integrations/source-events`),
  importSourceEvent: (brfId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/api/brf/${brfId}/integrations/source-events`, {
      method: 'POST',
      body: form,
    });
  },
  decideSourceEvent: (brfId, eventId, decision) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}/decision`,
    jsonBody('POST', decision),
  ),
  deleteSourceEvent: (brfId, eventId) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}`,
    { method: 'DELETE' },
  ),

  // Adoption: the attachment stays exactly where it is, and stops being
  // excluded from the evidence the review may cite. The note is required by
  // the route, so the form asks for it rather than sending something invented.
  archiveAttachment: (brfId, eventId, attachmentId, note) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}`
    + `/attachments/${attachmentId}/archive`,
    jsonBody('POST', { note }),
  ),
  withdrawAttachment: (brfId, eventId, attachmentId) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}`
    + `/attachments/${attachmentId}/archive`,
    { method: 'DELETE' },
  ),

  availableInvoices: (brfId, source = 'fixture') => request(
    `/api/brf/${brfId}/integrations/available-invoices?source=${encodeURIComponent(source)}`,
  ),
  listInvoices: (brfId) => request(`/api/brf/${brfId}/integrations/invoices`),
  importInvoice: (brfId, externalRef, source = 'fixture') => request(
    `/api/brf/${brfId}/integrations/invoices`,
    jsonBody('POST', { external_ref: externalRef, source }),
  ),
  mappingPreview: (brfId, externalRef) => request(
    `/api/brf/${brfId}/integrations/invoices/mapping-preview`
    + `?external_ref=${encodeURIComponent(externalRef)}`,
  ),
  reviewInvoice: (brfId, invoiceId) => request(
    `/api/brf/${brfId}/integrations/invoices/${invoiceId}/review`,
    { method: 'POST' },
  ),

  listFindings: (brfId) => request(`/api/brf/${brfId}/integrations/findings`),
  decideFinding: (brfId, findingId, decision) => request(
    `/api/brf/${brfId}/integrations/findings/${findingId}/decision`,
    jsonBody('POST', decision),
  ),

  listSupplierAliases: (brfId) => request(`/api/brf/${brfId}/integrations/supplier-aliases`),
  addSupplierAlias: (brfId, alias) => request(
    `/api/brf/${brfId}/integrations/supplier-aliases`,
    jsonBody('POST', alias),
  ),
  deleteSupplierAlias: (brfId, aliasId) => request(
    `/api/brf/${brfId}/integrations/supplier-aliases/${aliasId}`,
    { method: 'DELETE' },
  ),
};

// The invoice workspace: one invoice as one case.
//
// Two reads serve the whole area — the queue and one case — because the
// alternative is a screen that renders in stages and can briefly show a row
// whose badge disagrees with its buttons.
//
// Nothing in here writes to an accounting system. `importInvoice` and `refresh`
// are read-only GETs on the other side of the adapter boundary; the review
// status, the comments and the responsible person are this association's own
// record and exist nowhere else. There is deliberately no approve call, because
// there is no approval to give.
export const invoicesApi = {
  workspace: (brfId) => request(`/api/brf/${brfId}/invoices`),
  case: (brfId, caseId) => request(`/api/brf/${brfId}/invoices/cases/${caseId}`),

  // Read one invoice in and analyse it in a single operator action — nobody
  // reads an invoice in order to leave it unexamined. Idempotent: the same
  // reference twice lands on the same case.
  importInvoice: (brfId, externalRef, source = 'fixture') => request(
    `/api/brf/${brfId}/invoices/import`,
    jsonBody('POST', { external_ref: externalRef, source }),
  ),
  // Re-read the source and re-run the analysis. Adds no second case, no second
  // finding and no second timeline entry when nothing has changed.
  refresh: (brfId, caseId) => request(
    `/api/brf/${brfId}/invoices/cases/${caseId}/refresh`,
    { method: 'POST' },
  ),

  // Only the fields that actually changed. The backend refuses a status that
  // needs a sentence and did not get one.
  update: (brfId, caseId, change) => request(
    `/api/brf/${brfId}/invoices/cases/${caseId}`,
    jsonBody('POST', change),
  ),
  comment: (brfId, caseId, note) => request(
    `/api/brf/${brfId}/invoices/cases/${caseId}/comment`,
    jsonBody('POST', { note }),
  ),

  // One recorded analysis, with the findings it replaced. Fetched only when
  // somebody opens an older version — carrying every superseded finding,
  // citations and all, on every case read would send bytes nobody asked for.
  analysis: (brfId, caseId, runId) => request(
    `/api/brf/${brfId}/invoices/cases/${caseId}/analyses/${runId}`,
  ),
};

// The review queue for incoming post.
//
// One read for the whole screen (`queue`), because the alternative is a list
// call plus a triage call plus a task lookup per row — a screen that renders in
// stages and can briefly show a card whose badge disagrees with its buttons.
//
// Nothing in here writes to the mailbox. `fetch` reads what has arrived since
// the last checkpoint; `resolve` records what a human decided and routes the
// result into documents, tasks and watches. A message is never marked, moved
// or deleted in the mail system by any of it.
export const intakeApi = {
  queue: (brfId) => request(`/api/brf/${brfId}/integrations/intake`),

  // Incremental: the backend holds the checkpoint, so the client never sends
  // one and cannot get it wrong. `onlyWithAttachments` defaults to false —
  // decisions and deadlines usually arrive as plain text.
  fetch: (brfId, { limit = 25, onlyWithAttachments = false } = {}) => request(
    `/api/brf/${brfId}/integrations/mailbox/fetch`
    + `?limit=${limit}&onlyWithAttachments=${onlyWithAttachments}`,
    { method: 'POST' },
  ),

  retriage: (brfId, eventId) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}/triage`,
    { method: 'POST' },
  ),
  // Recorded beside the suggestion, never over it: the pair is the only record
  // of where the reading was wrong.
  confirmCategory: (brfId, eventId, category, note = '') => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}/triage/confirm`,
    jsonBody('POST', { category, note }),
  ),

  // One call for the whole decision. Preserving a message and creating the
  // task from it is a single act at the desk; two round trips would let the
  // second half fail after the first succeeded.
  resolve: (brfId, eventId, decision) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}/resolve`,
    jsonBody('POST', decision),
  ),
  reopen: (brfId, eventId) => request(
    `/api/brf/${brfId}/integrations/source-events/${eventId}/reopen`,
    { method: 'POST' },
  ),
};

// Dated obligations read out of the association's own contracts.
//
// Reading is open to any member; scanning and every decision needs admin,
// because approving a watch is the association taking on an obligation. The
// split matters here more than elsewhere: `board` returns proposals and watches
// in two separate fields, and nothing in this client merges them.
export const watchesApi = {
  board: (brfId) => request(`/api/brf/${brfId}/watches`),
  scan: (brfId) => request(`/api/brf/${brfId}/watches/scan`, { method: 'POST' }),
  decide: (brfId, watchId, decision) => request(
    `/api/brf/${brfId}/watches/${watchId}/decision`,
    jsonBody('POST', decision),
  ),
  // 200 for a proposal, 409 for one somebody has already decided on. The
  // refusal carries the sentence that says what to do instead, so callers show
  // it rather than a generic failure.
  remove: (brfId, watchId) => request(
    `/api/brf/${brfId}/watches/${watchId}`,
    { method: 'DELETE' },
  ),
};

// Work somebody has taken on: owner, deadline, status, history.
//
// There is no scan and no proposal here, and there is deliberately no delete:
// the backend has no such route, because a task that existed is a record of
// what the board decided to do. Work that turned out to be unnecessary is
// cancelled with a stated reason and stays readable.
export const tasksApi = {
  list: (brfId) => request(`/api/brf/${brfId}/tasks`),
  // What already exists for a finding, a watch or a piece of incoming post —
  // asked before creating, so two people a week apart do not each make the
  // same task.
  forOrigin: (brfId, kind, refId) => request(
    `/api/brf/${brfId}/tasks/for/${encodeURIComponent(kind)}/${encodeURIComponent(refId)}`,
  ),
  create: (brfId, task) => request(`/api/brf/${brfId}/tasks`, jsonBody('POST', task)),
  // Only the fields that actually changed. Sending a field its current value
  // with no note is 422 "Inget att ändra" — the route refuses to write history
  // that says nothing happened.
  update: (brfId, taskId, change) => request(
    `/api/brf/${brfId}/tasks/${taskId}`,
    jsonBody('POST', change),
  ),
  comment: (brfId, taskId, note) => request(
    `/api/brf/${brfId}/tasks/${taskId}/comment`,
    jsonBody('POST', { note }),
  ),
};

// Routes that only the installed desktop application serves. On the web these
// 404, which is exactly how the UI detects which delivery it is running in —
// there is no build flag and no second bundle.
export const desktopApi = {
  state: () => request('/api/desktop/state'),
  setup: (payload) => request('/api/desktop/setup', jsonBody('POST', payload)),
  createBrf: (name) => request('/api/desktop/brf', jsonBody('POST', { name })),
  getModelRuntime: () => request('/api/desktop/model-runtime'),
  putModelRuntime: (config) => request('/api/desktop/model-runtime', jsonBody('PUT', config)),
  testModelRuntime: () => request('/api/desktop/model-runtime/test', { method: 'POST' }),
  listBackups: () => request('/api/desktop/backups'),
  createBackup: () => request('/api/desktop/backups', { method: 'POST' }),
  deleteBackup: (name) => request(
    `/api/desktop/backups/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  ),
  restoreBackup: (name) => request(
    `/api/desktop/backups/${encodeURIComponent(name)}/restore`,
    { method: 'POST' },
  ),
  restart: () => request('/api/desktop/restart', { method: 'POST' }),
};
