import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Puck } from '@puckeditor/core';
// Puck's own stylesheet, in the variant that references no external origin.
//
// This import is load-bearing, not cosmetic. Left out, Puck injects its default
// stylesheet at runtime, and that stylesheet begins
// `@import "https://rsms.me/inter/inter.css"` — the installed desktop product
// would reach for a webfont on the open internet the moment a board opened this
// screen. The packaged application's CSP blocks it, so the request fails rather
// than succeeds, but a blocked request is still a request this product should
// never make: index.html states in as many words that no external font origin
// is referenced, and the offline pilot's whole claim is that nothing leaves the
// machine.
//
// Importing this file statically is the library's supported way to say so: it
// sets `--_puck-styles-loaded`, which the runtime checks and then skips
// injecting the default. Inter is still used when the system has it, and the
// platform UI font otherwise — exactly what the rest of the product does.
import '@puckeditor/core/no-external.css';
import { Loader2, RotateCcw, X } from 'lucide-react';
import { api, websiteApi } from '../../api';
import { createWebsiteConfig } from './websiteConfig';
import WorkspaceShell from './WorkspaceShell';
import {
  actionToCommands,
  coalesce,
  describeBatch,
  groundingMetadata,
  toPuckData,
} from './websiteCommands';
import './Website.css';

// Hemsidan — the association's public website, edited inside the product.
//
// The container owns everything that talks to the server; `WorkspaceShell` owns
// what the board looks at. The seam between them is one idea: **the canvas is
// optimistic, the server is the authority.** Puck applies an edit locally so
// typing and dragging stay instant, the same edit goes to the backend as
// commands, and if the backend refuses it the canvas is re-synced from what the
// backend actually has. Nothing is ever "saved" as a page.

const TEXT_DEBOUNCE_MS = 650;

