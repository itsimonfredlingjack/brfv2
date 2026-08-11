import './Avsnitt.css';

/**
 * Avsnittet — a numbered section, the way a document numbers its paragraphs.
 *
 * The device is an eyebrow in uppercase mono over a heading, and it is only
 * worth having because the number means something here. Numbered markers are
 * the first thing a templated design reaches for and they are usually a lie:
 * three cards labelled 01/02/03 that are not a sequence. In this product the
 * page a board is reading really is organised the way a contract is — §-marks,
 * numbered clauses, ordered sections — and §07 already gives paragraph marks
 * to the mono. So the eyebrow is content, not decoration.
 *
 * Pass `nummer` only when the section genuinely sits in an order the reader
 * needs. A screen with one section does not number it.
 *
 *   nummer     "01", or "§ 3" — whatever the document itself calls it.
 *   namn       the heading, in the assertion cut.
 *   children   one or two sentences saying what is in here. Not a subtitle
 *              restating the heading — a lead that tells you what you are
 *              about to read.
 *   atgard     an optional control belonging to the section, on the same line
 *              as the heading.
 */
export default function Avsnitt({ nummer, namn, children, atgard, id }) {
  return (
    <section className="avsnitt" id={id}>
      {(nummer || namn) && (
        <header className="avsnitt-huvud">
          <div>
            {nummer && <div className="avsnitt-nummer">{nummer}</div>}
            {namn && <h2 className="avsnitt-namn">{namn}</h2>}
          </div>
          {atgard && <div className="avsnitt-atgard">{atgard}</div>}
        </header>
      )}
      {children && <p className="avsnitt-ingress">{children}</p>}
    </section>
  );
}
