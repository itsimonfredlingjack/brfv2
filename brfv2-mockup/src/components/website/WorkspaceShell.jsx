import React, { useEffect, useRef, useState } from 'react';
import { Drawer, Puck, usePuck } from '@puckeditor/core';
import {
  ChevronDown,
  Check,
  Copy,
  FileText,
  Globe,
  History,
  Loader2,
  Monitor,
  MoveDown,
  MoveUp,
  Plus,
  Smartphone,
  ShieldAlert,
  Sparkles,
  Tablet,
  Trash2,
  X,
} from 'lucide-react';
import AiPartner from './AiPartner';

// The workspace as the board sees it: the AI partner on the left, the website
// itself filling everything else.
//
// It lives *inside* `<Puck>` rather than beside it, which is what lets it use
// `usePuck()` — the selection, the history and the dispatcher — while still
// being our own layout. Puck's default three-panel chrome is never rendered:
// composing `<Puck.Preview>`, `<Puck.Fields>` and `<Puck.Components>` into this
// shell is the supported way to make the editor look like the product it is
// embedded in rather than like an editor that happens to be embedded.

const VIEWPORTS = [
  { id: 'mobile', label: 'Mobil', width: 390, icon: Smartphone },
  { id: 'tablet', label: 'Platta', width: 820, icon: Tablet },
  { id: 'desktop', label: 'Dator', width: 0, icon: Monitor },
];

function StatusPill({ page }) {
  if (!page) return null;
  if (!page.published) {
    return <span className="site-pill site-pill--draft">Utkast · aldrig publicerad</span>;
  }
  if (page.has_unpublished_changes) {
    return <span className="site-pill site-pill--pending">Publicerad · ändringar väntar</span>;
  }
  return <span className="site-pill site-pill--live">Publicerad · version {page.publication?.seq}</span>;
}

/**
 * Push server state into the editor without echoing it back as an edit.
 *
 * `setData` is not in the mapper's list of edit actions, so re-syncing after an
 * AI change or an undo cannot loop back into another write.
 */
function CanvasSync({ nonce, data }) {
  const { dispatch } = usePuck();
  const seen = useRef(nonce);
  useEffect(() => {
    if (nonce === seen.current || !data) return;
    seen.current = nonce;
    dispatch({ type: 'setData', data, recordHistory: false });
  }, [nonce, data, dispatch]);
  return null;
}

