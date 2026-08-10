import React from 'react';
import TraffMark from './TraffMark';

/**
 * The one empty state, shared by every section — and now the one glyph too.
 * A different Lucide icon per section (inbox, clipboard, receipt…) said
 * "generic empty widget" six different ways; the ring says the one thing
 * that's actually true here in the app's own language: nothing has been
 * established yet (vila), or everything that needed proving has been
 * (tone="ok" → belagt). Same mark as the rest of the identity, not a
 * decoration invented for this one spot.
 *
 * An empty screen is information, not a loading failure: the sentence says
 * what is missing and what would fill it, and the action — when there is
 * one — is the thing a person can do about it. Primary when the action
 * creates the missing content, outline when it only navigates. Tone "ok" is
 * for emptiness that means "all handled" rather than "nothing here yet".
 *
 * No engine fills this in: the action always does what a human could have
 * done from the section's own toolbar.
 */
export default function EmptyState({ tone, title, children, actions }) {
  return (
    <div className={`ui-empty${tone === 'ok' ? ' ui-empty--ok' : ''}`}>
      <div className="ui-empty-media">
        <TraffMark size={40} variant="status" state={tone === 'ok' ? 'belagt' : 'vila'} decorative />
      </div>
      <p className="ui-empty-text">
        <strong className="ui-empty-title">{title}</strong>
        {children ? <span className="ui-empty-body">{children}</span> : null}
      </p>
      {actions ? <div className="ui-empty-actions">{actions}</div> : null}
    </div>
  );
}
