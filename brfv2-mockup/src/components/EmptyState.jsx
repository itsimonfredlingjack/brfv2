/**
 * The empty state, composed once for every screen that has one.
 *
 * Each screen used to draw its own emptiness, and in a pilot every screen is
 * empty — so this composition is the first thing a board sees, three or four
 * times, before it has seen a single row of real work. It was drawn three
 * different ways: a grey ring that read as a spinner stuck mid-load
 * (Uppgifter), the brand mark pressed into service as an illustration
 * (Inkommande), and on Hemsidan two zeros and then nothing at all.
 *
 * The composition is the one this product uses everywhere else — a statement
 * in the assertion cut, a lead under it in plain Swedish, at most one action —
 * set at the left gutter like every other statement on the page. It is not
 * centred and it carries no glyph: an empty screen is a sentence the document
 * is making, not a widget reporting its own condition. Centring was what made
 * it read as a widget; it was the only thing on these screens that did not
 * start where everything else starts.
 *
 * What separates "nothing has arrived yet" from "everything is handled" is the
 * sentence, not a mark. The ring had two states and told nobody which was
 * which; a heading that says "Allt är hanterat." cannot be misread. That is
 * why `tone` is gone rather than restyled.
 *
 *   title     the state, as a whole sentence. The largest thing here.
 *   children  what would fill the screen. One or two sentences.
 *   actions   what a person can do about it. Primary when the action creates
 *             the missing content, outline when it only navigates.
 */
export default function EmptyState({ title, children, actions }) {
  return (
    <div className="ui-empty">
      <p className="ui-empty-title">{title}</p>
      {children ? <p className="ui-empty-body">{children}</p> : null}
      {actions ? <div className="ui-empty-actions">{actions}</div> : null}
    </div>
  );
}
