/**
 * When something happened, said the way a Swede says it.
 *
 * This was written out four times — in IntakeQueue, Tasks, Watches and
 * InvoiceCase — as the same nine lines with the same options, and twice more as
 * a bare `iso.slice(0, 10)` in Dokument and the invoice register, which is why
 * those two tables printed `2026-08-09` at a board. Six copies of one idea, and
 * so no date format to change: that is the same failure the instrument had.
 *
 * `2026-08-09` is a timestamp, not a date. It is sorted, zero-padded and
 * unambiguous because it was written for a machine, and a register full of them
 * reads as a log file. A board reads `9 aug. 2026`. The information is
 * identical; only the reader changed.
 *
 * The year is dropped inside the current year — "9 aug." is what a person says
 * in August 2026, and carrying "2026" down a whole column only adds a number
 * that is the same on every row. It comes back the moment a date is in another
 * year, because then it is the part that matters.
 */

const nu = () => new Date();

/** A day: "9 aug." this year, "9 aug. 2025" otherwise. */
export function datum(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString('sv-SE', {
    day: 'numeric',
    month: 'short',
    ...(d.getFullYear() === nu().getFullYear() ? {} : { year: 'numeric' }),
  });
}

/** A moment: the day, plus the time it happened at. */
export function datumTid(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const klocka = d.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' });
  return `${datum(iso)} ${klocka}`;
}
