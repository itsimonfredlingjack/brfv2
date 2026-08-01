import { useCallback, useRef } from 'react'
import type { View } from 'react-native'
import { AccessibilityInfo } from 'react-native'
import {
  Easing,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withTiming,
} from 'react-native-reanimated'

import { motion } from '../theme/tokens'

interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/**
 * The hero interaction: a citation card visibly becomes the exact
 * highlighted passage on the source page. This is the FLIP technique
 * (First/Last/Invert/Play) transcribed from the 3a prototype's `flip()`
 * (support.js) into native measurement + Reanimated:
 *
 *  - `captureSource` measures the tapped citation card on the JS thread
 *    (`measureInWindow`) the instant it is pressed, before navigation.
 *  - `registerDestination` measures the real highlight once Källa has
 *    mounted and painted, computes the delta transform back to the source
 *    rect, and drives one Reanimated timeline: a box sized/positioned at
 *    the DESTINATION animates its transform from "looks like the source"
 *    to identity over 460ms — transform + opacity only, so it stays on the
 *    compositor even if the JS thread is busy — while a card-visual
 *    crossfades into a highlight-visual inside it. The real highlight stays
 *    hidden until the flight lands, then the flight fades out.
 *
 * Not a port of the prototype's DOM code: no CSS transitions, no
 * `getBoundingClientRect` polling — one native measurement per side, one
 * UI-thread timeline.
 */
export function useHeroFlight() {
  const sourceRect = useRef<Rect | null>(null)
  const pending = useRef(false)

  const overlayLeft = useSharedValue(0)
  const overlayTop = useSharedValue(0)
  const overlayWidth = useSharedValue(0)
  const overlayHeight = useSharedValue(0)
  const overlayOpacity = useSharedValue(0)
  const deltaX = useSharedValue(0)
  const deltaY = useSharedValue(0)
  const deltaScaleX = useSharedValue(1)
  const deltaScaleY = useSharedValue(1)
  const progress = useSharedValue(0)
  const cardOpacity = useSharedValue(1)
  const highlightOpacity = useSharedValue(0)
  /** The real highlight rendered on the page — hidden during flight so the
   * page doesn't show the destination before the card has visibly arrived. */
  const realHighlightOpacity = useSharedValue(1)

  /* eslint-disable react-hooks/immutability -- SharedValue.value; see below. */
  const captureSource = useCallback(
    (node: View | null) => {
      if (!node) return
      // Arm the destination's hidden state now, at tap time. The real
      // highlight mounts with the page image, which is one or more frames
      // before `registerDestination` can measure and start the flight —
      // hiding it only then let the finished highlight flash for a frame
      // before the card had flown to it. Every exit path below restores it,
      // as does `reset()`, so it can never stay hidden.
      realHighlightOpacity.value = 0
      node.measureInWindow((x, y, width, height) => {
        if (width > 0 && height > 0) sourceRect.current = { x, y, width, height }
        else realHighlightOpacity.value = 1
      })
    },
    [realHighlightOpacity],
  )
  /* eslint-enable react-hooks/immutability */

  // Reanimated's SharedValue is a deliberately mutable escape hatch — the
  // whole point of `.value =` is writing across the JS/UI-thread boundary
  // without going through React state. The react-hooks `immutability` rule
  // doesn't yet recognize that pattern and flags it the same as mutating a
  // plain hook return value.
  /* eslint-disable react-hooks/immutability */
  const reset = useCallback(() => {
    pending.current = false
    overlayOpacity.value = 0
    progress.value = 0
    cardOpacity.value = 1
    highlightOpacity.value = 0
    realHighlightOpacity.value = 1
    sourceRect.current = null
  }, [cardOpacity, highlightOpacity, overlayOpacity, progress, realHighlightOpacity])
  /* eslint-enable react-hooks/immutability */

  /* Same SharedValue caveat as `reset` above: `.value =` is Reanimated's
   * deliberate cross-thread write, not a mutation of a hook return value. */
  /* eslint-disable react-hooks/immutability */
  const registerDestination = useCallback(
    async (node: View | null) => {
      if (!node || !sourceRect.current) {
        // Nothing will fly — the passage must not stay hidden by the arming
        // done in `captureSource`.
        realHighlightOpacity.value = 1
        return
      }
      // A flight is already running; it owns the opacity from here.
      if (pending.current) return
      const reduceMotion = await AccessibilityInfo.isReduceMotionEnabled().catch(() => false)
      pending.current = true
      const src = sourceRect.current

      node.measureInWindow((x, y, width, height) => {
        if (width <= 0 || height <= 0) {
          realHighlightOpacity.value = 1
          pending.current = false
          return
        }

        if (reduceMotion) {
          realHighlightOpacity.value = 1
          pending.current = false
          return
        }

        overlayLeft.value = x
        overlayTop.value = y
        overlayWidth.value = width
        overlayHeight.value = height
        deltaX.value = src.x - x
        deltaY.value = src.y - y
        deltaScaleX.value = src.width / width
        deltaScaleY.value = src.height / height

        realHighlightOpacity.value = 0
        overlayOpacity.value = 1
        cardOpacity.value = 1
        highlightOpacity.value = 0
        progress.value = 0

        const easing = Easing.bezier(...motion.easing)
        progress.value = withTiming(1, { duration: motion.heroFlight, easing })
        cardOpacity.value = withTiming(0, { duration: motion.heroCardFade, easing: Easing.linear })
        highlightOpacity.value = withDelay(
          motion.heroHighlightDelay,
          withTiming(1, { duration: motion.heroHighlightFade, easing: Easing.linear }),
        )
        realHighlightOpacity.value = withDelay(motion.heroFlight, withTiming(1, { duration: 0 }))
        overlayOpacity.value = withDelay(
          motion.heroFlight,
          withTiming(0, { duration: motion.heroCardFade, easing: Easing.linear }),
        )

        // The animations own every value from here, so stop treating this as
        // "in flight". Leaving it set meant a later open found a stale guard,
        // returned early, and left the passage hidden — KallaSheet's own
        // `flownRef` is what keeps this to one flight per open.
        pending.current = false
      })
    },
    [cardOpacity, deltaScaleX, deltaScaleY, deltaX, deltaY, highlightOpacity, overlayHeight, overlayLeft, overlayOpacity, overlayTop, overlayWidth, progress, realHighlightOpacity],
  )
  /* eslint-enable react-hooks/immutability */

  const overlayStyle = useAnimatedStyle(() => ({
    position: 'absolute',
    left: overlayLeft.value,
    top: overlayTop.value,
    width: overlayWidth.value,
    height: overlayHeight.value,
    opacity: overlayOpacity.value,
    transform: [
      { translateX: interpolate(progress.value, [0, 1], [deltaX.value, 0]) },
      { translateY: interpolate(progress.value, [0, 1], [deltaY.value, 0]) },
      { scaleX: interpolate(progress.value, [0, 1], [deltaScaleX.value, 1]) },
      { scaleY: interpolate(progress.value, [0, 1], [deltaScaleY.value, 1]) },
    ],
  }))

  const cardStyle = useAnimatedStyle(() => ({ opacity: cardOpacity.value }))
  const highlightStyle = useAnimatedStyle(() => ({ opacity: highlightOpacity.value }))
  const realHighlightStyle = useAnimatedStyle(() => ({ opacity: realHighlightOpacity.value }))

  return {
    captureSource,
    registerDestination,
    reset,
    overlayStyle,
    cardStyle,
    highlightStyle,
    realHighlightStyle,
  }
}
