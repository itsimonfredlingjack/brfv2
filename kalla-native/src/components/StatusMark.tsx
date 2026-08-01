import { useEffect, useId } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Animated, {
  cancelAnimation,
  Easing,
  interpolate,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg'

import { coreSizeFor, mark, ringWeightFor } from '../theme/brand'
import { color, font, motion, radius, space } from '../theme/tokens'

/**
 * ◉ · B · STATUSMÄRKET — the mark reporting a result (identity §01, §03).
 *
 * The whole dramaturgy is that the middle stays empty all the way up to the
 * evidence: "Läs raden vänster till höger: mitten är tom hela vägen fram
 * till belägget." So `belagt` is the ONLY state that draws a core, and it
 * draws it at the moment a passage is verified verbatim — never earlier.
 *
 *   vila      tyst tom ring, 30 % opacitet, ingen rörelse
 *   soker     bruten ring + diffust sken, ingen kärna (inget är belagt än)
 *   belagt    kärnan slår till: 40 → 116 → 100 % på 460 ms
 *   ejbelagt  ringen håller, mitten helt tom — Träff hittar aldrig på en kärna
 *
 * Never the sole signal. §01 TILLGÄNGLIGHET: the mark is the *primary*
 * visual status indicator, never the only one — every state carries its mono
 * text label, so status never rides on colour or shape alone, for a screen
 * reader or for someone who does not separate green from amber. `StatusChip`
 * is the paired form; a bare `StatusMark` is only correct next to a label
 * that already says the same thing.
 */
export type MarkState = 'vila' | 'soker' | 'belagt' | 'ejbelagt'

/**
 * The mono label each state must carry (§01). `vila` has none on purpose: it
 * asserts nothing, so it has nothing to report.
 */
export const STATUS_LABEL: Record<MarkState, string | null> = {
  vila: null,
  soker: 'SÖKER',
  belagt: 'BELAGT',
  ejbelagt: 'EJ BELAGT',
}

/** Spoken form of each state, so the symbol is never mute to a screen reader. */
export const STATUS_SPOKEN: Record<MarkState, string> = {
  vila: 'Ingen fråga ställd',
  soker: 'Söker',
  belagt: 'Belagt',
  ejbelagt: 'Ej belagt',
}

/** Resting opacity of the mark at rest (§03 VILA: "30 % opacitet"). */
const VILA_RING = 'rgba(236,237,239,0.3)'

const TINT: Record<MarkState, string> = {
  vila: VILA_RING,
  soker: color.light,
  belagt: color.grounded,
  ejbelagt: color.refusal,
}

/** Halos are the identity's large-format treatment; at chip scale they are
 *  noise, and the identity's own product mockup draws the chip without one. */
const HALO_FROM = 40

/** §03 SÖKER: the ring rotates once every 1.05 s, linear. */
const SEEK_SPIN = 1050
/** §03 SÖKER: the sken breathes .22 → .7 and back. */
const BREATHE = 1500
/** §03 BELAGT: "Skalar 40 → 116 → 100 % på 460 ms." */
const LOCK = motion.heroFlight
/** §03 BELAGT: the shock ring that leaves the mark as the core lands. */
const SHOCK = 900

export function StatusMark({ state, size = 20 }: { state: MarkState; size?: number }) {
  const reduced = useReducedMotion()
  const weight = ringWeightFor(size)
  const core = coreSizeFor(size)
  const tint = TINT[state]

  const spin = useSharedValue(0)
  const breathe = useSharedValue(0)
  // The core starts invisible and the shock starts already spent. Both must
  // be in their *finished-for-the-wrong-state* position on the very first
  // frame: a core that exists for even one frame before the evidence lands
  // is the exact lie the identity forbids.
  const lock = useSharedValue(0)
  const shock = useSharedValue(1)

  useEffect(() => {
    if (state !== 'soker' || reduced) {
      // A static broken ring is the identity's own reduced-motion variant
      // (§03 draws `motionOff` as the same arc, simply not turning).
      spin.value = 0
      breathe.value = 0.5
      return
    }
    spin.value = 0
    spin.value = withRepeat(withTiming(360, { duration: SEEK_SPIN, easing: Easing.linear }), -1, false)
    breathe.value = withRepeat(
      withTiming(1, { duration: BREATHE, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    )
    return () => {
      cancelAnimation(spin)
      cancelAnimation(breathe)
    }
  }, [state, reduced, spin, breathe])

  useEffect(() => {
    if (state !== 'belagt') return
    if (reduced) {
      // The core still appears — it is the evidence, not decoration. Only the
      // strike is dropped.
      lock.value = 1
      shock.value = 1
      return
    }
    lock.value = 0
    shock.value = 0
    lock.value = withTiming(1, { duration: LOCK, easing: Easing.bezier(...motion.easing) })
    shock.value = withTiming(1, { duration: SHOCK, easing: Easing.bezier(...motion.easing) })
    return () => {
      cancelAnimation(lock)
      cancelAnimation(shock)
    }
  }, [state, reduced, lock, shock])

  const spinStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value}deg` }] }))
  const breatheStyle = useAnimatedStyle(() => ({ opacity: interpolate(breathe.value, [0, 1], [0.22, 0.7]) }))
  const coreStyle = useAnimatedStyle(() => ({
    opacity: interpolate(lock.value, [0, 0.58, 1], [0, 1, 1]),
    transform: [{ scale: interpolate(lock.value, [0, 0.58, 1], [0.4, 1.16, 1]) }],
  }))
  const shockStyle = useAnimatedStyle(() => ({
    opacity: interpolate(shock.value, [0, 1], [0.8, 0]),
    transform: [{ scale: interpolate(shock.value, [0, 1], [0.9, 2.1]) }],
  }))

  const showHalo = size >= HALO_FROM

  return (
    <View style={{ width: size, height: size }} importantForAccessibility="no-hide-descendants">
      {showHalo && state === 'soker' && (
        <Animated.View style={[haloBox(size, 1.12), breatheStyle]} pointerEvents="none">
          <Halo size={size * 1.12} tint={color.light} peak={0.16} edge="0.58" />
        </Animated.View>
      )}
      {showHalo && state === 'belagt' && (
        <View style={haloBox(size, 1.26)} pointerEvents="none">
          <Halo size={size * 1.26} tint={color.grounded} peak={0.2} edge="0.58" />
        </View>
      )}

      {state === 'soker' ? (
        <>
          {/* The material is still there while the light sweeps it. */}
          <View
            style={[
              styles.ring,
              { width: size, height: size, borderRadius: size / 2, borderWidth: weight, borderColor: 'rgba(207,224,255,0.12)' },
            ]}
          />
          <Animated.View style={[styles.ring, { width: size, height: size }, spinStyle]}>
            <SeekArc size={size} weight={weight} />
          </Animated.View>
          {showHalo && (
            <Animated.View style={[haloBox(size, 0.44), breatheStyle]} pointerEvents="none">
              <Halo size={size * 0.44} tint={color.light} peak={0.34} edge="0.68" />
            </Animated.View>
          )}
        </>
      ) : (
        <View
          style={[
            styles.ring,
            { width: size, height: size, borderRadius: size / 2, borderWidth: weight, borderColor: tint },
          ]}
        />
      )}

      {state === 'belagt' && (
        <>
          {/* The shock ring is the identity's hero-scale treatment — it rings
            * the big mark, not the inline chip, where at 2.1× it would sweep
            * straight across the word beside it. Same threshold as the halo. */}
          {showHalo && (
            <Animated.View
              style={[
                styles.centered,
                { width: size, height: size, borderRadius: size / 2, borderWidth: 1, borderColor: 'rgba(79,199,156,0.6)' },
                shockStyle,
              ]}
              pointerEvents="none"
            />
          )}
          <View style={[styles.centered, { width: size, height: size, alignItems: 'center', justifyContent: 'center' }]}>
            <Animated.View
              style={[{ width: core, height: core, borderRadius: core / 2, backgroundColor: tint }, coreStyle]}
            />
          </View>
        </>
      )}
    </View>
  )
}

/** The broken ring: a solid quarter at twelve o'clock and a faint quarter at
 *  three, exactly the identity's `border-top-color` + `border-right-color`
 *  construction expressed as stroke dashes. */
function SeekArc({ size, weight }: { size: number; weight: number }) {
  const r = (size - weight) / 2
  const c = size / 2
  const quarter = 2 * Math.PI * r * 0.25

  return (
    <Svg width={size} height={size}>
      <Circle
        cx={c}
        cy={c}
        r={r}
        stroke={color.light}
        strokeWidth={weight}
        fill="none"
        strokeDasharray={`${quarter},${quarter * 3}`}
        origin={`${c},${c}`}
        rotation={-135}
      />
      <Circle
        cx={c}
        cy={c}
        r={r}
        stroke="rgba(207,224,255,0.4)"
        strokeWidth={weight}
        fill="none"
        strokeDasharray={`${quarter},${quarter * 3}`}
        origin={`${c},${c}`}
        rotation={-45}
      />
    </Svg>
  )
}

function Halo({ size, tint, peak, edge }: { size: number; tint: string; peak: number; edge: string }) {
  // Unique per instance: several marks can be on screen at once and a shared
  // gradient id makes them fight over one definition.
  const id = useId()
  return (
    <Svg width={size} height={size}>
      <Defs>
        <RadialGradient id={id} cx="50%" cy="50%" r="50%">
          <Stop offset="0" stopColor={tint} stopOpacity={peak} />
          <Stop offset={edge} stopColor={tint} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={`url(#${id})`} />
    </Svg>
  )
}

function haloBox(size: number, factor: number) {
  const h = size * factor
  return {
    position: 'absolute' as const,
    width: h,
    height: h,
    left: (size - h) / 2,
    top: (size - h) / 2,
  }
}

/**
 * The mark and its word, together. This is the shape the identity's own
 * product mockup uses for a grounded answer (◉ BELAGT) and the only form in
 * which a status may be shown, since the label is what carries the meaning
 * when colour cannot.
 */
export function StatusChip({
  state,
  label,
  size = mark.minRingSize,
}: {
  state: MarkState
  label?: string
  size?: number
}) {
  const text = label ?? STATUS_LABEL[state]
  const tint = TINT[state]
  const skin = CHIP[state]

  return (
    <View
      style={[styles.chip, { backgroundColor: skin.fill, borderColor: skin.edge }]}
      accessible
      accessibilityRole="text"
      accessibilityLabel={text ? `${STATUS_SPOKEN[state]}: ${text}` : STATUS_SPOKEN[state]}
    >
      <StatusMark state={state} size={size} />
      {text && <Text style={[styles.chipLabel, { color: tint }]}>{text}</Text>}
    </View>
  )
}

const CHIP: Record<MarkState, { fill: string; edge: string }> = {
  vila: { fill: color.surface, edge: color.hairline },
  soker: { fill: color.lightGlow, edge: 'rgba(207,224,255,0.3)' },
  belagt: { fill: color.groundedTint, edge: color.groundedBorder },
  ejbelagt: { fill: color.refusalTint, edge: color.refusalBorder },
}

const styles = StyleSheet.create({
  ring: { position: 'absolute', left: 0, top: 0 },
  centered: { position: 'absolute', left: 0, top: 0 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    alignSelf: 'flex-start',
    paddingLeft: space.sm,
    paddingRight: space.md,
    paddingVertical: 5,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  /* §07 MÄTNINGEN: state is a measurement, so it is set in mono, uppercase,
   * with the identity's +0.10–0.20 em tracking. */
  chipLabel: { fontFamily: font.monoBold, fontSize: 10, letterSpacing: 1.3 },
})
