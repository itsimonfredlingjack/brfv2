/**
 * Money on screen, in one place.
 *
 * Amounts arrive from the backend as JSON *strings*, never numbers: every
 * amount in this domain is a `Decimal` server-side, because a comparison
 * decides whether a finding says "överensstämmer" or "möjlig avvikelse" and
 * `12500.10 !== 12500.099999999999` matters when it does. The string survives
 * the wire exactly; this function is the only place it becomes a float, and it
 * does so purely to be displayed.
 *
 * A value that will not parse is shown as it arrived rather than as `NaN` — a
 * number nobody can read is better than a number that is wrong.
 */
export function formatAmount(value, currency = 'SEK') {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (Number.isNaN(number)) return `${value} ${currency}`;
  return `${number.toLocaleString('sv-SE', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })} ${currency}`;
}

export default formatAmount;
