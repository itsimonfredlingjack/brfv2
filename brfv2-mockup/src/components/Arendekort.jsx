import Tillstand from './Tillstand';
import './Arendekort.css';

/**
 * Ärendekortet — one case, shown the way this product shows a document.
 *
 * It replaces a register: an eight-column table that optimised for taking in
 * forty rows at once. A board does not do that. A board works through a
 * handful of cases on a weeknight and needs to understand each one — what it
 * is, what the product decided about it, and what that decision rests on. So
 * the card optimises for understanding one, and a case taking up room is the
 * point rather than a cost.
 *
 * The shape is a specimen: the thing, then its facts stated underneath in
 * small mono, separated by · — the same pattern a reference page uses to
 * caption a component with its properties. It suits this product better than
 * it suits the page it was borrowed from, because Träff has more to put on
 * that line than a design system does.
 *
 *   tillstand   { form, text } — see Tillstand.jsx. Shape, never colour alone.
 *   namn        what the case is about; the reader's anchor.
 *   figur       the one number, right-aligned against the name.
 *   children    why the product decided what it decided, in plain Swedish.
 *               This is the part a table had no room for at all.
 *   fakta       [{ etikett, varde, matt }] — the mono row. `matt: true` sets
 *               the value as arithmetic (tabular, ink) rather than as a label's
 *               value: lateness and counts, the things that are computed.
 *   kalla       { text, onOpen } — the citation. It gets its own line and is
 *               never folded into `fakta`, because it is the product's whole
 *               promise: an answer says which document it came out of. A
 *               screen with no citation data passes nothing and the line does
 *               not appear — better a missing line than a fabricated one.
 *   onOpen      opens the case. The whole card becomes the target, so it is
 *               mutually exclusive with `atgarder` — a button cannot contain
 *               buttons.
 *   atgarder    controls belonging to this case, below the facts. For screens
 *               where the decision is made on the card rather than behind it.
 */
export default function Arendekort({
  tillstand, namn, figur, children, fakta = [], kalla, atgarder, onOpen,
}) {
  const Rot = onOpen ? 'button' : 'article';
  return (
    <Rot
      type={onOpen ? 'button' : undefined}
      className={`arendekort${onOpen ? ' arendekort--oppnbar' : ''}`}
      onClick={onOpen}
    >
      {tillstand && <Tillstand form={tillstand.form}>{tillstand.text}</Tillstand>}

      <div className="arendekort-huvud">
        <span className="arendekort-namn">{namn}</span>
        {figur !== undefined && <span className="arendekort-figur">{figur}</span>}
      </div>

      {children && <p className="arendekort-motiv">{children}</p>}

      {fakta.length > 0 && (
        <div className="arendekort-fakta">
          {fakta.map((f, i) => (
            <span key={f.etikett} className="arendekort-fakta-post">
              {i > 0 && <span className="arendekort-avdelare" aria-hidden="true">·</span>}
              <span className="arendekort-fakta-etikett">{f.etikett}</span>{' '}
              <span className={f.matt ? 'arendekort-matt' : 'arendekort-varde'}>{f.varde}</span>
            </span>
          ))}
        </div>
      )}

      {kalla && (
        <div className="arendekort-kalla">
          <span className="arendekort-fakta-etikett">källa</span>{' '}
          {kalla.onOpen ? (
            <button
              type="button"
              className="arendekort-kalla-lank"
              onClick={(e) => { e.stopPropagation(); kalla.onOpen(); }}
            >
              {kalla.text}
            </button>
          ) : (
            <span className="arendekort-varde">{kalla.text}</span>
          )}
        </div>
      )}

      {atgarder && <div className="arendekort-atgarder">{atgarder}</div>}
    </Rot>
  );
}
