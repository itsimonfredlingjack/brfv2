import './Instrument.css';

/**
 * The instrument — the band at the foot of every page header that states what
 * the screen is currently measuring.
 *
 * It used to have no name. The markup was hand-copied across eight screens
 * under two borrowed class names (`invoices-ledger` and `watches-standing`),
 * so Dokument was literally built out of Fakturor's and Bevakningar's parts.
 * That meant there was no instrument to change: editing the rule that set the
 * big figure moved three unrelated screens at once, and the only way to touch
 * one of them was a scoped override, each of which made the next change
 * harder. Naming the thing once is what makes per-screen design possible again.
 *
 * An instrument is the one figure the screen came for, followed by the readings
 * that qualify it.
 *
 * It used to take a `lead` as well — a chart standing where the figure would,
 * for Bevakningar's horizon. That slot is gone. The band is one fixed height on
 * every workspace and the row this leaves for the instrument comes to 108px; a
 * twelve-month chart measures 192px and simply overflowed, drawing itself
 * through the section below. A figure with an axis is not a reading, and the
 * band is not where it goes.
 *
 *   label     caption for the big figure.
 *   value     the big figure itself.
 *   readings  [{ label, value, flagged }] — `flagged` is lateness, which
 *             refuses red everywhere in this product and underlines instead.
 *   raw       the figure's underlying number, when it has one. Only used to
 *             tell nothing from something — see below. Money arrives from the
 *             backend as a decimal *string* ("0"), so this is compared by
 *             value, not identity; `raw={0}` and `raw="0.00"` mean the same
 *             thing. Absent, null or empty means "not known yet", which is not
 *             the same as zero and must keep the figure.
 *   vila      what to say when `raw` is 0. Defaults to "Inget att visa".
 *
 * A screen with no figure (Uppgifter, Bevakningar) has its readings promoted to
 * the figure's size — see Instrument.css. That rule is derived from the markup
 * rather than declared per screen, so a screen cannot get it wrong.
 *
 * Zero is not a measurement.
 *
 * Fakturor at rest set "0,00 SEK" in mono at display scale: the largest thing
 * on the screen, in the face this product reserves for measurement, reporting
 * the absence of anything to measure. §07 is what settles it — "serif för det
 * som påstås, sans för det som förklaras, mono för det som mäts." There is no
 * sum here to measure; there is a state to explain. So at zero the figure
 * leaves the mono and says the state in the sans instead, at a size that hands
 * the screen back to whatever the board should look at next.
 *
 * The typeface carries the meaning, which is why this is a derived rule and
 * not a per-screen variant class: a screen passes the number it already has
 * and cannot choose to render its own zero loudly.
 *
 * And an instrument with nothing to measure does not draw at all.
 *
 * That half of the rule was missing, and it was the page grammar's worst
 * offender. The figure knew about zero; the readings did not. So Uppgifter
 * opened on 0 / 0 / 0, Hemsidan on 0 / 0, Inkommande on 0 / 0 / 0 — the least
 * informative row on the page, set in the largest numerals on the page, above
 * the one sentence that actually said something. Four of the seven workspaces
 * are empty in the pilot, and this is what a board sees first in all four.
 *
 * The band itself stays: it carries the screen's name and is the reason the
 * workspaces read as one product, and it reads at zero data. What is gated is
 * the measurement inside it, and the test is the whole instrument rather than
 * each number — a single "1" among zeros is a distribution and keeps its
 * siblings, because 1 / 0 / 0 says something 1 alone does not.
 *
 * The rule is here rather than at the seven call sites for the usual reason:
 * seven screens deciding this separately is seven chances to decide it wrong,
 * and the last five passes all left at least one screen behind.
 *
 * The known cost: a screen whose board has not arrived computes zeros from an
 * empty object, so its band opens short and grows by the instrument's row when
 * the fetch lands. That is a shift on first entry to a tab, and it is the
 * cheaper of the two — the alternative is a strip of reserved white above
 * every empty workspace for as long as the association stays empty, which in
 * a pilot is the whole of it.
 */
export default function Instrument({
  label, value, raw, vila, readings = [], className = '',
}) {
  const hasFigure = label !== undefined || value !== undefined;
  const vilande = raw !== undefined && raw !== null && raw !== '' && Number(raw) === 0;

  // `value` may already be formatted for reading ("0,00 SEK"), which is why
  // `raw` exists; a value that is still a number is its own raw. Anything
  // unstated (undefined, null, "") is not zero — it is not known yet — and
  // anything non-numeric is a state rather than a count, so both keep the
  // instrument on screen.
  const nagot = (v) => {
    if (v === undefined || v === null || v === '') return false;
    const n = Number(v);
    return Number.isNaN(n) ? true : n !== 0;
  };
  const matning = [
    raw !== undefined ? raw : (hasFigure ? value : undefined),
    ...readings.map((r) => r.value),
  ].some(nagot);
  if (!matning) return null;

  return (
    <div className={['instrument', className].filter(Boolean).join(' ')}>
      {hasFigure && (
        <div className={`instrument-figure${vilande ? ' vilande' : ''}`}>
          <span className="instrument-label">{label}</span>
          <span className="instrument-amount">{vilande ? (vila || 'Inget att visa') : value}</span>
        </div>
      )}
      {readings.length > 0 && (
        <dl className="instrument-readings">
          {readings.map((reading) => (
            <div key={reading.label} className={reading.flagged ? 'flagged' : ''}>
              <dt>{reading.label}</dt>
              <dd>{reading.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
