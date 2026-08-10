import './Hogen.css';

/**
 * Högen — the identity's one image motif (§04), on the screen that is about it.
 *
 * "Materialet är fysiskt — en hög papper med mätbart djup — och sökljuset går
 * rakt igenom det. En enda sida lyser. Använd motivet stort, aldrig som liten
 * dekor, och alltid med sidnumret utsatt."
 *
 * The empty state used to be a title, two example questions and a void, under a
 * composer whose placeholder says "Fråga rakt in i högen…" — the product named
 * its own central image in the copy and then showed nothing. This is that image,
 * at the size §04 asks for.
 *
 * It is a diagram of the mechanism rather than decoration, and it is built from
 * the archive that is actually loaded: one leaf per searchable page, so the pile
 * a board sees is the depth of the material they are about to ask a question of.
 * An association with four documents gets a thin pile. That is the honest
 * picture, and it is the argument for uploading more.
 *
 * The light sweeps once, on arrival, and stops. A loop would make the screen
 * restless and turn a claim about how the product works into an ornament.
 */

const MAX_LEAVES = 18;

export default function Hogen({ pages, documents }) {
  // The pile is the archive, but a thousand-page association cannot be drawn
  // leaf by leaf. Past the cap the pile stays full and the number carries the
  // rest — which is why §04 insists the page number is always shown.
  const leaves = Math.max(3, Math.min(pages || 0, MAX_LEAVES));

  // The lit page is fixed, not random: a different sheet on every render would
  // read as animation rather than as the one page an answer came from.
  const lit = Math.floor(leaves * 0.42);
  const sida = Math.max(1, Math.round((lit / leaves) * (pages || leaves)));

  return (
    <figure className="hogen" aria-hidden="true">
      <div className="hogen-stack" style={{ '--leaves': leaves }}>
        {Array.from({ length: leaves }, (_, i) => (
          <span
            key={i}
            className={`hogen-leaf${i === lit ? ' lit' : ''}`}
            style={{ '--i': i, '--skew': `${((i * 37) % 9) - 4}px` }}
          />
        ))}
        <span className="hogen-beam" />
      </div>
      <figcaption className="hogen-caption">
        <span className="matt">Sida {sida} av {pages || leaves}</span>
        <span className="hogen-punkt" aria-hidden="true">·</span>
        <span className="hogen-of">
          {documents === 1 ? '1 dokument' : `${documents} dokument`} genomlysta
        </span>
      </figcaption>
    </figure>
  );
}
