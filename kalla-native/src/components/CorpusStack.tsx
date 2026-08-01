import { useEffect } from 'react'
import { StyleSheet, View } from 'react-native'
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated'

import { color } from '../theme/tokens'

const LAYERS: { bg: string; y: number; scale: number; face?: boolean }[] = [
  { bg: '#8E949E', y: 16, scale: 0.9 },
  { bg: '#A7ADB6', y: 11, scale: 0.93 },
  { bg: '#C4C9D1', y: 7, scale: 0.96 },
  { bg: '#E2E5EA', y: 3, scale: 0.98 },
  { bg: color.paper, y: 0, scale: 1, face: true },
]

const PAGE_W = 256
const PAGE_H = 180
/** The page's margin. Everything on the sheet lives inside this column. */
const PAD = 26
const COL = PAGE_W - PAD * 2

/** One ink, several weights — the way real type sits on real paper. */
const ink = (a: number) => `rgba(20,22,26,${a})`

/**
 * The top sheet's content, as *signal* rather than text: a title, a couple of
 * paragraphs, one marked passage, a section further down. Widths are
 * fractions of the column so the lines rag like set type instead of ending
 * flush, which is most of what makes the eye say "paper" and not "shape".
 *
 * The rows are deliberately fatter than type would really be at this scale.
 * The stack is tilted 52°, so everything on it is foreshortened to about 62 %
 * of its height before it reaches the eye; drawn true-to-scale the body lines
 * arrive at well under a dp and the sheet goes blank again.
 */
const ROWS: { y: number; h: number; w: number; a: number }[] = [
  { y: 22, h: 8, w: 0.52, a: 0.82 }, // rubrik
  { y: 44, h: 4, w: 1.0, a: 0.2 },
  { y: 55, h: 4, w: 0.93, a: 0.2 },
  { y: 66, h: 4, w: 0.61, a: 0.2 }, // stycket tar slut
  // The marked row carries more ink than the rest. Partly because that is
  // what a highlighter does to the text under it, partly because at 0.2 it
  // simply disappears into the yellow and the mark stops reading as a mark.
  { y: 86, h: 4, w: 0.68, a: 0.48 },
  { y: 110, h: 5.5, w: 0.29, a: 0.5 }, // underrubrik
  { y: 128, h: 4, w: 0.97, a: 0.2 },
  { y: 139, h: 4, w: 0.79, a: 0.2 },
  { y: 150, h: 4, w: 0.46, a: 0.2 },
]

/**
 * The marked passage. Weaker than `color.hlFill`, and on purpose: this sheet
 * is an illustration of the corpus at rest, not a result. It should say "this
 * is what a marked passage looks like", not "something has already been
 * found" — the screen's own answer to that is ◉ vila, INGEN FRÅGA STÄLLD.
 *
 * It overshoots the line it marks at both ends, the way a marker does.
 */
const HL = { y: 83, h: 10, w: 0.74, x: -4 }

/**
 * The corpus at rest — "ett ljus, en hög": one physical pile of the
 * förening's documents, tilted back in perspective, breathing with a slow
 * light drift of its own rather than reacting to the device gyro (3a's
 * "ANDAS LIKADANT OM TELEFONEN LIGGER PÅ ETT BORD"). translateZ has no RN
 * equivalent, so depth here comes from perspective + rotateX on the shared
 * container plus per-layer translateY/scale staggering — a native
 * approximation of the prototype's DOM stack, not a port of it.
 */
export function CorpusStack({ height = 240 }: { height?: number }) {
  const drift = useSharedValue(0)

  useEffect(() => {
    drift.value = withRepeat(withTiming(1, { duration: 8000, easing: Easing.inOut(Easing.sin) }), -1, true)
  }, [drift])

  const sweepStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: -80 + drift.value * 160 }],
    opacity: 0.14 + drift.value * 0.1,
  }))

  return (
    <View style={[styles.scene, { height }]}>
      <View style={styles.tilt}>
        {LAYERS.map((layer, i) => (
          <View
            key={i}
            style={[
              styles.page,
              {
                backgroundColor: layer.bg,
                top: layer.y,
                transform: [{ scale: layer.scale }],
                zIndex: i,
              },
            ]}
          >
            {layer.face && <PageFace />}
          </View>
        ))}
        <Animated.View style={[styles.sweep, sweepStyle]} pointerEvents="none" />
      </View>
    </View>
  )
}

/**
 * Stylised, never legible. It reads as a document at a glance and stays
 * abstract at any distance — closer to a document mark than to a page of a
 * real stadga. Nothing here is content, so it is hidden from screen readers
 * along with the rest of the stack.
 */
function PageFace() {
  return (
    <View style={styles.face} pointerEvents="none" importantForAccessibility="no-hide-descendants">
      <View style={[styles.highlight, { top: HL.y, left: HL.x, height: HL.h, width: COL * HL.w }]} />
      {ROWS.map((row, i) => (
        <View
          key={i}
          style={{
            position: 'absolute',
            left: 0,
            top: row.y,
            height: row.h,
            width: COL * row.w,
            borderRadius: 1.5,
            backgroundColor: ink(row.a),
          }}
        />
      ))}
      {/* Faint page structure — a folio, so the sheet is one of many. */}
      <View style={styles.folio} />
    </View>
  )
}

const styles = StyleSheet.create({
  scene: {
    overflow: 'hidden',
    alignItems: 'center',
  },
  tilt: {
    // The pages span this box edge to edge, so this *is* the page width and
    // the column on the sheet is measured off it.
    width: PAGE_W,
    height: 200,
    marginTop: 30,
    transform: [{ perspective: 900 }, { rotateX: '52deg' }, { rotateZ: '-4deg' }],
  },
  page: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: PAGE_H,
    borderRadius: 4,
    shadowColor: '#000',
    shadowOpacity: 0.5,
    shadowRadius: 20,
  },
  face: { position: 'absolute', left: PAD, right: PAD, top: 0, bottom: 0 },
  highlight: { position: 'absolute', borderRadius: 2, backgroundColor: 'rgba(255,214,0,0.3)' },
  folio: {
    position: 'absolute',
    right: 0,
    top: 165,
    width: 14,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: ink(0.14),
  },
  sweep: {
    position: 'absolute',
    top: -20,
    bottom: -20,
    width: 90,
    backgroundColor: color.light,
    borderRadius: 40,
    // Above every sheet. Without this the sweep defaults to zIndex 0 and the
    // pages (0–4) paint over it, so the light fell *behind* the pile and only
    // the part overhanging the edges was visible — a grey blob beside the
    // stack instead of one light moving across the corpus.
    zIndex: LAYERS.length,
  },
})
