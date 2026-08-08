import React, { useState } from 'react';
import { Folders, Search as SearchIcon, FileText, ArrowRight, Loader2, AlertCircle, Upload, CheckCircle2, AlertTriangle, X, ChevronRight, CornerDownRight, ArrowLeft, ZoomIn, ZoomOut, ThumbsDown, MessageCircle, Info, Trash2 } from 'lucide-react';
import TraffMark from './components/TraffMark';
import EmptyState from './components/EmptyState';
import useSlashFocus from './useSlashFocus';
import Login from './components/Login';
import PdfPane from './components/PdfPane';
import Setup from './components/Setup';
import DesktopSettings from './components/DesktopSettings';
import AppNavigation from './components/AppNavigation';
import { api, desktopApi } from './api';
import { displayNameForModel, displayNameForProvider } from './modelDisplay';
import { PRODUCT_WORKSPACES } from './appWorkspaces';
import './App.css';

// Refusal reasons where the LLM was never invoked (gated on retrieval, not
// generation) — no model actually produced these responses, so provenance
// must not be shown alongside them even though AskResponse still carries
// provider/model for logging purposes.
const NO_MODEL_REFUSAL_REASONS = ['no_documents', 'low_relevance'];

/**
 * The state of one answer, said the way the identity says it (§01, §03).
 *
 * The mark is the primary indicator and never the only one: the mono label
 * beside it carries the same state in words, so nothing here depends on telling
 * green from amber. Which state is shown is decided by evidence and by nothing
 * else — the core is drawn if and only if a citation survived verification,
 * because "en fylld kärna utan citat är en lögn i formspråket".
 */
const STATE_TEXT = {
  soker: 'Söker',
  belagt: 'Belagt',
  ejbelagt: 'Ej belagt',
  avbrott: 'Avbrott',
};

function AnswerState({ state }) {
  return (
    <p className={`answer-state answer-state--${state}`}>
      {state === 'avbrott'
        ? <AlertTriangle size={14} aria-hidden="true" />
        : <TraffMark size={16} variant="status" state={state} decorative />}
      <span>{STATE_TEXT[state]}</span>
    </p>
  );
}

/** Belagt only where a verified citation exists; never on the strength of prose. */
const answerState = (msg) => {
  if (msg.pending) return 'soker';
  if (msg.refusal) return 'ejbelagt';
  return msg.citations?.length ? 'belagt' : null;
};

function ModelStatusBadge({ status }) {
  const primary =
    status.kind === 'loading' ? 'Kontrollerar modell…'
    : status.kind === 'unknown' ? 'Modellstatus ej tillgänglig'
    : status.kind === 'warning' && status.provider === 'fake' ? 'Testleverantör – inte redo'
    : status.kind === 'warning' && status.provider === 'none' ? 'Ingen modell konfigurerad'
    : status.kind === 'warning' ? 'Modell inte redo'
    : status.displayName || status.model || 'Okänd modell';

  // Only a ready runtime earns a second line: for a warning the primary
  // sentence already names the provider, and repeating it in small grey type
  // read as a leaked debug string beside the real message.
  const secondary =
    status.kind === 'ready'
      ? [displayNameForProvider(status.provider), status.runtimeLabel].filter(Boolean).join(' · ')
      : null;

  const title = 'Modellen som just nu används för att generera AI-chattens svar.';
  const ariaLabel = `Modellstatus: ${primary}${secondary ? ', ' + secondary : ''}`;

  return (
    <div className={`model-status-badge ${status.kind}`} title={title} aria-label={ariaLabel}>
      <span className={`model-status-dot ${status.kind}`} aria-hidden="true" />
      <span className="model-status-text">
        <span className="model-status-primary">{primary}</span>
        {secondary && <span className="model-status-secondary desktop-only">{secondary}</span>}
      </span>
    </div>
  );
}

const MOCK_SEARCH_RESULTS = {
  query: 'andrahandsuthyrning',
  status: 'success',
  totalDocuments: 3,
  totalPassages: 5,
  results: [
    {
      id: 'res1',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 12,
      date: '2026-07-15',
      excerpt: "Bostadsrättshavaren får upplåta sin lägenhet i andra hand till annan för självständigt brukande endast om styrelsen ger sitt samtycke. Samtycke ska lämnas om bostadsrättshavaren har beaktansvärda skäl för upplåtelsen och föreningen inte har någon befogad anledning att vägra samtycke.",
      highlights: ['andra hand', 'samtycke', 'upplåtelse'],
    },
    {
      id: 'res2',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 14,
      date: '2026-07-15',
      excerpt: "Avgiften för andrahandsuthyrning uppgår till 10% av prisbasbeloppet per år. En upplåtelse i andra hand som sker utan samtycke är grund för förverkande av bostadsrätten.",
      highlights: ['andrahandsuthyrning', 'andra hand', 'utan samtycke'],
    }
  ]
};

