/**
 * Träff's mark. Two marks, one form — the identity's hardest rule (§01).
 *
 * `variant="brand"` is **A · Varumärket**: always complete, always monochrome.
 * Here the circle is a name. It says who is speaking, not what is true, which
 * is why it never carries a state colour — not green, not even in marketing.
 *
 * `variant="status"` is **B · Statusmärket**: empty until the proof exists. The
 * core is drawn in the same moment a passage has been verified verbatim, and
 * not a millisecond earlier. A filled core without a citation is a lie told in
 * the shape.
 *
 * The geometry is fixed (§02): the ring is 8 % of the outer diameter, the gap
 * is always empty — no tint, no gradient, it *is* the distance between the
 * question and the proof — and the core is 46 % of the inner measure, always
 * concentric, because a hit never sits off-centre. Below 16 px the gap stops
 * reading and the identity's own fallback is the solid dot without a ring.
 *
 * Accessibility (§01): the status mark is the primary visual state indicator
 * and never the only one. Every state carries its own text label in mono beside
 * it, so `decorative` is the normal case here — announcing "Ej belagt, Ej
 * belagt" is not more accessible than announcing it once.
 */

export type MarkState = 'vila' | 'soker' | 'belagt' | 'ejbelagt'

const STATE_LABEL: Record<MarkState, string> = {
  vila: 'Vilande',
  soker: 'Söker',
  belagt: 'Belagt',
  ejbelagt: 'Ej belagt',
}

export function TraffMark({
  size = 22,
  variant = 'brand',
  state = 'belagt',
  title,
  decorative = false,
}: {
  size?: number
  variant?: 'brand' | 'status'
  state?: MarkState
  title?: string
  decorative?: boolean
}) {
  const ring = Math.max(1.4, size * 0.08)
  const inner = size - ring * 2
  const core = inner * 0.46

  if (size < 16) {
    return (
      <span
        className="mark mark--dot"
        style={{ width: size, height: size }}
        aria-hidden="true"
      />
    )
  }

  const shown = variant === 'brand' ? 'brand' : state
  const label = title ?? (variant === 'brand' ? 'Träff' : STATE_LABEL[state])

  return (
    <span
      className={`mark mark--${shown}`}
      style={{ width: size, height: size, borderWidth: `${ring}px` }}
      role={decorative ? undefined : 'img'}
      aria-hidden={decorative ? 'true' : undefined}
      aria-label={decorative ? undefined : label}
    >
      {/* The core exists only where something has actually been established. */}
      {(shown === 'brand' || shown === 'belagt') && (
        <span className="mark__core" style={{ width: core, height: core }} />
      )}
    </span>
  )
}