export default function Website({ brfId, isAdmin, onOpenCitation }) {
  const [workspace, setWorkspace] = useState(null);
  const [vocabulary, setVocabulary] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [activePageId, setActivePageId] = useState('');
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [revisions, setRevisions] = useState(null);
  const [syncNonce, setSyncNonce] = useState(0);
  const [syncData, setSyncData] = useState(null);

  // Ordering guarantee: every write goes through one promise chain, so a debounced
  // text edit can never overtake the drag that followed it.
  const chainRef = useRef(Promise.resolve());
  const pendingRef = useRef([]);
  const timerRef = useRef(null);

  const fieldsByType = useMemo(() => {
    const map = {};
    Object.entries(vocabulary?.components || {}).forEach(([name, spec]) => {
      map[name] = Object.keys(spec.fields || {});
    });
    return map;
  }, [vocabulary]);

  const labelForType = useCallback(
    (type) => vocabulary?.components?.[type]?.label || type,
    [vocabulary],
  );

  const loadWorkspace = useCallback(async () => {
    const data = await websiteApi.workspace(brfId);
    setWorkspace(data);
    return data;
  }, [brfId]);

  const loadPage = useCallback(async (pageId, { resync = false } = {}) => {
    const data = await websiteApi.page(brfId, pageId);
    setPage(data);
    if (resync) {
      setSyncData(toPuckData({ title: data.draft.title, content: data.draft.content }));
      setSyncNonce((n) => n + 1);
    }
    return data;
  }, [brfId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const [ws, vocab, docs] = await Promise.all([
          websiteApi.workspace(brfId),
          websiteApi.vocabulary(brfId),
          api.listDocuments(brfId).catch(() => []),
        ]);
        if (cancelled) return;
        setWorkspace(ws);
        setVocabulary(vocab);
        setDocuments(Array.isArray(docs) ? docs : docs?.documents || []);
        const first = ws.pages.find((p) => p.home) || ws.pages[0];
        if (first) {
          setActivePageId(first.id);
          const detail = await websiteApi.page(brfId, first.id);
          if (!cancelled) setPage(detail);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Webbplatsen gick inte att läsa.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [brfId]);

  // ---------- writing ----------

  const post = useCallback((commands, summary) => {
    if (commands.length === 0) return Promise.resolve(null);
    setBusy(true);
    chainRef.current = chainRef.current
      .then(async () => {
        try {
          const result = await websiteApi.runCommands(brfId, commands, summary);
          setWorkspace(result.workspace);
          // The page detail is re-read rather than patched locally: the server
          // decides what a page is, and a client that maintained its own copy
          // would eventually disagree with it about something small and wrong.
          const detail = await websiteApi.page(brfId, activePageId);
          setPage(detail);
          return result;
        } catch (err) {
          // The canvas is now showing something the server refused. Put the
          // server's version back rather than leaving an edit on screen that
          // does not exist — a page that lies about what it contains is worse
          // than an error message.
          setError(err.message || 'Ändringen gick inte att spara.');
          await loadPage(activePageId, { resync: true }).catch(() => {});
          return null;
        }
      })
      .finally(() => setBusy(false));
    return chainRef.current;
  }, [brfId, activePageId, loadPage]);

  const flushText = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const pending = coalesce(pendingRef.current);
    pendingRef.current = [];
    if (pending.length === 0) return Promise.resolve(null);
    return post(pending, describeBatch(pending, labelForType));
  }, [post, labelForType]);

  // A pending keystroke must not be lost when the workspace goes away.
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const handleAction = useCallback((action, appState, prevAppState) => {
    if (!isAdmin || !activePageId) return;
    const commands = actionToCommands({
      action, appState, prevAppState, pageId: activePageId, fieldsByType,
    });
    if (commands.length === 0) return;

    const isTyping = commands.every((c) => c.command === 'update_text');
    if (isTyping) {
      pendingRef.current.push(...commands);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => { flushText(); }, TEXT_DEBOUNCE_MS);
      return;
    }
    // Anything structural lands now — but only after the typing that preceded
    // it, so the history reads in the order things actually happened.
    flushText();
    post(commands, describeBatch(commands, labelForType));
  }, [isAdmin, activePageId, fieldsByType, flushText, post, labelForType]);

  // ---------- page-level actions ----------

  const selectPage = useCallback(async (pageId) => {
    await flushText();
    setActivePageId(pageId);
    setLoading(true);
    try {
      await loadPage(pageId);
    } catch (err) {
      setError(err.message || 'Sidan gick inte att läsa.');
    } finally {
      setLoading(false);
    }
  }, [flushText, loadPage]);

  const createPage = useCallback(async () => {
    const title = window.prompt('Vad ska sidan heta?');
    if (!title || !title.trim()) return;
    const result = await post(
      [
        { command: 'create_page', title: title.trim() },
      ],
      `Skapade sidan ${title.trim()}`,
    );
    if (!result) return;
    const created = result.workspace.pages.find((p) => !workspace?.pages.some((old) => old.id === p.id));
    if (created) {
      // A new page that is not in the menu is a page nobody can reach.
      await post(
        [{ command: 'update_navigation', action: 'add', page_id: created.id }],
        'La in sidan i menyn',
      );
      selectPage(created.id);
    }
  }, [post, workspace, selectPage]);

  const nudge = useCallback((blockId, index) => {
    post([{ command: 'move_block', page_id: activePageId, block_id: blockId, index }], 'Flyttade ett block')
      .then(() => loadPage(activePageId, { resync: true }));
  }, [post, activePageId, loadPage]);

  const removeBlock = useCallback((index) => {
    const block = page?.draft?.content?.[index];
    if (!block) return;
    post([{ command: 'delete_block', page_id: activePageId, block_id: block.id }], 'Tog bort ett block')
      .then(() => loadPage(activePageId, { resync: true }));
  }, [page, post, activePageId, loadPage]);

  const duplicateBlock = useCallback((index) => {
    const block = page?.draft?.content?.[index];
    if (!block) return;
    post([{ command: 'duplicate_block', page_id: activePageId, block_id: block.id }], 'Kopierade ett block')
      .then(() => loadPage(activePageId, { resync: true }));
  }, [page, post, activePageId, loadPage]);

  const insertBlock = useCallback((type) => {
    // Click-to-add from the block drawer. No index: it goes last, which is what
    // "lägg till ett avsnitt" means when nobody has said where. The canvas is
    // re-synced from the server afterwards rather than patched here, so the
    // block the editor shows is the block that was actually stored — including
    // the defaults the backend filled in.
    post([{ command: 'insert_block', page_id: activePageId, type }], `La till ${labelForType(type)}`)
      .then((result) => { if (result) loadPage(activePageId, { resync: true }); });
  }, [post, activePageId, labelForType, loadPage]);

  const confirmBlock = useCallback((blockId) => {
    // Adopting text a model wrote. Deliberately a command like any other, so it
    // lands in the history with a name and a time and can be taken back — this
    // is the association saying "that is what we mean", and that is worth a
    // record.
    post(
      [{ command: 'confirm_block', page_id: activePageId, block_id: blockId, confirmed: true }],
      'Bekräftade AI-skriven text',
    ).then((result) => { if (result) loadPage(activePageId, { resync: true }); });
  }, [post, activePageId, loadPage]);

  const publish = useCallback(async () => {
    await flushText();
    setBusy(true);
    try {
      await websiteApi.publish(brfId, activePageId, '');
      await Promise.all([loadWorkspace(), loadPage(activePageId)]);
    } catch (err) {
      setError(err.message || 'Publiceringen gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }, [brfId, activePageId, flushText, loadWorkspace, loadPage]);

  const unpublish = useCallback(async () => {
    setBusy(true);
    try {
      await websiteApi.unpublish(brfId, activePageId);
      await Promise.all([loadWorkspace(), loadPage(activePageId)]);
    } catch (err) {
      setError(err.message || 'Avpubliceringen gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }, [brfId, activePageId, loadWorkspace, loadPage]);

  const openRevisions = useCallback(async () => {
    try {
      setRevisions(await websiteApi.revisions(brfId, activePageId));
    } catch (err) {
      setError(err.message || 'Versionerna gick inte att läsa.');
    }
  }, [brfId, activePageId]);

  const rollback = useCallback(async (revisionId) => {
    setBusy(true);
    try {
      await websiteApi.rollback(brfId, activePageId, revisionId, '');
      await Promise.all([loadWorkspace(), loadPage(activePageId)]);
      setRevisions(await websiteApi.revisions(brfId, activePageId));
    } catch (err) {
      setError(err.message || 'Återställningen gick inte igenom.');
    } finally {
      setBusy(false);
    }
  }, [brfId, activePageId, loadWorkspace, loadPage]);

  const onAiApplied = useCallback(async (result) => {
    if (result?.workspace) setWorkspace(result.workspace);
    if (!activePageId) return;
    // The AI's work is applied straight into the draft, so the canvas shows it
    // immediately — that is the whole point of not asking for a diff first.
    await loadPage(activePageId, { resync: true }).catch(() => {});
  }, [activePageId, loadPage]);

  const undo = useCallback(async (transactionId) => {
    setBusy(true);
    try {
      const result = await websiteApi.undo(brfId, transactionId);
      setWorkspace(result.workspace);
      await loadPage(activePageId, { resync: true });
    } finally {
      setBusy(false);
    }
  }, [brfId, activePageId, loadPage]);

  const startSite = useCallback(async () => {
    setBusy(true);
    try {
      const ws = await websiteApi.initialize(brfId, 'Startsida');
      setWorkspace(ws);
      const first = ws.pages[0];
      setActivePageId(first.id);
      setPage(await websiteApi.page(brfId, first.id));
    } catch (err) {
      setError(err.message || 'Webbplatsen gick inte att skapa.');
    } finally {
      setBusy(false);
    }
  }, [brfId]);

  // ---------- render ----------

  const config = useMemo(() => createWebsiteConfig({
    documents,
    settings: workspace?.settings || {},
    navigation: workspace?.navigation || [],
    activePageId,
  }), [documents, workspace?.settings, workspace?.navigation, activePageId]);

  const puckData = useMemo(
    () => (page ? toPuckData({ title: page.draft.title, content: page.draft.content }) : null),
    // Deliberately keyed on the page identity, not on its content: this is the
    // *seed* Puck mounts with, and recomputing it on every keystroke would fight
    // the editor for control of its own state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [page?.id],
  );

  const grounding = useMemo(
    () => groundingMetadata({ content: page?.draft?.content || [] }),
    [page],
  );

  if (loading && !workspace) {
    return (
      <div className="site-loading">
        <Loader2 size={20} className="site-spin" aria-hidden="true" /> Läser webbplatsen…
      </div>
    );
  }

  if (workspace && workspace.pages.length === 0) {
    return (
      /* Hemsidan opens on the same plate as every other workspace. It used to
         open on a centred card floating in an empty canvas with no masthead at
         all — the one screen that gave no sign of which product it belonged to.
         Its instrument is the site's own standing, which at zero is honestly
         zero: no pages, nothing published. */
      <div className="site-start">
        <header className="page-header">
          <div className="page-header-text">
            <h2 className="page-title">Hemsidan</h2>
            <p className="page-header-sub">
              Sidan medlemmarna läser, byggd ur föreningens egna handlingar.
            </p>
          </div>
          <div className="page-header-actions">
            {isAdmin && (
              <button type="button" className="ui-btn ui-btn--primary" onClick={startSite} disabled={busy}>
                {busy ? 'Skapar…' : 'Skapa startsidan'}
              </button>
            )}
          </div>
          <div className="page-header-instrument">
            <div className="invoices-ledger">
              <div className="invoices-ledger-figure">
                <span className="ledger-label">Sidor</span>
                <span className="ledger-amount">0</span>
              </div>
              <dl className="watches-standing">
                <div><dt>Publicerade</dt><dd>0</dd></div>
              </dl>
            </div>
          </div>
        </header>

        <div className="site-start__body">
          <p className="site-start__lead">
            Sakuppgifter hämtas ur föreningens egna handlingar, med källhänvisning.
            Det som inte går att belägga skrivs inte.
          </p>
          {!isAdmin && (
            <p className="site-start__note">En administratör behöver komma igång med webbplatsen först.</p>
          )}
          {error && <p className="site-start__error">{error}</p>}
        </div>
      </div>
    );
  }

  if (!page || !puckData) {
    return (
      <div className="site-loading">
        <Loader2 size={20} className="site-spin" aria-hidden="true" /> Läser sidan…
      </div>
    );
  }

  return (
    <>
      <Puck
        key={page.id}
        config={config}
        data={puckData}
        onAction={handleAction}
        iframe={{ enabled: true }}
        // The same rule the backend enforces with a 403, expressed in the canvas
        // so a member sees a page they cannot accidentally try to change.
        permissions={{
          drag: isAdmin, edit: isAdmin, insert: isAdmin, delete: isAdmin, duplicate: isAdmin,
        }}
        metadata={{ grounding }}
      >
        <WorkspaceShell
          brfId={brfId}
          isAdmin={isAdmin}
          page={page}
          pages={workspace?.pages || []}
          workspace={workspace}
          activePageId={activePageId}
          onSelectPage={selectPage}
          onCreatePage={createPage}
          onPublish={publish}
          onUnpublish={unpublish}
          onOpenRevisions={openRevisions}
          onDelete={removeBlock}
          onDuplicate={duplicateBlock}
          onNudge={nudge}
          onAiApplied={onAiApplied}
          onUndo={undo}
          onInsertBlock={insertBlock}
          onConfirmBlock={confirmBlock}
          vocabulary={vocabulary}
          labelForType={labelForType}
          onOpenCitation={onOpenCitation}
          grounding={grounding}
          syncNonce={syncNonce}
          syncData={syncData}
          busy={busy}
          error={error}
          onDismissError={() => setError('')}
        />
      </Puck>

      {revisions && (
        <div className="site-modal" role="dialog" aria-label="Tidigare versioner">
          <div className="site-modal__backdrop" onClick={() => setRevisions(null)} aria-hidden="true" />
          <div className="site-modal__card">
            <header>
              <h2>Tidigare versioner</h2>
              <button type="button" onClick={() => setRevisions(null)} aria-label="Stäng"><X size={16} /></button>
            </header>
            {revisions.revisions.length === 0 ? (
              <p className="site-modal__empty">Sidan har aldrig publicerats.</p>
            ) : (
              <ul className="site-revisions">
                {revisions.revisions.map((revision) => (
                  <li key={revision.id} className={revision.id === revisions.current ? 'current' : ''}>
                    <div>
                      <div className="site-revisions__title">
                        Version {revision.seq}
                        {revision.id === revisions.current && <span className="site-pill site-pill--live">Publicerad nu</span>}
                      </div>
                      <div className="site-revisions__meta">
                        {revision.created_at?.slice(0, 16).replace('T', ' ')} · {revision.block_count} block
                        {revision.note ? ` · ${revision.note}` : ''}
                      </div>
                    </div>
                    {isAdmin && revision.id !== revisions.current && (
                      <button type="button" className="site-btn" onClick={() => rollback(revision.id)} disabled={busy}>
                        <RotateCcw size={14} aria-hidden="true" /> Återställ
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="site-modal__note">
              En återställning publicerar en tidigare version på nytt. Ingen version skrivs
              om och utkastet lämnas orört.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