/** Detailed fields for the selected block — over the canvas, never beside it. */
function BlockInspector({ readOnly, onDelete, onDuplicate, onNudge, onConfirmBlock, grounding, onOpenCitation, labelForType }) {
  const { appState, selectedItem, dispatch, getSelectorForId } = usePuck();
  const [open, setOpen] = useState(true);
  const blockId = selectedItem?.props?.id;

  // Selecting a different block re-opens the panel: having collapsed it once
  // should not mean the next block silently has no fields.
  useEffect(() => {
    if (blockId) setOpen(true);
  }, [blockId]);

  if (!selectedItem) return null;
  const meta = grounding?.[blockId];
  const selector = getSelectorForId(blockId);
  const index = selector?.index ?? -1;
  const total = appState?.data?.content?.length ?? 0;
  const close = () => dispatch({ type: 'setUi', ui: { itemSelector: null } });

  return (
    <aside className={`site-inspector ${open ? '' : 'collapsed'}`} aria-label="Egenskaper för valt block">
      <header className="site-inspector__head">
        <button
          type="button"
          className="site-inspector__toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <ChevronDown size={15} className={open ? 'rot' : ''} aria-hidden="true" />
        </button>
        <div className="site-inspector__title">{labelForType(selectedItem.type)}</div>
        <button type="button" className="site-inspector__close" onClick={close} aria-label="Stäng">
          <X size={15} />
        </button>
      </header>

      {open && (
        <>
          {!readOnly && (
            <div className="site-inspector__actions">
              <button type="button" onClick={() => onNudge(blockId, index - 1)} disabled={index <= 0} title="Flytta upp">
                <MoveUp size={15} />
              </button>
              <button
                type="button"
                onClick={() => onNudge(blockId, index + 1)}
                disabled={index < 0 || index >= total - 1}
                title="Flytta ner"
              >
                <MoveDown size={15} />
              </button>
              <button type="button" onClick={() => onDuplicate(index)} title="Kopiera">
                <Copy size={15} />
              </button>
              <button
                type="button"
                className="danger"
                onClick={() => onDelete(index)}
                title="Ta bort"
              >
                <Trash2 size={15} />
              </button>
            </div>
          )}

          {meta?.grounding === 'unverified' && (
            <div className="site-review">
              <div className="site-review__label">
                <ShieldAlert size={13} aria-hidden="true" /> AI-skriven text utan källa
              </div>
              <p>
                Ingen källa i föreningens dokument stöder den här texten. Läs igenom den —
                sidan går inte att publicera förrän någon står för den.
              </p>
              {!readOnly && (
                <button type="button" className="site-review__confirm" onClick={() => onConfirmBlock(blockId)}>
                  <Check size={14} aria-hidden="true" /> Bekräfta texten
                </button>
              )}
            </div>
          )}

          {meta && meta.grounding !== 'authored' && meta.grounding !== 'unverified' && (
            <div className={`site-source site-source--${meta.grounding}`}>
              <div className="site-source__label">
                <Sparkles size={13} aria-hidden="true" /> {meta.grounding_label}
              </div>
              {(meta.sources || []).map((citation, i) => (
                <button
                  key={i}
                  type="button"
                  className="site-source__cite"
                  onClick={() => onOpenCitation?.(citation)}
                >
                  <FileText size={13} aria-hidden="true" />
                  <span>
                    {citation.document_name}, s. {citation.page}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="site-inspector__fields">
            <Puck.Fields />
          </div>
        </>
      )}
    </aside>
  );
}

/**
 * The block library. A drawer over the canvas, not a permanent column.
 *
 * Every block can be added two ways, and both matter. Dragging puts it exactly
 * where the operator wants it and is what the editor is good at. Clicking adds
 * it to the end — which is how most sections actually get written, and which
 * keeps the feature usable for anyone who cannot comfortably drag: the drag
 * source alone would have made "lägg till ett avsnitt" a pointer-precision
 * task, and there is no keyboard path through a drag.
 *
 * Both end up in the same place. The drag becomes a Puck action that
 * `actionToCommands` translates; the click *is* an `insert_block` command. One
 * validator, one history, one undo.
 */
function AddBlockDrawer({ open, onClose, vocabulary, onInsertBlock }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const components = vocabulary?.components || {};
  const categories = (vocabulary?.categories || []).map((category) => ({
    category,
    blocks: Object.entries(components)
      .filter(([, spec]) => spec.category === category)
      .map(([type, spec]) => ({ type, label: spec.label, description: spec.description })),
  })).filter((group) => group.blocks.length > 0);

  return (
    <>
      <div className="site-drawer__backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="site-drawer" aria-label="Lägg till block">
        <header className="site-drawer__head">
          <h2>Lägg till block</h2>
          <button type="button" onClick={onClose} aria-label="Stäng"><X size={16} /></button>
        </header>
        <p className="site-drawer__hint">
          Dra ett block dit du vill ha det — eller klicka på plus för att lägga det sist på sidan.
        </p>
        <div className="site-drawer__list">
          <Drawer>
            {categories.map(({ category, blocks }) => (
              <section className="site-drawer__group" key={category}>
                <h3>{category}</h3>
                {blocks.map(({ type, label, description }) => (
                  <div className="site-drawer__row" key={type}>
                    <Drawer.Item name={type} label={label}>
                      {({ children }) => <div className="site-drawer__drag">{children}</div>}
                    </Drawer.Item>
                    <button
                      type="button"
                      className="site-drawer__add"
                      title={`Lägg ${label} sist på sidan — ${description}`}
                      aria-label={`Lägg till ${label}`}
                      onClick={() => { onInsertBlock(type); onClose(); }}
                    >
                      <Plus size={15} />
                    </button>
                  </div>
                ))}
              </section>
            ))}
          </Drawer>
        </div>
      </aside>
    </>
  );
}

export default function WorkspaceShell({
  brfId,
  isAdmin,
  page,
  pages,
  workspace,
  activePageId,
  onSelectPage,
  onCreatePage,
  onPublish,
  onUnpublish,
  onOpenRevisions,
  onDelete,
  onDuplicate,
  onNudge,
  onAiApplied,
  onUndo,
  onInsertBlock,
  onConfirmBlock,
  vocabulary,
  labelForType,
  onOpenCitation,
  grounding,
  syncNonce,
  syncData,
  busy,
  error,
  onDismissError,
}) {
  const [viewport, setViewport] = useState('desktop');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [aiCollapsed, setAiCollapsed] = useState(false);
  const { selectedItem, appState } = usePuck();

  const active = VIEWPORTS.find((v) => v.id === viewport) || VIEWPORTS[2];
  const canvasStyle = active.width ? { width: `${active.width}px` } : { width: '100%' };

  // What the AI needs to resolve "detta" and "den markerade texten": which block
  // is selected, which field has focus, and what is highlighted inside it.
  const selection = {
    page_id: activePageId,
    block_id: selectedItem?.props?.id || '',
    field: appState?.ui?.field?.focus || '',
    selected_text: typeof window !== 'undefined' ? (window.getSelection?.()?.toString() || '') : '',
  };

  return (
    <div className={`site-ws ${aiCollapsed ? 'ai-collapsed' : ''}`}>
      <CanvasSync nonce={syncNonce} data={syncData} />

      <AiPartner
        brfId={brfId}
        isAdmin={isAdmin}
        collapsed={aiCollapsed}
        onToggleCollapse={() => setAiCollapsed((v) => !v)}
        selection={selection}
        selectedType={selectedItem ? labelForType(selectedItem.type) : ''}
        history={workspace?.history || []}
        onApplied={onAiApplied}
        onUndo={onUndo}
        onOpenCitation={onOpenCitation}
      />

      <div className="site-main">
        <header className="site-topbar">
          <div className="site-topbar__left">
            <div className="site-pageselect">
              <Globe size={15} aria-hidden="true" />
              <select
                value={activePageId}
                onChange={(e) => {
                  if (e.target.value === '__new__') onCreatePage();
                  else onSelectPage(e.target.value);
                }}
                aria-label="Välj sida"
              >
                {pages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                    {p.home ? ' · startsida' : ''}
                  </option>
                ))}
                {isAdmin && <option value="__new__">+ Ny sida…</option>}
              </select>
              <ChevronDown size={14} aria-hidden="true" className="site-pageselect__chevron" />
            </div>
            <StatusPill page={page} />
            {(page?.needs_review?.length || 0) > 0 && (
              <span className="site-pill site-pill--review" title="AI-skriven text som ingen har bekräftat. Sidan kan inte publiceras förrän den är genomläst.">
                {page.needs_review.length} att bekräfta
              </span>
            )}
            {busy && <Loader2 size={14} className="site-spin" aria-label="Sparar" />}
          </div>

          <div className="site-topbar__center" role="group" aria-label="Visningsbredd">
            {VIEWPORTS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`site-vp ${viewport === id ? 'active' : ''}`}
                onClick={() => setViewport(id)}
                title={label}
                aria-pressed={viewport === id}
              >
                <Icon size={15} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </div>

          <div className="site-topbar__right">
            {isAdmin && (
              <button type="button" className="site-btn" onClick={() => setDrawerOpen(true)}>
                <Plus size={15} aria-hidden="true" /> Lägg till block
              </button>
            )}
            <button type="button" className="site-btn" onClick={onOpenRevisions} title="Tidigare versioner">
              <History size={15} aria-hidden="true" /> Versioner
            </button>
            {isAdmin && (
              <>
                {page?.published && (
                  <button type="button" className="site-btn" onClick={onUnpublish}>
                    Avpublicera
                  </button>
                )}
                <button
                  type="button"
                  className="site-btn site-btn--primary"
                  onClick={onPublish}
                  disabled={Boolean(page && page.published && !page.has_unpublished_changes)}
                  title={
                    page && page.published && !page.has_unpublished_changes
                      ? 'Det finns inget nytt att publicera.'
                      : 'Publicera sidan'
                  }
                >
                  Publicera
                </button>
              </>
            )}
          </div>
        </header>

        {error && (
          <div className="site-error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={onDismissError} aria-label="Stäng">
              <X size={14} />
            </button>
          </div>
        )}

        <div className="site-canvas-area">
          <div
            className={`site-canvas site-canvas--${viewport}`}
            style={canvasStyle}
            data-testid="site-canvas"
          >
            <Puck.Preview />
          </div>
        </div>

        <BlockInspector
          readOnly={!isAdmin}
          onDelete={onDelete}
          onDuplicate={onDuplicate}
          onNudge={onNudge}
          onConfirmBlock={onConfirmBlock}
          grounding={grounding}
          onOpenCitation={onOpenCitation}
          labelForType={labelForType}
        />

        <AddBlockDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          vocabulary={vocabulary}
          onInsertBlock={onInsertBlock}
        />
      </div>
    </div>
  );
}
