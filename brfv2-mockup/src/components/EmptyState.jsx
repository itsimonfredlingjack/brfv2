import React from 'react';

/**
 * The one empty state, shared by every section.
 *
 * An empty screen is information, not a loading failure: the tile says which
 * section this is, the sentence says what is missing and what would fill it,
 * and the action — when there is one — is the thing a person can do about it.
 * Primary when the action creates the missing content, outline when it only
 * navigates. Tone "ok" is for emptiness that means "all handled" rather than
 * "nothing here yet".
 *
 * No engine fills this in: the action always does what a human could have
 * done from the section's own toolbar.
 */
export default function EmptyState({ icon: Icon, tone, title, children, actions }) {
  return (
    <div className={`ui-empty${tone === 'ok' ? ' ui-empty--ok' : ''}`}>
      <div className="ui-empty-media"><Icon size={22} aria-hidden="true" /></div>
      <p className="ui-empty-text">
        <strong>{title}</strong> {children}
      </p>
      {actions ? <div className="ui-empty-actions">{actions}</div> : null}
    </div>
  );
}
