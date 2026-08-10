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
 * An instrument is a lead — the one figure the screen came for, or a chart that
 * plays that part — followed by the readings that qualify it.
 *
 *   lead      a chart standing where the figure would (Bevakningar's horizon).
 *             Pass `null` rather than omitting it while the data is still
 *             loading: the shape then holds its size instead of jumping when
 *             the chart lands.
 *   label     caption for the big figure.
 *   value     the big figure itself.
 *   readings  [{ label, value, flagged }] — `flagged` is lateness, which
 *             refuses red everywhere in this product and underlines instead.
 *
 * A screen with neither lead nor figure (Uppgifter) has its readings promoted
 * to the figure's size — see Instrument.css. That rule is derived from the
 * markup rather than declared per screen, so a screen cannot get it wrong.
 */
export default function Instrument({ lead, label, value, readings = [], className = '' }) {
  const hasLead = lead !== undefined;
  const hasFigure = label !== undefined || value !== undefined;

  return (
    <div className={['instrument', className].filter(Boolean).join(' ')}>
      {hasLead && <div className="instrument-lead">{lead}</div>}
      {hasFigure && (
        <div className="instrument-figure">
          <span className="instrument-label">{label}</span>
          <span className="instrument-amount">{value}</span>
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