function App() {
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState(null);

  // ---- Auth & active-BRF state (real backend; document list, global AI
  // answers/citations, and PDF viewing/citation navigation are now real too
  // — upload, delete, document-bound chat, and QA are still
  // MOCK_BEVAKNINGAR / mock until the later integration steps land) ----
  const [authState, setAuthState] = useState('loading'); // 'loading' | 'loggedOut' | 'loggedIn'
  const [user, setUser] = useState(null);
  const [memberships, setMemberships] = useState([]);
  const [activeBrfId, setActiveBrfId] = useState(null);

  const activeMembership = memberships.find((m) => m.brf_id === activeBrfId) || null;
  const activeBrfName = activeMembership?.name || '';
  // Backend is the enforcing authority (require_admin on upload/delete) —
  // this only drives whether the frontend offers the controls at all.
  const isAdmin = activeMembership?.role === 'admin';
  const handleLoggedIn = (result) => {
    setUser(result.user);
    setMemberships(result.memberships || []);
    setActiveBrfId(result.memberships?.[0]?.brf_id ?? null);
    setAuthState('loggedIn');
  };

  const resetToLogin = () => {
    setUser(null);
    setMemberships([]);
    setActiveBrfId(null);
    setAuthState('loggedOut');
  };

  // Central 401 handling: an expired session drops straight back to login.
  const handleApiError = (e) => {
    if (e?.status === 401) {
      resetToLogin();
      return true;
    }
    return false;
  };

  const handleLogout = async () => {
    try { await api.logout(); } catch { /* clear locally regardless */ }
    resetToLogin();
  };

  const switchTenant = (value) => {
    // <option> values are strings — resolve back to the membership to keep the original id type.
    const m = memberships.find((mm) => String(mm.brf_id) === String(value));
    if (!m || m.brf_id === activeBrfId) return;
    setActiveBrfId(m.brf_id);
  };

  // ---- Desktop delivery ----
  // /api/desktop/state only exists in the installed application; on the web it
  // 404s and every desktop-only surface below stays absent. There is no build
  // flag and no second bundle — the running backend decides.
  const [desktopState, setDesktopState] = useState(null);
  const [desktopReady, setDesktopReady] = useState(false);
  const [showDesktopSettings, setShowDesktopSettings] = useState(false);

  const refreshDesktopState = React.useCallback(
    () => desktopApi.state()
      .then((state) => { setDesktopState(state); return state; })
      .catch(() => { setDesktopState(null); return null; }),
    [],
  );

  // Session bootstrap: probe the delivery, then restore an existing session
  // cookie, else show login (or first-run setup on an unprovisioned desktop).
  React.useEffect(() => {
    let cancelled = false;
    refreshDesktopState()
      .then((state) => {
        if (cancelled) return null;
        setDesktopReady(true);
        // An unprovisioned installation has no accounts at all, so there is
        // nothing for /api/auth/me to restore.
        if (state && !state.provisioned) {
          setAuthState('loggedOut');
          return null;
        }
        return api.me().then(handleLoggedIn).catch(() => setAuthState('loggedOut'));
      })
      .catch(() => { if (!cancelled) { setDesktopReady(true); setAuthState('loggedOut'); } });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshDesktopState]);

  const [currentTab, setCurrentTab] = useState('docs');
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const closeMobileMenu = React.useCallback(() => setIsMobileMenuOpen(false), []);

  // Upload/delete state — see the [activeBrfId] effect below for how these
  // get invalidated on a tenant switch.
  const uploadInputRef = React.useRef(null);
  const docsSearchRef = React.useRef(null);
  // "/" focuses the document search, but only where that field is on screen.
  useSlashFocus(docsSearchRef, currentTab === 'docs');
  const uploadRequestIdRef = React.useRef(0);
  const [uploadState, setUploadState] = useState(null); // { fileName } while an upload is in flight
  const [uploadError, setUploadError] = useState(null); // { fileName, message }
  const [highlightDocId, setHighlightDocId] = useState(null); // most-recently-uploaded doc, for the "Ny" badge
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { id, name }
  const [deletingId, setDeletingId] = useState(null);

  const mapDocument = (d) => ({
    id: d.id,
    name: d.name,
    date: d.uploaded_at.slice(0, 10),
    pages: d.pages,
    status: 'Färdigbehandlad', // upload is synchronous server-side — every listed doc is done
  });

  // Shared by the tenant-change effect below and by post-upload/-delete
  // refreshes. `cancelled` is a plain mutable ref-like object (not a React
  // ref) so callers without a component-lifetime ref can still pass one.
  const fetchAndSetDocuments = (brfId, cancelledBox = { current: false }) => {
    setDocumentsLoading(true);
    setDocumentsError(null);
    return api.listDocuments(brfId)
      .then((docs) => {
        if (cancelledBox.current) return [];
        const mapped = docs.map(mapDocument);
        setDocuments(mapped);
        // Returned as well as stored: a caller that needs to act on the
        // refreshed list cannot read it back out of state in the same tick.
        return mapped;
      })
      .catch((e) => {
        if (cancelledBox.current) return;
        if (!handleApiError(e)) setDocumentsError(e.message);
      })
      .finally(() => {
        if (!cancelledBox.current) setDocumentsLoading(false);
      });
  };

  // Fetch the tenant-scoped document list whenever the active BRF changes.
  // Clears immediately so a slow request never leaves the previous BRF's
  // documents on screen after switching tenants. Also invalidates any
  // upload/delete presentation state tied to the BRF being left — an
  // upload or delete already in flight can still complete, but its result
  // can no longer touch what's on screen (see executeUpload/executeDelete).
  React.useEffect(() => {
    setDocuments([]);
    setSelectedDocument(null);
    setPdfNumPages(null);
    setPdfHighlight(null);
    setDocumentsError(null);
    uploadRequestIdRef.current += 1;
    setUploadState(null);
    setUploadError(null);
    setHighlightDocId(null);
    setDeleteConfirm(null);
    setDeletingId(null);
    if (uploadInputRef.current) uploadInputRef.current.value = '';
    if (!activeBrfId) return;

    const cancelledBox = { current: false };
    fetchAndSetDocuments(activeBrfId, cancelledBox);
    return () => { cancelledBox.current = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBrfId]);

  const [toastMessage, setToastMessage] = useState(null);
  const showToast = (message, type = 'info') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 4500);
  };

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchIsLoading, setSearchIsLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);

  // Doc State
  const [docsSearchQuery, setDocsSearchQuery] = useState('');

  // Workspace State
  const [workspaceTab, setWorkspaceTab] = useState('read'); // 'read', 'review', 'chat'
  const [mobileQaSegment, setMobileQaSegment] = useState('pdf'); // 'pdf' or 'text'
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [pdfNumPages, setPdfNumPages] = useState(null); // ground truth from pdf.js, overrides list metadata
  // Set only when the current document was opened via a citation click —
  // { rects, approximate, page }. PdfPane only shows it while pdfPage ===
  // page, so navigating away naturally clears the highlight.
  const [pdfHighlight, setPdfHighlight] = useState(null);
  const [workspaceChatInput, setWorkspaceChatInput] = useState('');
  const [workspaceChatMessages, setWorkspaceChatMessages] = useState([]);
  const [workspaceChatBusy, setWorkspaceChatBusy] = useState(false);
  const [demoState, setDemoState] = useState('standard'); // 'standard', 'no-answer', 'conflict'
  const [reportMenuOpen, setReportMenuOpen] = useState(false);
  const reportMenuRef = React.useRef(null);

  React.useEffect(() => {
    if (!reportMenuOpen) return;
    const handleClickOutside = (e) => {
      if (reportMenuRef.current && !reportMenuRef.current.contains(e.target)) {
        setReportMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [reportMenuOpen]);

  // Model identity status for the chat header — from GET /api/health's
  // `llm` object, not a hardcoded label, so it never drifts from what the
  // backend is actually configured to generate with.
  const [llmStatus, setLlmStatus] = useState({ kind: 'loading' });

  // Also re-read after the desktop model runtime is reconfigured, so the badge
  // reflects what the backend will actually generate with right now.
  const refreshLlmStatus = React.useCallback(() => api.health()
    .then((body) => {
      const llm = body.llm || {};
      setLlmStatus({
        kind: llm.ready ? 'ready' : 'warning',
        provider: llm.provider || '',
        model: llm.model || '',
        displayName: llm.display_name || displayNameForModel(llm.model || ''),
        runtimeLabel: llm.runtime_label || '',
      });
    })
    .catch(() => setLlmStatus({ kind: 'unknown' })), []);

  React.useEffect(() => { refreshLlmStatus(); }, [refreshLlmStatus]);

  // General Chat State — wired to the real POST /api/brf/{brfId}/ask
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState(null);
  // Bumped on every new request and on every activeBrfId change — a
  // response is only ever applied if this still matches the id it was
  // issued under, so a late response from a BRF the user has since left
  // can never be shown under the wrong (or no) tenant.
  const chatRequestIdRef = React.useRef(0);

  React.useEffect(() => {
    chatRequestIdRef.current += 1;
    setChatMessages([]);
    setChatInput('');
    setChatBusy(false);
    setChatError(null);
  }, [activeBrfId]);

  const executeSearch = (query) => {
    if (!query.trim()) return;
    setSearchQuery(query);
    setCurrentTab('search');
    setSelectedDocument(null);
    setSearchIsLoading(true);
    setIsMobileMenuOpen(false);

    setTimeout(() => {
      setSearchResults(MOCK_SEARCH_RESULTS);
      setSearchIsLoading(false);
    }, 800);
  };

  const openDocument = (docId, initialPage = 1, initialTab = 'read') => {
    const show = (doc) => {
      if (!doc) return;
      setSelectedDocument(doc);
      setPdfPage(initialPage);
      setWorkspaceTab(initialTab);
      setPdfZoom(100);
      setPdfNumPages(null);
      setPdfHighlight(null);
      setWorkspaceChatMessages([]);
      setIsMobileMenuOpen(false);
    };
    const known = documents.find(d => d.id === docId);
    if (known) {
      show(known);
      return;
    }
    // Not in the list this workspace loaded — which is a normal state, not a
    // missing document. The review queue creates documents while the workspace
    // is open: preserving a message makes one, adopting an attachment makes
    // another, and the card then offers to open exactly that. This used to
    // return silently, so the control that said "Öppna dokumentet" did nothing
    // at all until the association was switched or the application restarted.
    // Fetch the list again and open it from there; if it genuinely is not
    // there, `show` still does nothing and nothing is invented.
    if (!activeBrfId) return;
    fetchAndSetDocuments(activeBrfId).then((docs) => show((docs || []).find(d => d.id === docId)));
  };

  // Citations only carry document_id/document_name (never inferred) — look
  // up the richer list entry for display metadata when available, but the
  // navigation itself is keyed on document_id alone, never on the name.
  const openDocumentFromCitation = (citation) => {
    const listed = documents.find(d => d.id === citation.document_id);
    setSelectedDocument(listed || {
      id: citation.document_id,
      name: citation.document_name,
      pages: null,
      date: null,
      status: 'Färdigbehandlad',
    });
    setWorkspaceTab('read');
    setPdfZoom(100);
    setPdfPage(citation.page);
    setPdfNumPages(listed?.pages ?? null);
    setPdfHighlight({ rects: citation.rects || [], approximate: !!citation.approximate, page: citation.page });
    setWorkspaceChatMessages([]);
    setIsMobileMenuOpen(false);
  };

  const closeDocument = () => {
    setSelectedDocument(null);
    setPdfNumPages(null);
    setPdfHighlight(null);
  };

  const describeUploadError = (e) => {
    if (!e?.status) return 'Kunde inte nå servern. Kontrollera anslutningen och försök igen.';
    if (e.status === 403) return 'Du saknar behörighet att ladda upp dokument.';
    if (e.status === 413) return 'Filen är större än 50 MB.';
    if (e.status >= 500) return `Serverfel (${e.status}). Försök igen om en stund.`;
    return e.message || `Något gick fel (${e.status}).`; // 400/422: backend detail is already Swedish
  };

  // Upload is single-shot from a hidden <input type="file">: selecting a
  // file validates and immediately submits it (no separate confirm step —
  // matches the existing one-button design). The captured brfId/requestId
  // pair is the stale-result guard: activeBrfId itself may have moved on
  // by the time this resolves, so neither is trusted from the closure.
  const executeUpload = (file) => {
    if (!file || uploadState || !activeBrfId) return;
    const looksLikePdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!looksLikePdf) {
      showToast('Endast PDF-filer stöds.', 'error');
      if (uploadInputRef.current) uploadInputRef.current.value = '';
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      showToast('Filen är större än 50 MB.', 'error');
      if (uploadInputRef.current) uploadInputRef.current.value = '';
      return;
    }

    const brfId = activeBrfId;
    const brfName = activeBrfName;
    const requestId = ++uploadRequestIdRef.current;
    setUploadError(null);
    setUploadState({ fileName: file.name });

    api.uploadDocument(brfId, file)
      .then((meta) => {
        if (uploadRequestIdRef.current !== requestId) {
          // BRF changed mid-upload: the document was correctly added to
          // brfId's corpus server-side, but that's not what's on screen
          // any more — never claim it belongs to the newly active BRF.
          showToast(`Uppladdningen av "${file.name}" till ${brfName} slutfördes, men du har bytt förening.`, 'info');
          return;
        }
        setUploadState(null);
        setHighlightDocId(meta.id);
        if (uploadInputRef.current) uploadInputRef.current.value = '';
        showToast(`"${meta.name}" laddades upp och indexerades.`, 'success');
        fetchAndSetDocuments(brfId);
      })
      .catch((e) => {
        if (uploadRequestIdRef.current !== requestId) return; // stale — stay quiet about a BRF we've left
        if (handleApiError(e)) return;
        const message = describeUploadError(e);
        setUploadState(null);
        setUploadError({ fileName: file.name, message });
        showToast(message, 'error');
      });
  };

  const describeDeleteError = (e, doc) => {
    if (!e?.status) return 'Kunde inte nå servern. Kontrollera anslutningen och försök igen.';
    if (e.status === 403) return 'Du saknar behörighet att ta bort dokument.';
    if (e.status === 404) return `"${doc.name}" finns inte längre.`;
    if (e.status === 409) return 'Dokumentet är upptaget och kunde inte tas bort just nu. Försök igen.';
    if (e.status >= 500) return `Serverfel (${e.status}). Försök igen om en stund.`;
    return e.message || `Något gick fel (${e.status}).`;
  };

  const requestDeleteDocument = (doc) => {
    if (deletingId) return;
    setDeleteConfirm({ id: doc.id, name: doc.name });
  };

  const executeDelete = (target) => {
    if (deletingId || !activeBrfId) return;
    const brfId = activeBrfId;
    const docId = target.id;
    setDeletingId(docId);

    api.deleteDocument(brfId, docId)
      .then(() => {
        setDeletingId(null);
        setDeleteConfirm(null);
        if (brfId !== activeBrfId) return; // tenant switched mid-delete; that list isn't on screen any more
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
        if (highlightDocId === docId) setHighlightDocId(null);
        if (selectedDocument?.id === docId) closeDocument();
        showToast(`"${target.name}" togs bort.`, 'success');
      })
      .catch((e) => {
        setDeletingId(null);
        if (brfId !== activeBrfId) return; // stale — say nothing about a BRF we've left
        if (handleApiError(e)) return;
        setDeleteConfirm(null);
        showToast(describeDeleteError(e, target), 'error');
        if (e.status === 404) setDocuments((prev) => prev.filter((d) => d.id !== docId)); // already gone server-side
      });
  };

  React.useEffect(() => {
    if (!deleteConfirm) return;
    const onKey = (e) => { if (e.key === 'Escape' && !deletingId) setDeleteConfirm(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [deleteConfirm, deletingId]);

  const pdfDocUrl = (activeBrfId && selectedDocument) ? api.pdfUrl(activeBrfId, selectedDocument.id) : null;
  const pdfDisplayPages = pdfNumPages ?? selectedDocument?.pages ?? null;

  const pdfSurface = (scale) => (
    <div className="pdf-page-shell" style={{ transform: `scale(${scale})` }}>
      <PdfPane
        url={pdfDocUrl}
        page={pdfPage}
        onNumPages={setPdfNumPages}
        rects={pdfHighlight?.rects || []}
        highlightPage={pdfHighlight?.page ?? null}
        approximate={!!pdfHighlight?.approximate}
      />
    </div>
  );

  const handleApproveQa = () => {
    if (!window.confirm('Är du säker på att du vill godkänna detta dokument?')) return;
    setDocuments(prev => prev.map(d => d.id === selectedDocument.id ? { ...d, qa: 'Granskad' } : d));
    setSelectedDocument(prev => ({ ...prev, qa: 'Granskad' }));
    showToast('Dokumentet har godkänts och sparats.', 'success');
  };

  const executeWorkspaceChat = () => {
    if (!workspaceChatInput.trim() || workspaceChatBusy) return;
    const query = workspaceChatInput;
    setWorkspaceChatInput('');

    const newUserMsg = { role: 'user', content: query };
    const pendingAiMsg = { role: 'ai', pending: true, content: 'Söker i dokumentet…' };

    setWorkspaceChatMessages(prev => [...prev, newUserMsg, pendingAiMsg]);
    setWorkspaceChatBusy(true);

    setTimeout(() => {
      setWorkspaceChatMessages(prev => {
        const withoutPending = prev.slice(0, -1);

        if (demoState === 'no-answer') {
           return [...withoutPending, {
             role: 'ai',
             content: 'Det står inte i det här dokumentet.',
             refusal: true
           }];
        }

        if (demoState === 'conflict') {
           return [...withoutPending, {
             role: 'ai',
             content: 'Dokumentet säger två olika saker. Sida 1 anger 15 november. Ett tillägg på sida 2 anger 1 december vid mildväder. Styrelsen får avgöra vilken som gäller.',
             refusal: true,
             warning: true,
             citations: [
               { quote: 'Jouren träder i kraft den 15 november', page: 1 },
               { quote: 'Tillägg: 1 december vid mildväder', page: 2 }
             ]
           }];
        }

        return [...withoutPending, {
          role: 'ai',
          content: 'Jouren träder i kraft den 15 november och pågår till den 15 april.',
          citations: [
            { quote: 'Jouren träder i kraft den 15 november och pågår till den 15 april', page: 1 }
          ],
          followUps: ["Hur mycket kostar det?", "När måste de påbörja snöröjningen?"]
        }];
      });
      setWorkspaceChatBusy(false);
    }, 1200);
  };

  const describeAskError = (e) => {
    if (!e?.status) return 'Kunde inte nå servern. Kontrollera anslutningen och försök igen.';
    if (e.status === 403) return 'Åtkomst nekad för den här föreningen.';
    if (e.status >= 500) return `Serverfel (${e.status}). Försök igen om en stund.`;
    return e.message || `Något gick fel (${e.status}).`;
  };

  const executeGeneralChat = (query) => {
    const question = query.trim();
    if (!question || chatBusy || !activeBrfId) return;

    const brfId = activeBrfId;
    const requestId = ++chatRequestIdRef.current;

    setCurrentTab('chat');
    setChatInput('');
    setSelectedDocument(null);
    setIsMobileMenuOpen(false);
    setChatError(null);

    setChatMessages(prev => [...prev, { role: 'user', content: question }, { role: 'ai', pending: true, content: 'Söker i högen…' }]);
    setChatBusy(true);

    api.ask(brfId, question)
      .then((res) => {
        // Stale if the BRF changed (or another request superseded this
        // one) while the request was in flight — never surface it.
        if (chatRequestIdRef.current !== requestId) return;
        setChatMessages(prev => [...prev.slice(0, -1), {
          role: 'ai',
          content: res.answer,
          refusal: !!res.refusal,
          refusalReason: res.refusal_reason || null,
          warning: res.warning || null,
          citations: res.citations || [],
          provider: res.provider || null,
          model: res.model || null,
        }]);
        setChatBusy(false);
      })
      .catch((e) => {
        if (chatRequestIdRef.current !== requestId) return;
        if (handleApiError(e)) return; // 401 → back to login
        setChatMessages(prev => prev.slice(0, -1)); // drop the pending bubble
        setChatBusy(false);
        setChatError({ question, message: describeAskError(e) });
      });
  };

  const highlightText = (text, queryWords) => {
    if (!queryWords || queryWords.length === 0) return text;
    const sortedWords = [...queryWords].sort((a, b) => b.length - a.length);
    const pattern = new RegExp(`(${sortedWords.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
    const parts = text.split(pattern);
    return (
      <>
        {parts.map((part, i) => {
          const isMatch = sortedWords.some(w => w.toLowerCase() === part.toLowerCase());
          return isMatch ? <mark key={i} className="search-highlight">{part}</mark> : <span key={i}>{part}</span>;
        })}
      </>
    );
  };

  const filteredDocs = documents.filter(doc =>
    docsSearchQuery === '' || doc.name.toLowerCase().includes(docsSearchQuery.toLowerCase())
  );

  if (authState === 'loading' || !desktopReady) {
    return (
      <div className="auth-loading-screen">
        <Loader2 size={28} className="spin" />
        <span>Laddar…</span>
      </div>
    );
  }

  if (authState !== 'loggedIn') {
    // A desktop installation with no association yet has nothing to log in to.
    if (desktopState && !desktopState.provisioned) {
      return (
        <Setup
          state={desktopState}
          onProvisioned={(session) => {
            handleLoggedIn(session);
            refreshDesktopState();
            refreshLlmStatus();
          }}
        />
      );
    }
    return <Login onLoggedIn={handleLoggedIn} modelStatus={<ModelStatusBadge status={llmStatus} />} />;
  }

  return (
    <div className="app-shell">
      {showDesktopSettings && desktopState && (
        <DesktopSettings
          state={desktopState}
          onClose={() => setShowDesktopSettings(false)}
          onStateChanged={async () => {
            await refreshDesktopState();
            await refreshLlmStatus();
          }}
          onMembershipsChanged={(next) => setMemberships(next)}
        />
      )}
      {toastMessage && (
        <div role="status" aria-live="polite" style={{ position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)', background: 'var(--popover)', color: 'var(--foreground)', padding: '12px 20px', borderRadius: 'var(--radius-2xl)', zIndex: 1000, display: 'flex', alignItems: 'center', gap: '8px', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--border-strong)' }}>
          {toastMessage.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span style={{ fontWeight: '500', fontSize: '14px' }}>{toastMessage.message}</span>
        </div>
      )}
      {deleteConfirm && (
        <div className="modal-backdrop" onClick={() => !deletingId && setDeleteConfirm(null)}>
          <div
            className="confirm-dialog glass-panel"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-dialog-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="delete-dialog-title">Ta bort dokument?</h3>
            <p>Är du säker på att du vill ta bort <strong>"{deleteConfirm.name}"</strong>? Dokumentet tas bort permanent och kan inte längre sökas eller citeras av AI-chatten.</p>
            <div className="confirm-dialog-actions">
              <button className="ui-btn ui-btn--outline" onClick={() => setDeleteConfirm(null)} disabled={!!deletingId}>
                Avbryt
              </button>
              <button className="ui-btn ui-btn--destructive" onClick={() => executeDelete(deleteConfirm)} disabled={!!deletingId}>
                {deletingId === deleteConfirm.id ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
                {deletingId === deleteConfirm.id ? 'Tar bort…' : 'Ta bort'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="mock-banner-compact">
        <span className="mock-badge-inline">PILOT</span>
        Verifierad pilotslinga: förening, dokument, uppladdning, AI-svar, källor och PDF-markering använder den riktiga tjänsten. Sök, dokumentchatt, kvalitetskontroll och inställningar ingår inte i piloten.
      </div>

      <AppNavigation
        navigationVisible={!selectedDocument}
        mobileMenuOpen={isMobileMenuOpen}
        onToggleMobileMenu={() => setIsMobileMenuOpen((open) => !open)}
        onCloseMobileMenu={closeMobileMenu}
        currentTab={currentTab}
        onNavigate={(tab) => {
          setCurrentTab(tab);
          if (tab === 'docs') setDocsSearchQuery('');
        }}
        desktopState={desktopState}
        activeMembership={activeMembership}
        activeBrfId={activeBrfId}
        activeBrfName={activeBrfName}
        memberships={memberships}
        onSwitchTenant={switchTenant}
        user={user}
        onOpenDesktopSettings={() => setShowDesktopSettings(true)}
        onLogout={handleLogout}
      >

        {/* WORKSPACE MODE - Visible when a document is selected */}
        {selectedDocument && (
          <div className="workspace-container">
            <header className="workspace-header">
              <div className="workspace-header-left">
                <button className="icon-action-btn" onClick={closeDocument} title="Tillbaka till listan" aria-label="Tillbaka">
                  <ArrowLeft size={20} />
                </button>
                <div className="workspace-doc-info">
                  <h1 className="workspace-doc-title">{selectedDocument.name}</h1>
                  <div className="workspace-doc-meta">
                    {selectedDocument.status === 'Färdigbehandlad' ? (
                      <span className="status-text ok"><CheckCircle2 size={12}/> Färdigbehandlad</span>
                    ) : (
                      <span className="status-text muted"><Loader2 size={12} className="spin"/> Behandlas</span>
                    )}
                    <span className="meta-divider">·</span>
                    <span className="status-text">{pdfDisplayPages != null ? `${pdfDisplayPages} sidor` : '… sidor'}</span>
                  </div>
                </div>
              </div>

              <div className="workspace-tabs">
                <button className={`workspace-tab ${workspaceTab === 'read' ? 'active' : ''}`} onClick={() => setWorkspaceTab('read')}>
                  <FileText size={16}/> <span className="tab-label">Läs dokument</span>
                </button>
                <button className="workspace-tab" disabled title="Kvalitetskontroll ingår inte i pilotens verifierade funktioner.">
                  <CheckCircle2 size={16}/> <span className="tab-label">Kvalitetskontroll <span className="mock-tab-suffix">(ej i piloten)</span></span>
                </button>
                <button className="workspace-tab" disabled title="Dokumentchatt ingår inte i pilotens verifierade funktioner.">
                  <MessageCircle size={16}/> <span className="tab-label">Fråga dokumentet <span className="mock-tab-suffix">(ej i piloten)</span></span>
                </button>
              </div>

              <div className="workspace-header-right desktop-only" />
            </header>

            <div className="workspace-content">
              {workspaceTab === 'read' && (
                <div className="workspace-split read-mode">
                  <div className="pdf-viewer-container">
                    <div className="pdf-toolbar">
                      <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(p => Math.max(1, p - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                         <span data-testid="pdf-page-indicator">Sida {pdfPage} av {pdfDisplayPages ?? '…'}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(p => p + 1)} disabled={pdfDisplayPages != null && pdfPage >= pdfDisplayPages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
                      </div>
                      <div className="pdf-actions">
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.max(50, z - 10))} title="Zooma ut" aria-label="Zooma ut"><ZoomOut size={16}/></button>
                         <span className="pdf-zoom-value">{pdfZoom}%</span>
                         <button className="icon-action-btn" onClick={() => setPdfZoom(z => Math.min(200, z + 10))} title="Zooma in" aria-label="Zooma in"><ZoomIn size={16}/></button>
                      </div>
                    </div>

                    {pdfHighlight && pdfHighlight.page === pdfPage && (
                      pdfHighlight.rects.length > 0 ? (
                        pdfHighlight.approximate && (
                          <div className="pdf-approx-note"><AlertCircle size={13} /> Inskannat dokument — markeringen är ungefärlig.</div>
                        )
                      ) : (
                        <div className="pdf-nohighlight-note"><Info size={13} /> Citatet är verifierat, men exakt markering kunde inte beräknas för denna källa.</div>
                      )
                    )}

                    <div className="pdf-canvas">
                      {pdfSurface(pdfZoom / 100)}
                    </div>
                  </div>

                  <div className="workspace-sidepanel">
                    <div className="panel-section">
                      <h3>Dokumentinformation</h3>
                      <div className="info-grid">
                        <div className="info-item">
                          <span className="info-label">Laddades upp</span>
                          <span className="info-value">{selectedDocument.date}</span>
                        </div>
                        <div className="info-item">
                          <span className="info-label">Systembearbetning</span>
                          <span className="info-value">
                            {selectedDocument.status === 'Färdigbehandlad' ? <span className="status-text ok">Färdigbehandlad</span> : <span className="status-text muted">Behandlas</span>}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="panel-section pilot-unavailable-note">
                      <h3>Utanför pilotens omfattning</h3>
                      <p>Kvalitetskontroll ingår inte i den verifierade pilotvyn. Bevakningar finns i den installerade applikationen, under Bevakningar i menyn.</p>
                    </div>
                  </div>
                </div>
              )}

              {workspaceTab === 'review' && (
                <div className="workspace-split review-mode">
                  <div className="mobile-qa-segmented-control mobile-only">
                     <button className={mobileQaSegment === 'pdf' ? 'active' : ''} onClick={() => setMobileQaSegment('pdf')}>Original (PDF)</button>
                     <button className={mobileQaSegment === 'text' ? 'active' : ''} onClick={() => setMobileQaSegment('text')}>Extraherad text</button>
                  </div>
                  <div className={`pdf-viewer-container half ${mobileQaSegment !== 'pdf' ? 'mobile-hidden' : ''}`}>
                    <div className="pdf-toolbar">
                       <span className="desktop-only" style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Original (PDF)</span>
                       <div className="pdf-nav">
                         <button className="icon-action-btn" onClick={() => setPdfPage(p => Math.max(1, p - 1))} disabled={pdfPage === 1} aria-label="Föregående sida"><ArrowLeft size={16}/></button>
                         <span>Sid {pdfPage} / {pdfDisplayPages ?? '…'}</span>
                         <button className="icon-action-btn" onClick={() => setPdfPage(p => p + 1)} disabled={pdfDisplayPages != null && pdfPage >= pdfDisplayPages} aria-label="Nästa sida"><ArrowRight size={16}/></button>
                      </div>
                    </div>
                    <div className="pdf-canvas">
                      {pdfSurface(0.8)}
                    </div>
                  </div>

                  <div className={`extraction-container half ${mobileQaSegment !== 'text' ? 'mobile-hidden' : ''}`}>
                    <div className="pdf-toolbar extraction-toolbar">
                      <span className="desktop-only" style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Extraherad text <span className="mock-tab-suffix">(mock)</span></span>
                    </div>
                    <div className="extraction-content">
                      <div className="extracted-text-box empty">
                         Den utlästa texten är inte kopplad till den riktiga tjänsten än.
                      </div>
                    </div>

                    <div className="extraction-actions">
                       <button className="ui-btn ui-btn--primary" onClick={handleApproveQa}>
                         <CheckCircle2 size={16}/> <span className="action-label">Godkänn dokument</span>
                       </button>
                       <div ref={reportMenuRef} style={{ position: 'relative' }}>
                         <button className="ui-btn ui-btn--warning" onClick={() => setReportMenuOpen(!reportMenuOpen)} aria-haspopup="true" aria-expanded={reportMenuOpen}>
                           <ThumbsDown size={16}/> <span className="action-label">Rapportera problem</span>
                         </button>
                         {reportMenuOpen && (
                           <div className="report-menu">
                             <button onClick={() => setReportMenuOpen(false)}>Saknad text</button>
                             <button onClick={() => setReportMenuOpen(false)}>Felaktigt tecken / Skräptecken</button>
                             <button onClick={() => setReportMenuOpen(false)}>Fel styckeordning</button>
                             <button onClick={() => setReportMenuOpen(false)}>Låg läsbarhet i PDF</button>
                           </div>
                         )}
                       </div>
                    </div>
                  </div>
                </div>
              )}

              {workspaceTab === 'chat' && (
                <div className="workspace-split chat-mode">
                  <div className="pdf-viewer-container half desktop-only">
                    <div className="pdf-toolbar">
                       <span style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)' }}>Referensvy</span>
                    </div>
                    <div className="pdf-canvas">
                      {pdfSurface(0.8)}
                    </div>
                  </div>

                  <div className="workspace-chat-container half full-width-mobile">
                    <div className="workspace-chat-header">
                       <span style={{ fontWeight: 500 }}>AI-chatt för detta dokument</span>

                       <div className="demo-state-fence">
                         <span className="demo-state-fence-label">Dev</span>
                         <select value={demoState} onChange={e => setDemoState(e.target.value)} title="Ändra vilket svar AI:n tvingas ge i mockupen." aria-label="Välj AI svarstillstånd">
                           <option value="standard">Svar med citat</option>
                           <option value="no-answer">Utan belägg</option>
                           <option value="conflict">Motstridiga källor</option>
                         </select>
                       </div>
                    </div>

                    <div className="chat-messages-area" style={{ flex: 1, padding: '20px' }}>
                      {workspaceChatMessages.length === 0 ? (
                        <div className="chat-empty-state">
                          <Info size={32} color="var(--text-muted)" style={{ marginBottom: '16px', opacity: 0.5 }} />
                          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '24px' }}>
                            Ställ frågor specifikt om innehållet i <strong>{selectedDocument.name}</strong>.
                          </p>
                          <button className="example-prompt-btn" onClick={() => setWorkspaceChatInput(
                            selectedDocument.id === 'd1' ? 'När startar jouren?' :
                            selectedDocument.id === 'd2' ? 'Vad gäller för andrahandsuthyrning?' :
                            'Sammanfatta dokumentet'
                          )}>
                            {selectedDocument.id === 'd1' ? 'När startar jouren?' :
                             selectedDocument.id === 'd2' ? 'Vad gäller för andrahandsuthyrning?' :
                             'Sammanfatta dokumentet'}
                          </button>
                        </div>
                      ) : (
                        workspaceChatMessages.map((msg, idx) => (
                          <div key={idx} className={`chat-message ${msg.role}`}>
                            <div className="chat-avatar">
                              {msg.role === 'ai' ? (msg.pending ? <Loader2 size={14} className="spin" /> : 'AI') : 'DU'}
                            </div>
                            <div style={{ flex: 1 }}>
                              <div className={`chat-content chat-content--answer${msg.refusal ? ' is-ejbelagt' : ''}`}>
                                {msg.refusal && !msg.warning && <AnswerState state="ejbelagt" />}
                                {msg.warning && (
                                  <p className="answer-state answer-state--ejbelagt">
                                    <AlertTriangle size={14} aria-hidden="true" />
                                    <span>Motstridiga källor</span>
                                  </p>
                                )}
                                <div className="answer-body">{msg.content}</div>

                                {msg.citations && (
                                  <div className="chat-citations">
                                    <p className="chat-citations-head">Hämtat ur högen</p>
                                    {msg.citations.map((c, i) => (
                                      <div key={i} className="citation-pill interactive" onClick={() => setPdfPage(c.page)} title={`Gå till sida ${c.page}`} tabIndex={0} role="button" onKeyDown={e => e.key === 'Enter' && setPdfPage(c.page)}>
                                        <span className="citation-number">[{i + 1}]</span>
                                        <span className="citation-text">"{c.quote}"</span>
                                        <span className="citation-source">— s.{c.page}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {msg.followUps && !msg.pending && (
                                <div className="chat-followups">
                                  {msg.followUps.map((fu, fidx) => (
                                    <button key={fidx} className="followup-btn" onClick={() => setWorkspaceChatInput(fu)}>
                                      <CornerDownRight size={14}/> {fu}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>

                    <div className="chat-input-area" style={{ padding: '20px', borderTop: '1px solid var(--panel-border)' }}>
                      <div className="chat-input-wrapper">
                        <input
                          type="text"
                          value={workspaceChatInput}
                          onChange={(e) => setWorkspaceChatInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && executeWorkspaceChat()}
                          placeholder={`Fråga om ${selectedDocument.name}…`}
                          disabled={workspaceChatBusy}
                        />
                        <button className="chat-send-btn" onClick={() => executeWorkspaceChat()} disabled={workspaceChatBusy || !workspaceChatInput.trim()} aria-label="Skicka fråga">
                          {workspaceChatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>
          </div>
        )}

        {/* MAIN APPLICATION (Visible when NO document is selected) */}
        {!selectedDocument && (
          <main className="main-content">
            {/* Omitted Home/Search/Chat logic from earlier mockup to keep code cleaner, but I should keep them intact if the user wants to navigate back */}
            {currentTab === 'home' && (
              <div className="tab-content" style={{ maxWidth: '900px' }}>
                <div className="hero-section">
                  <h1 className="hero-title">Sök i dina dokument</h1>

                  <div className="search-input-large-wrapper" style={{ maxWidth: '640px', margin: '0 auto', padding: '8px 8px 8px 20px' }}>
                    <SearchIcon size={20} color="var(--text-secondary)" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && executeSearch(searchQuery)}
                      placeholder="Sök efter avtal, paragrafer eller ämnen…"
                      style={{ fontSize: '16px' }}
                    />
                    <button className="search-action-btn primary" onClick={() => executeSearch(searchQuery)}>
                      Sök
                    </button>
                  </div>

                  <div className="hero-subtitle">
                    Har du en mer komplex fråga? <button onClick={() => { if (searchQuery.trim()) executeGeneralChat(searchQuery); else { setCurrentTab('chat'); setIsMobileMenuOpen(false); } }} className="link-button ai" style={{ fontWeight: '500', textDecoration: 'underline' }}>Ställ den i AI-chatten istället</button>
                  </div>
                </div>

                <div className="dashboard-grid split">
                  <div className="glass-panel" style={{ padding: '24px' }}>
                    <h3 className="recent-docs-heading">
                      <Folders size={18} /> Senaste Dokument
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {documents.length === 0 ? (
                        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
                          {documentsLoading ? 'Hämtar dokument…' : 'Inga dokument ännu.'}
                        </p>
                      ) : documents.slice(0, 3).map(doc => (
                        <button key={doc.id} className="interactive-row text-left" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                          <FileText size={16} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: '14px', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.name}</span>
                          <span className="status-text">{doc.pages} sidor</span>
                        </button>
                      ))}
                    </div>
                    <button className="link-button" onClick={() => { setCurrentTab('docs'); setDocsSearchQuery(''); }} style={{ marginTop: '16px' }}>Visa alla dokument →</button>
                  </div>

                  <div className="glass-panel stat-card">
                     <div className="stat-number">{documents.reduce((sum, d) => sum + d.pages, 0)}</div>
                     <div className="stat-label">Sökbara sidor</div>
                     <div className="stat-divider">
                       <div className="stat-number">{documents.length}</div>
                       <div className="stat-label">Dokument</div>
                     </div>
                  </div>
                </div>
              </div>
            )}

            {currentTab === 'docs' && (
              <div className="tab-content docs-overview" style={{ maxWidth: '1200px' }}>
                <header className="page-header">
                  <div className="page-header-text">
                    <h2 className="page-title">Dokument</h2>
                    <p className="page-header-sub">
                      {activeBrfName ? `Dokument för ${activeBrfName}.` : 'Hantera dokument.'}
                      {' '}Allt som ligger här kan sökas, citeras och öppnas på rätt sida.
                    </p>
                  </div>
                  {isAdmin && (
                    <>
                      <input
                        ref={uploadInputRef}
                        type="file"
                        accept="application/pdf"
                        style={{ display: 'none' }}
                        onChange={(e) => executeUpload(e.target.files?.[0] || null)}
                      />
                      <button
                        className="ui-btn ui-btn--primary desktop-only"
                        onClick={() => uploadInputRef.current?.click()}
                        disabled={!!uploadState}
                        title="Ladda upp ett nytt PDF-dokument"
                      >
                        {uploadState ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
                        {uploadState ? 'Laddar upp…' : 'Ladda upp dokument'}
                      </button>
                    </>
                  )}
                </header>

                {uploadState && (
                  <div className="upload-status-banner">
                    <Loader2 size={16} className="spin" />
                    <span>Laddar upp och bearbetar &quot;{uploadState.fileName}&quot;… Detta kan ta en stund.</span>
                  </div>
                )}
                {uploadError && (
                  <div className="upload-status-banner error">
                    <AlertCircle size={16} />
                    <span>Uppladdningen av &quot;{uploadError.fileName}&quot; misslyckades: {uploadError.message}</span>
                  </div>
                )}

                <div className="docs-control-bar">
                  <div className="search-input-small responsive-search">
                    <SearchIcon size={16} />
                    <input
                      type="text"
                      ref={docsSearchRef}
                      placeholder="Sök dokumentnamn…"
                      value={docsSearchQuery}
                      onChange={(e) => setDocsSearchQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape' && docsSearchQuery) setDocsSearchQuery('');
                      }}
                      aria-label="Sök dokument"
                    />
                    {!docsSearchQuery && <kbd className="kbd" aria-hidden="true">/</kbd>}
                    {docsSearchQuery && (
                      <button className="icon-action-btn clear-search" onClick={() => setDocsSearchQuery('')} aria-label="Rensa sökning">
                        <X size={14} />
                      </button>
                    )}
                  </div>
                  {/* The corpus, said as a measurement — and, under a filter,
                      the measurement of what the filter left. */}
                  {!documentsLoading && !documentsError && documents.length > 0 && (
                    <p className="docs-register-count" aria-live="polite">
                      {docsSearchQuery
                        ? `${filteredDocs.length} av ${documents.length} dokument`
                        : `${documents.length} dokument · ${documents.reduce((sum, d) => sum + (d.pages || 0), 0)} sökbara sidor`}
                    </p>
                  )}
                </div>

                <div className="docs-collection-container">
                  {documentsLoading ? (
                    <div className="docs-empty-state">
                      <Loader2 size={32} className="spin" style={{ marginBottom: '16px' }} />
                      <h3>Hämtar dokument…</h3>
                    </div>
                  ) : documentsError ? (
                    <div className="docs-empty-state">
                      <AlertCircle size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
                      <h3>Kunde inte hämta dokument</h3>
                      <p>{documentsError}</p>
                    </div>
                  ) : documents.length === 0 ? (
                    <EmptyState
                      icon={Folders}
                      title="Arkivet är tomt."
                      actions={isAdmin ? (
                        <button type="button" className="ui-btn ui-btn--primary" onClick={() => uploadInputRef.current?.click()}>
                          <Upload size={15} /> Ladda upp ditt första dokument
                        </button>
                      ) : null}
                    >
                      Ladda upp stadgar, protokoll och avtal — varje sida blir sökbar och citerbar.
                    </EmptyState>
                  ) : filteredDocs.length === 0 ? (
                    <EmptyState
                      icon={SearchIcon}
                      title="Inga träffar."
                      actions={(
                        <button type="button" className="ui-btn ui-btn--outline" onClick={() => setDocsSearchQuery('')}>
                          Rensa sökning
                        </button>
                      )}
                    >
                      Inga dokument matchar sökningen — prova att ändra sökordet.
                    </EmptyState>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      {/* The register. Name first and strongest; what can be
                          measured about the document — pages, date — stands to
                          the right in the mono, the cut that measures. The old
                          status column said "Färdigbehandlad" on every row of
                          every library (ingestion is synchronous), and a badge
                          every row carries is decoration, not status. */}
                      <table className="docs-table desktop-only">
                        <thead>
                          <tr>
                            <th scope="col">Dokumentnamn</th>
                            <th scope="col" className="num-col">Sidor</th>
                            <th scope="col" className="num-col">Uppladdat</th>
                            {isAdmin && <th scope="col" className="action-col"><span className="visually-hidden">Åtgärder</span></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredDocs.map(doc => (
                            <tr
                              key={doc.id}
                              className="interactive-table-row"
                              onClick={() => openDocument(doc.id)}
                              role="row"
                            >
                              <td className="doc-name-cell">
                                <button className="doc-open-btn" onClick={() => openDocument(doc.id)} aria-label={`Öppna ${doc.name}`}>
                                  <span className="truncate">{doc.name}</span>
                                  {doc.id === highlightDocId && <span className="new-doc-badge">Ny</span>}
                                </button>
                              </td>
                              <td className="meta-cell num-col">{doc.pages != null ? doc.pages : '—'}</td>
                              <td className="meta-cell num-col">{doc.date}</td>
                              {isAdmin && (
                                <td className="action-col" onClick={(e) => e.stopPropagation()}>
                                  <button
                                    className="icon-action-btn danger row-reveal"
                                    onClick={() => requestDeleteDocument(doc)}
                                    disabled={!!deletingId}
                                    aria-label={`Ta bort ${doc.name}`}
                                    title="Ta bort dokument"
                                  >
                                    <Trash2 size={16} />
                                  </button>
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      {/* Mobile List View */}
                      <div className="docs-mobile-list mobile-only">
                        {filteredDocs.map(doc => (
                          <div key={doc.id} className="doc-mobile-card">
                            <button
                              className="doc-mobile-card-open"
                              onClick={() => openDocument(doc.id)}
                              aria-label={`Öppna ${doc.name}`}
                            >
                              <div className="doc-card-header">
                                <FileText size={16} color="var(--text-secondary)" />
                                <h4 className="truncate">{doc.name}</h4>
                                {doc.id === highlightDocId && <span className="new-doc-badge">Ny</span>}
                              </div>
                              <div className="doc-card-meta">
                                 <span>{doc.date}</span>
                                 <span>·</span>
                                 <span>{doc.pages != null ? `${doc.pages} sidor` : ''}</span>
                              </div>
                              <ChevronRight size={16} className="chevron-icon" />
                            </button>
                            {isAdmin && (
                              <button
                                className="icon-action-btn danger doc-mobile-delete-btn"
                                onClick={() => requestDeleteDocument(doc)}
                                disabled={!!deletingId}
                                aria-label={`Ta bort ${doc.name}`}
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Omitted the rest of search/chat for brevity, identical logic */}
            {currentTab === 'search' && (
               // Kept simple for now as it wasn't the main focus, but keeping it functional
               <div className="tab-content" style={{ maxWidth: '800px', margin: '0 auto' }}>
                <div className="search-top-bar" style={{ marginBottom: '24px' }}>
                  <div className="search-input-large-wrapper">
                    <SearchIcon size={20} color="var(--text-secondary)" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && executeSearch(searchQuery)}
                      placeholder="Sök i text…"
                    />
                    <button className="search-action-btn primary" onClick={() => executeSearch(searchQuery)}>
                      {searchIsLoading ? <Loader2 size={16} className="spin" /> : 'Sök'}
                    </button>
                  </div>

                  {!searchIsLoading && searchResults && (
                    <div className="search-summary-text" style={{ display: 'flex', justifyContent: 'space-between', marginTop: '16px' }}>
                      <span>Hittade {searchResults.totalPassages} träffar i {searchResults.totalDocuments} dokument.</span>
                      <button onClick={() => executeGeneralChat(searchQuery)} className="link-button ai">Fråga AI:n istället</button>
                    </div>
                  )}
                </div>

                {searchIsLoading ? (
                  <div style={{ textAlign: 'center', marginTop: '60px', color: 'var(--text-secondary)' }}>
                    <Loader2 size={32} className="spin" style={{ margin: '0 auto', color: 'var(--primary-action)' }} />
                    <h3 style={{ marginTop: '16px' }}>Söker i högen…</h3>
                  </div>
                ) : searchResults && (
                  <div className="search-results-list">
                    {searchResults.results.map((res) => (
                      <div key={res.id} className="search-snippet-card">
                        <div className="snippet-excerpt">
                          {highlightText(res.excerpt, res.highlights)}
                        </div>
                        <div className="snippet-meta">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                             <FileText size={14} />
                             <span style={{ fontWeight: '500', color: 'var(--text-primary)' }}>{res.documentName}</span>
                             <span>· Sid {res.page}</span>
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                             <button className="small-action-btn" onClick={() => openDocument(res.documentId, res.page, 'read')}>Öppna källa</button>
                             <button className="small-action-btn ai" onClick={() => {
                               openDocument(res.documentId, res.page, 'chat');
                               setWorkspaceChatInput(`Angående sökningen "${searchQuery}": vad står det mer om detta i dokumentet?`);
                             }}>Fråga AI i dokument</button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {currentTab === 'chat' && (
              <div className="tab-content tab-content--fill">
                <div className="chat-container">
                  <div className="chat-header">
                    <h2 className="chat-title">Fråga dokumenten</h2>
                    <p className="chat-header-sub">Frågan går till föreningens egna dokument. Ingenting annat.</p>
                  </div>

                  <div className="chat-messages-area">
                    {chatMessages.length === 0 ? (
                      <div className="chat-empty-state">
                         <TraffMark size={26} decorative />
                         <h3 className="chat-empty-title">Ställ en fråga om föreningens dokument</h3>
                         <p className="chat-empty-hint">
                           Svaret citerar det dokument det kommer ur — eller uteblir.
                         </p>
                         <div className="chat-empty-examples">
                           <button className="example-prompt-btn" onClick={() => executeGeneralChat('Vad säger stadgarna om andrahandsuthyrning?')} disabled={chatBusy}>
                             Vad säger stadgarna om andrahandsuthyrning?
                           </button>
                           <button className="example-prompt-btn" onClick={() => executeGeneralChat('Vilka datum gäller för snöröjningsjouren?')} disabled={chatBusy}>
                             Vilka datum gäller för snöröjningsjouren?
                           </button>
                         </div>
                      </div>
                    ) : (
                      <>
                        {chatMessages.map((msg, idx) => (
                          msg.role === 'user' ? (
                            /* The person's words, as a line in the record —
                               not a speech bubble. The label does the telling. */
                            <div key={idx} className="chat-message user">
                              <p className="chat-question-label">Fråga</p>
                              <p className="chat-question-text">{msg.content}</p>
                            </div>
                          ) : (
                          <div key={idx} className="chat-message ai">
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div className={`chat-content chat-content--answer${msg.refusal ? ' is-ejbelagt' : ''}${msg.pending ? ' is-pending' : ''}`}>
                                {answerState(msg) && <AnswerState state={answerState(msg)} />}
                                <div className="answer-body">{msg.content}</div>
                                {msg.warning && <p className="answer-caveat"><Info size={14} aria-hidden="true" /> {msg.warning}</p>}

                                {msg.citations && msg.citations.length > 0 && (
                                  <div className="chat-citations">
                                    <p className="chat-citations-head">Hämtat ur högen</p>
                                    {msg.citations.map((c, i) => (
                                      <div
                                        key={i}
                                        className="citation-pill interactive"
                                        onClick={() => openDocumentFromCitation(c)}
                                        title={`Öppna ${c.document_name}, sida ${c.page}`}
                                        tabIndex={0}
                                        role="button"
                                        onKeyDown={e => e.key === 'Enter' && openDocumentFromCitation(c)}
                                      >
                                        <span className="citation-number">[{i + 1}]</span>
                                        <span className="citation-text">"{c.quote}"</span>
                                        <span className="citation-source">— {c.document_name} s.{c.page}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                              {msg.model && !NO_MODEL_REFUSAL_REASONS.includes(msg.refusalReason) && (
                                <div className="chat-model-provenance" title="Modellen som genererade detta svar.">
                                  {displayNameForModel(msg.model)} · {displayNameForProvider(msg.provider)}
                                </div>
                              )}
                            </div>
                          </div>
                          )
                        ))}

                        {chatError && (
                          <div className="chat-message ai">
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div className="chat-content is-avbrott">
                                <AnswerState state="avbrott" />
                                {chatError.message}
                              </div>
                              <div className="chat-followups">
                                <button className="followup-btn" onClick={() => executeGeneralChat(chatError.question)} disabled={chatBusy}>
                                  <CornerDownRight size={14}/> Försök igen
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  <div className="chat-input-area">
                    <div className="chat-input-wrapper">
                      <input
                        type="text"
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && executeGeneralChat(chatInput)}
                        placeholder="Fråga rakt in i högen…"
                        disabled={chatBusy}
                      />
                      <button className="chat-send-btn" onClick={() => executeGeneralChat(chatInput)} disabled={chatBusy || !chatInput.trim()} aria-label="Skicka fråga">
                        {chatBusy ? <Loader2 size={18} className="spin"/> : <ArrowRight size={18} />}
                      </button>
                    </div>
                    {/* Provenance where the question is asked: what will be
                        searched, and what will do the generating. */}
                    <div className="chat-composer-meta">
                      <ModelStatusBadge status={llmStatus} />
                      <span className="chat-composer-scope">Söker i alla {documents.length} dokument</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {PRODUCT_WORKSPACES.map((workspace) => (
              workspace.id === currentTab && desktopState && activeBrfId ? (
                <div key={workspace.id} className="tab-content">
                  {workspace.render({
                    brfId: activeBrfId,
                    isAdmin,
                    onOpenDocument: openDocument,
                    onOpenCitation: openDocumentFromCitation,
                    onDocumentsChanged: () => activeBrfId && fetchAndSetDocuments(activeBrfId),
                  })}
                </div>
              ) : null
            ))}

            {currentTab === 'settings' && (
              <div className="settings-placeholder" style={{ padding: '24px', background: 'var(--panel-bg)', borderRadius: '12px', border: '1px solid var(--panel-border)', marginTop: '24px' }}>
                <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>Inställningar</h2>
                <p style={{ color: 'var(--text-secondary)' }}>Inställningsvyn är inte implementerad i denna mockup.</p>
              </div>
            )}
          </main>
        )}
      </AppNavigation>
    </div>
  );
}

export default App;
