// Swedish date rendering for the published site.
//
// Deliberately tiny and dependency-free: the stored value is always ISO
// (ÅÅÅÅ-MM-DD, which is what the backend validates and what sorts correctly),
// and these are the only two ways the site ever shows one.

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

/** "2026-03-12" → "12 mar 2026". An unparseable value is shown as-is, never guessed at. */
export function formatDate(iso) {
  if (!iso || typeof iso !== 'string') return '';
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${Number(d)} ${MONTHS[Number(m) - 1] || m} ${y}`;
}

/** The day/month split the calendar block prints as a tear-off date. */
export function splitDate(iso) {
  const [, m, d] = (iso || '').split('-');
  return { day: d ? String(Number(d)) : '–', month: MONTHS[Number(m) - 1] || '' };
}
