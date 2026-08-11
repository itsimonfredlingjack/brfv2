import './Tillstand.css';

/**
 * Tillståndet — what the product currently knows about one case.
 *
 * The distinction it has to carry is the product's whole reason to exist: a
 * figure that was checked verbatim against a contract, versus one that was
 * not. That has to read across a room, in a list, without being read.
 *
 * It is drawn as *shape*, not colour. Filled means proven; a dashed outline
 * means nothing was found to prove it against. Two earlier attempts carried
 * this in hue — a green pill and an amber pill — and both failed the same way:
 * on a light ground an accent has to be dark enough to survive, at which point
 * every accent converges on the same muddy weight and the register stops being
 * scannable. Shape has none of that problem, and it survives colour-blindness
 * and a bad projector.
 *
 * Five forms, and the line runs solid → dashed as the product's grounds run
 * from firm to none:
 *
 *   belagd    filled ink      checked against a contract, and it matches
 *   avviker   solid outline   checked against a contract, and it does not.
 *                             Solid because there *is* a basis — this is a
 *                             finding, not an absence.
 *   oprovad   dashed outline  no contract found; nothing to check against
 *   neutral   hairline        nothing flagged either way — the case's review
 *                             status is all that is true about it yet
 *   fel       tinted          the run broke; a machine fault, never something
 *                             the document did
 *
 * `pulserar` puts a pulsing dot in front. It is the only motion in the
 * language and it belongs to one meaning: work happening right now.
 */
const FORMER = new Set(['belagd', 'avviker', 'oprovad', 'neutral', 'fel']);

export default function Tillstand({ form, pulserar, children }) {
  const klass = FORMER.has(form) ? form : 'neutral';
  return (
    <span className={`tillstand tillstand--${klass}`}>
      {pulserar && <i className="tillstand-punkt" aria-hidden="true" />}
      {children}
    </span>
  );
}
