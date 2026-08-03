import React, { Suspense, lazy } from 'react';
import WorkspaceBoundary from './WorkspaceBoundary';

// How the website workspace is loaded, and why it is not loaded like the others.
//
// The editor it embeds brings its own drag-and-drop and rich-text engines, and
// one of their dependencies throws at module scope in the WebKitGTK build the
// desktop shell renders in. Imported with the rest of the workspaces, that took
// the **whole application** down at startup — a blank window before the login
// form, with no indication that a website editor was the reason.
//
// So it is loaded when somebody opens it, behind a boundary that catches it if
// it fails. The cost of the editor is then paid by the screen that needs it,
// and a failure there is one screen's problem rather than the product's.
//
// Both halves matter and neither replaces the other: lazy loading keeps the
// failure out of startup, the boundary keeps it out of everything else.
const Website = lazy(() => import('./Website'));

export default function WebsiteWorkspace(props) {
  return (
    <WorkspaceBoundary>
      <Suspense fallback={<div className="site-loading">Läser webbplatsen…</div>}>
        <Website {...props} />
      </Suspense>
    </WorkspaceBoundary>
  );
}
