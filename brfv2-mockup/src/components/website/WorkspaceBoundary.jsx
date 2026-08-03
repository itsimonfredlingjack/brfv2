import React from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Keeps a failure inside the website workspace from taking the product down.
 *
 * This is not defensive decoration. The editor this workspace embeds brings its
 * own drag-and-drop and rich-text engines, and one of their dependencies throws
 * at module scope in the WebKitGTK build the desktop shell renders in
 * (`TypeError: Attempted to assign to readonly property`, from
 * `@preact/signals-core` by way of `@dnd-kit`). Imported at startup, that
 * blanked the **whole application** — documents, invoices, incoming post, the
 * login form — before anybody had opened a website.
 *
 * Two things stop that now, and they are independent on purpose. The workspace
 * is loaded only when somebody opens it (see `appWorkspaces.jsx`), so the
 * failure cannot happen during boot; and this boundary catches it when it does
 * happen, so the worst case is one screen saying what went wrong while the rest
 * of the product keeps working.
 *
 * The message says which engine and which component, because the operator who
 * hits this is running an installed application and their next useful act is to
 * report exactly that.
 */
export default class WorkspaceBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    // Logged rather than swallowed: the desktop build ships a console nobody
    // reads by default, but the acceptance journey and any support session do.
    console.error('[hemsidan] arbetsytan kunde inte startas:', error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="site-broken" role="alert">
        <AlertTriangle size={26} aria-hidden="true" />
        <h1>Webbplatsarbetsytan kunde inte startas</h1>
        <p>
          Redigeraren gick inte att läsa in i den här versionen av programmet. Resten
          av produkten — dokument, fakturor, inkommande post och uppgifter — fungerar
          som vanligt, och ingenting på föreningens webbplats har ändrats.
        </p>
        <p className="site-broken__detail">
          {String(this.state.error?.message || this.state.error)}
        </p>
        <p className="site-broken__hint">
          Rapportera felet ovan tillsammans med vilken version av programmet du kör.
        </p>
      </div>
    );
  }
}
