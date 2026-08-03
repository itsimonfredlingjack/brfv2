import React, { useEffect, useRef, useState } from 'react';
import { registerOverlayPortal } from '@puckeditor/core';
import './site.css';

// The presentational primitives every BRF block is built from.
//
// Separate from websiteConfig.jsx so that file can be what it is — the wiring
// between this product's component vocabulary and the editor — while these stay
// what they are: plain React that renders the association's public page, in the
// editor canvas and on the published site alike, with no idea which of the two
// it is in.

/**
 * Rich text, rendered whichever way the editor hands it over.
 *
 * In the canvas a richtext field arrives as a React node (Tiptap's own
 * rendering, which is what makes it editable in place); the stored value is an
 * HTML string. Handling both rather than assuming one keeps the published
 * renderer correct without depending on an internal of the editor library.
 *
 * The string branch is `dangerouslySetInnerHTML`, and that is safe *by
 * construction* rather than by convention: every character of it passed
 * backend/app/website/sanitize.py's whitelist before it could be stored, on the
 * human path and the AI path alike, and that check refuses rather than strips.
 */
export function Prose({ value, className = 'blk__prose', placeholder }) {
  if (value && typeof value !== 'string') {
    return <div className={className}>{value}</div>;
  }
  const html = typeof value === 'string' ? value.trim() : '';
  if (!html || html === '<p></p>') {
    return placeholder ? <div className={className}><p className="blk__placeholder">{placeholder}</p></div> : null;
  }
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Button({ action }) {
  if (!action?.href || !action?.label) return null;
  return <a className="blk__button" href={action.href}>{action.label}</a>;
}

export function Media({ image, className, emptyHint }) {
  if (!image?.src) {
    return (
      <div className={`${className} ${className}--empty`}>
        {emptyHint || 'Ingen bild vald'}
      </div>
    );
  }
  return <div className={className}><img src={image.src} alt={image.alt || ''} /></div>;
}

/**
 * A folding question that stays foldable while the canvas is an editor.
 *
 * Without the overlay portal every click on a question would be captured as the
 * start of a drag, so the one block whose whole point is that it opens and
 * closes would be the one block nobody could try before publishing it.
 */
export function FaqItem({ question, answer, defaultOpen }) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  const ref = useRef(null);
  useEffect(() => registerOverlayPortal(ref.current), []);

  return (
    <div className="blk-faq__item" data-open={open ? 'true' : 'false'}>
      <button
        ref={ref}
        type="button"
        className="blk-faq__q"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {question}
      </button>
      {open ? <div className="blk-faq__a"><Prose value={answer} /></div> : null}
    </div>
  );
}
