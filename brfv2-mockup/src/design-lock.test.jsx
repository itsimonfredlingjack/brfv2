// Design lock (Beslut 1, docs/design/2026-08-08-unified-system/IMPLEMENTATION.md):
// .ui-btn is the only button primitive. The legacy classes were deleted in the
// consolidation commit — this test fails if the strings ever reappear under src/.
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
// Most locks here read the source; Beslut 11a has to render, because the rule
// it holds is about what reaches the screen rather than what is written down.
import React from 'react';
import { render } from '@testing-library/react';
import Instrument from './components/Instrument';

const SRC = dirname(fileURLToPath(import.meta.url));
const SELF = fileURLToPath(import.meta.url);

const FORBIDDEN = ['primary-action-btn', 'secondary-action-btn'];

// Beslut 2: four breakpoints, locked. A new exception requires a deliberate
// edit of this set — that is the price of adding a breakpoint.
const CANONICAL_BP = new Set(['1200', '1024', '768', '560']);
const MEDIA_WIDTH = /@media[^{]*\((?:max|min)-width:\s*(\d+)px\)/g;

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (/\.(jsx?|css)$/.test(entry.name)) yield path;
  }
}

describe('design lock: one button primitive', () => {
  it('no legacy button classes under src/', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (file === SELF) continue;
      const text = readFileSync(file, 'utf8');
      for (const needle of FORBIDDEN) {
        if (text.includes(needle)) offenders.push(`${relative(SRC, file)} contains "${needle}"`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe('design lock: four breakpoints', () => {
  it('every @media width is one of 1200/1024/768/560', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css')) continue;
      const text = readFileSync(file, 'utf8');
      for (const m of text.matchAll(MEDIA_WIDTH)) {
        if (!CANONICAL_BP.has(m[1])) offenders.push(`${relative(SRC, file)} uses @media width ${m[1]}px`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

// Beslut 3 (tangentbordsflödet): one focus ring — 2px solid var(--ring), 2px
// offset. The 3px glow was swept away in the keyboard-flow commit; the token
// is deleted, so the string itself failing to appear is the lock.
// Beslut 4 (avståndsskalan): spacing that lands on the scale must go through
// the scale. Before this lock, 93% of all padding/margin/gap in the product was
// loose literals — the app's rhythm lived in ~1200 scattered numbers instead of
// nine tokens, which is the concrete reason its layout could not be redesigned.
// Values *off* the scale are deliberately still allowed: converting those moves
// pixels, so each one is a design decision rather than a mechanical rewrite.
// This lock only stops the mechanical case from coming back.
const SPACING_PROP = String.raw`(?:padding|margin)(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?|gap|row-gap|column-gap`;
const SPACING_DECL = new RegExp(String.raw`(?:^|[;{\s])(${SPACING_PROP})\s*:\s*([^;}]+)`, 'gim');
const LENGTH = /(?<![\w.-])(\d*\.?\d+)(rem|px)(?![\w-])/g;
// The spacing ramp, in rem — including the half-steps added 2026-08-10.
const ON_SCALE = new Map([
  [0.125, '--s0h'], [0.25, '--s1'], [0.375, '--s1h'], [0.5, '--s2'],
  [0.625, '--s2h'], [0.75, '--s3'], [0.875, '--s3h'], [1, '--s4'],
  [1.25, '--s5'], [1.5, '--s6'], [2, '--s8'], [2.5, '--s10'], [3.5, '--s14'],
]);

// The type ramp, in rem.
const TYPE_SCALE = new Map([
  [0.6875, '--text-2xs'], [0.75, '--text-xs'], [0.8125, '--text-dense'],
  [0.875, '--text-sm'], [0.9375, '--text-base'], [1.0625, '--text-lg'],
  [1.5, '--text-xl'], [1.875, '--text-2xl'],
]);

function literalsOnScale(declRe, scale, label) {
  const offenders = [];
  for (const file of walk(SRC)) {
    if (!file.endsWith('.css')) continue;
    const text = readFileSync(file, 'utf8');
    for (const decl of text.matchAll(declRe)) {
      const prop = decl[1] ?? label;
      const value = decl[decl.length - 1];
      if (value.toLowerCase().includes('calc(')) continue;
      for (const len of value.matchAll(LENGTH)) {
        const rem = len[2].toLowerCase() === 'px' ? Number(len[1]) / 16 : Number(len[1]);
        const token = scale.get(Number(rem.toFixed(6)));
        if (token) {
          offenders.push(`${relative(SRC, file)}: ${prop}: …${len[0]}… — use var(${token})`);
        }
      }
    }
  }
  return offenders;
}

describe('design lock: spacing goes through the scale', () => {
  it('no literal on-scale padding/margin/gap under src/', () => {
    expect(literalsOnScale(SPACING_DECL, ON_SCALE, 'spacing')).toEqual([]);
  });
});

describe('design lock: type goes through the scale', () => {
  it('no literal on-scale font-size under src/', () => {
    const FONT_DECL = /(?:^|[;{\s])(font-size)\s*:\s*([^;}]+)/gim;
    expect(literalsOnScale(FONT_DECL, TYPE_SCALE, 'font-size')).toEqual([]);
  });
});

describe('design lock: one focus ring', () => {
  it('no 3px glow ring or ring-glow token under src/', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (file === SELF || !file.endsWith('.css')) continue;
      const text = readFileSync(file, 'utf8');
      if (text.includes('ring-glow')) offenders.push(`${relative(SRC, file)} mentions ring-glow`);
    }
    expect(offenders).toEqual([]);
  });
});

// Beslut 5 (instrumentet): the band's instrument is one component with one
// name. It used to be hand-copied across eight screens under two *borrowed*
// class names — `invoices-ledger` and `watches-standing` — so Dokument was
// literally built out of Fakturor's and Bevakningar's parts. The cost was that
// there was no instrument to change: editing `.ledger-amount` moved Dokument,
// Fakturor and Anslutningar at once, so touching one screen meant a scoped
// override, and each override made the next change harder. Two locks keep that
// from growing back.
const RETIRED_INSTRUMENT_CLASSES = [
  'page-header-instrument', 'invoices-ledger', 'invoices-ledger-figure',
  'invoices-ledger-counts', 'ledger-amount', 'ledger-label',
  'watches-standing', 'watches-instrument', 'tasks-standing',
];

describe('design lock: the instrument is one component', () => {
  // Quoted, because that is how a class is *used* — in a className or a
  // selector. Instrument.jsx names its predecessors in backticks to explain
  // what it replaced, which is documentation, not a second implementation.
  it('no retired instrument class is used under src/', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (file === SELF) continue;
      const text = readFileSync(file, 'utf8');
      for (const name of RETIRED_INSTRUMENT_CLASSES) {
        const used = new RegExp(String.raw`["'.]${name}(?![\w-])`);
        if (used.test(text)) offenders.push(`${relative(SRC, file)} uses "${name}"`);
      }
    }
    expect(offenders).toEqual([]);
  });

  // The lock that actually prevents the failure mode. A screen that wants a
  // different instrument has to change the instrument — it cannot bolt a
  // scoped override onto someone else's, which is how eight copies happened.
  //
  // Asking whether an instrument is there is not styling one. The band's
  // height depends on that answer — an instrument that measures nothing does
  // not draw, and the band must not go on reserving 268px for it — so App.css
  // writes `.page-header:not(:has(.instrument))`. That declares nothing about
  // the instrument and cannot drift from it; what this lock is for is
  // `.docs-overview .instrument-amount { … }`, which still trips it, including
  // when it is written as `.instrument:has(.x) { … }`.
  it('every .instrument rule lives in Instrument.css', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css') || file.endsWith('Instrument.css')) continue;
      const text = readFileSync(file, 'utf8').replace(/:has\([^)]*\)/g, ':has()');
      for (const m of text.matchAll(/\.instrument[\w-]*/g)) {
        offenders.push(`${relative(SRC, file)} styles ${m[0]} — put it in Instrument.css`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

// Beslut 8 (variablerna): a var() that names nothing renders its fallback in
// silence, and a fallback is a literal — the exact thing this codebase keeps
// getting undesignable from. Three call sites carried `var(--accent, #6384ff)`
// for long enough to be written down in CLAUDE.md as a known bug; the token was
// defined again at some point and nobody noticed, so the note stayed wrong and
// the literal stayed dead. Neither can happen quietly now.
//
// The allowlist is variables a component sets inline on the element — they are
// genuinely absent from the stylesheets and genuinely defined at runtime.
const INLINE_SET_VARS = new Set(['--mark-ring', '--leaves', '--i', '--skew', '--pitch']);

describe('design lock: every variable names something', () => {
  it('no var() refers to a custom property that is never defined', () => {
    const defined = new Set();
    const used = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css')) continue;
      const text = readFileSync(file, 'utf8');
      for (const m of text.matchAll(/(--[\w-]+)\s*:/g)) defined.add(m[1]);
      for (const m of text.matchAll(/var\(\s*(--[\w-]+)\s*(,)?/g)) {
        used.push({ name: m[1], fallback: Boolean(m[2]), file });
      }
    }
    const offenders = used
      .filter((u) => !defined.has(u.name) && !INLINE_SET_VARS.has(u.name))
      .map((u) => `${relative(SRC, u.file)}: var(${u.name}) is never defined`
        + (u.fallback ? ' — and its fallback is a literal that renders instead' : ''));
    expect([...new Set(offenders)]).toEqual([]);
  });
});

// Beslut 7 (etiketten): §07 gives the mono a closed list — "sidnummer,
// paragrafer, poäng, tillstånd" — and everything else that explains belongs to
// the sans. Uppercase mono had spread to seventeen captions, table heads and
// section labels that are on none of that list, which is what made the product
// read as instrumentation. They now go through --etikett-*; this lock keeps the
// list closed, so a new caption cannot quietly join them.
// 'overdue-flag' and 'signal-chip' left this list when the queue table they
// dressed was deleted from Invoices.css — the allowance shrinks with the code.
const MONO_CAPS_ALLOWED = [
  'matt', 'answer-state', 'verdict',
  'task-badge', 'logo-qualifier', 'login-brand-qualifier', 'docs-register-count',
];

describe('design lock: the measuring cut keeps its closed list', () => {
  it('no uppercase mono outside the states, scores and qualifiers', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css')) continue;
      const text = readFileSync(file, 'utf8');
      for (const rule of text.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
        const body = rule[2];
        if (!body.includes('var(--font-mono)')) continue;
        if (!/text-transform:\s*uppercase/.test(body)) continue;
        const selector = rule[1].replace(/\/\*[\s\S]*?\*\//g, '').trim();
        if (MONO_CAPS_ALLOWED.some((name) => selector.includes(name))) continue;
        offenders.push(`${relative(SRC, file)}: ${selector} sets uppercase mono — use var(--etikett-*)`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

// Beslut 6 (typrollerna): the identity (docs/design/2026-08-10-identitet) gives
// the three faces three jobs — serif asserts, sans explains, mono measures — and
// says the roles are never mixed, because that is how a reader tells the
// product's words from the document's. Instrument Serif ships exactly one
// weight. Asking it for 600 makes the browser smear a synthetic bold across a
// high-contrast face, which is how the serif quietly stops looking like itself.
// The rule is not "one weight" any more — Nunito ships three and all three are
// vendored. What it still stops is the thing it was written for: asking for a
// weight that was never shipped, so the browser smears a synthetic bold across
// the face. Add a weight here only after adding the woff2 beside theme.css.
const VENDORED_DISPLAY_WEIGHTS = new Set(['400', '600', '700']);

describe('design lock: the assertion face is only asked for weights it ships', () => {
  it('no unvendored font-weight in a rule that sets --font-display', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css')) continue;
      const text = readFileSync(file, 'utf8');
      // Each rule body, so a weight is only judged against its own selector.
      for (const rule of text.matchAll(/\{([^{}]*)\}/g)) {
        const body = rule[1];
        if (!body.includes('var(--font-display)')) continue;
        const weight = body.match(/font-weight:\s*(\d+)/);
        if (weight && !VENDORED_DISPLAY_WEIGHTS.has(weight[1])) {
          offenders.push(`${relative(SRC, file)}: --font-display with font-weight ${weight[1]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Beslut 9: the shell's contrast is computed, not judged by eye.
//
// A reviewer told us the dark mode "violates basic WCAG 2.1 AA" and named the
// subtext as the offender. The subtext measured 8.81:1. What actually failed
// was the thing nobody mentioned: the boundary of every input and select, at
// 1.75:1 against a 3:1 requirement — Fakturor's four filters and its search
// field were, accessibly speaking, not drawn at all.
//
// Eyes are bad at this in both directions, and screenshots are worse: they are
// re-encoded, and they are looked at on someone else's display at someone
// else's brightness. So the ratios are arithmetic now. If a token is re-mixed
// and drops below its floor, this fails before anyone has to notice.
const THEME = readFileSync(join(SRC, 'theme.css'), 'utf8');

function tokenHex(name) {
  const m = THEME.match(new RegExp(`^\\s*${name}:\\s*(#[0-9A-Fa-f]{6})\\s*;`, 'm'));
  if (!m) throw new Error(`design lock: token ${name} is not defined as a hex in theme.css`);
  return m[1];
}
const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toLinear = (c) => (c / 255 <= 0.03928 ? c / 255 / 12.92 : (((c / 255) + 0.055) / 1.055) ** 2.4);
const luminance = (hex) => {
  const [r, g, b] = channels(hex).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

// The grounds a shell colour can land on. Not --matta: nothing interactive and
// no interface text lies on the reading mat, only a document does.
const GROUNDS = ['--skal', '--skal-sunken', '--skal-pressed', '--matta'];

// floor, and why it is that number
const FLOORS = [
  ['--black-900', 4.5],      // headings, primary text, the filled state
  ['--black-700', 4.5],      // secondary prose, fact values
  ['--black-500', 4.5],      // body prose, fact labels, the mono eyebrows
  ['--kant-kontroll', 3.0],  // the boundary of a control (1.4.11)
  ['--horisont-fylld', 3.0], // a data mark you must see to read the chart
  ['--belagt', 4.5],         // the six meanings, as text
  ['--vagran', 4.5],
  ['--avbrott', 4.5],
  ['--handling', 4.5],
  ['--sokljus-text', 4.5],
];

describe('design lock: the shell meets AA by arithmetic', () => {
  it.each(FLOORS)('%s clears %f:1 on every ground it can sit on', (token, floor) => {
    const hex = tokenHex(token);
    const failures = GROUNDS
      .map((ground) => [ground, contrast(hex, tokenHex(ground))])
      .filter(([, ratio]) => ratio < floor)
      .map(([ground, ratio]) => `${token} (${hex}) on ${ground}: ${ratio.toFixed(2)}:1 < ${floor}`);
    expect(failures).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Beslut 9b: the one inverted surface is measured too.
//
// Every ground above is paper. The product has exactly one that is not: login's
// brand panel, the single "look here" surface the system allows per view. When
// §06 turned over from a dark shell to a paper-white one, that panel kept its
// ink ground while its type was re-pointed at the new ink scale — so the mark,
// the name and the tagline were all drawn in --black-900 on --black-900, and
// the column rendered as an empty black rectangle. Nothing failed, because
// nothing was measuring it: GROUNDS is a list of white surfaces, and a colour
// that never lands on white is invisible to that list in both senses.
//
// The paper scale genuinely cannot be reused here — --black-500 is 5.10:1 on
// white and 3.88:1 on ink — which is why the panel's quiet text is an alpha of
// --papper. So the floors are stated for what is actually allowed on ink.
const INK_FLOORS = [
  ['--papper', 4.5],      // the mark, the name, the tagline
  ['--skal', 4.5],        // the same white under its shell name
];

describe('design lock: the inverted surface meets AA too', () => {
  it.each(INK_FLOORS)('%s clears %f:1 on --ink', (token, floor) => {
    const ratio = contrast(tokenHex(token), tokenHex('--ink'));
    expect(
      ratio,
      `${token} (${tokenHex(token)}) on --ink: ${ratio.toFixed(2)}:1 < ${floor}`,
    ).toBeGreaterThanOrEqual(floor);
  });

  // And no rule that paints on the ink panel may reach for the paper scale.
  // That substitution is the exact mistake above, and it reads as deliberate
  // every time: --black-500 is the product's quiet grey everywhere else.
  it('the ink panel never takes a colour from the paper scale', () => {
    const css = readFileSync(join(SRC, 'components', 'Login.css'), 'utf8');
    const panel = css.slice(css.indexOf('.login-brand'), css.indexOf('.login-form-col'));
    const offenders = [...panel.matchAll(/color:\s*var\((--black-\d00)\)/g)]
      .map((m) => `Login.css .login-brand…: color: var(${m[1]}) — paper scale on the ink panel`);
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Beslut 10: a colour literal may not spell out a token's value.
//
// CSS cannot take an alpha of a hex token, so "paper at 15%" got written as
// rgb(232 229 222 / 0.15) — a copy of --papper that does not follow it. Högen's
// beam was four such copies of --ljus; --ljus was re-mixed from cold to warm
// and the beam silently stayed cold, and nothing failed, because a literal
// renders perfectly while meaning nothing. Same disease as the ~1000 spacing
// literals, in the colour column.
//
// The cure is --ljus-rgb / --papper-rgb / --ink-rgb, used as
// rgb(var(--papper-rgb) / 0.15). This test fails if a value comes back inline.
//
// White and black are exempt: rgb(255 255 255 / 0.045) in --lyft is not a copy
// of --dokument, it is the light every screen is lit from above by.
const NEUTRAL = new Set(['255 255 255', '0 0 0']);

describe('design lock: no literal spells out a token', () => {
  it('every inline rgb() is a neutral or a channel token', () => {
    const named = new Map();
    for (const [, name, hex] of THEME.matchAll(/^\s*(--[\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;/gm)) {
      named.set(channels(hex).join(' '), name);
    }
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css')) continue;
      for (const [, triple] of readFileSync(file, 'utf8')
        .matchAll(/rgba?\(\s*(\d{1,3}[\s,]+\d{1,3}[\s,]+\d{1,3})\s*[/,)]/g)) {
        const key = triple.replace(/[\s,]+/g, ' ');
        if (NEUTRAL.has(key)) continue;
        if (named.has(key)) {
          offenders.push(
            `${relative(SRC, file)}: rgb(${key}) is ${named.get(key)} — use rgb(var(${named.get(key)}-rgb) / …)`,
          );
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

// Beslut 10b: and the channel tokens must agree with their hex.
describe('design lock: channels agree with their colour', () => {
  it.each(['--black-900', '--papper', '--ink', '--remsgul', '--sokljus', '--avbrott', '--handling'])('%s-rgb equals its hex', (token) => {
    const triple = THEME.match(new RegExp(`^\\s*${token}-rgb:\\s*([\\d\\s]+);`, 'm'));
    expect(triple, `${token}-rgb is not defined`).toBeTruthy();
    expect(triple[1].trim().split(/\s+/).map(Number)).toEqual(channels(tokenHex(token)));
  });
});

// ── Beslut 11 (sidgrammatiken): the two rules a page follows before it has
// anything to say. Both were written for the pilot, where four of seven
// workspaces are empty and empty is the first thing a board ever sees.

// Beslut 11a: zero is not a measurement — for the whole instrument.
//
// The figure already knew this: Fakturor at rest says "Inget öppet att
// granska" instead of setting a 52px mono zero. The readings did not, so
// Uppgifter opened on 0 / 0 / 0, Hemsidan on 0 / 0 and Inkommande on 0 / 0 / 0
// — the least informative row on the page, in the largest numerals on the
// page, above the one sentence that said something. Seven screens pass an
// instrument and none of them should have to decide this.
//
// A rendered lock rather than a read one: the rule is about what reaches the
// screen, and grepping the seven call sites would only prove they still call
// it. See Instrument.jsx for why a single "1" among zeros keeps its siblings.
describe('design lock: an instrument with nothing to measure does not draw', () => {
  const readings = (...values) => values.map((v, i) => ({ label: `r${i}`, value: v }));

  it('renders nothing when every number it holds is zero', () => {
    const { container } = render(<Instrument readings={readings(0, 0, 0)} />);
    expect(container.querySelector('.instrument')).toBeNull();
  });

  it('renders nothing when a zero figure heads zero readings', () => {
    const { container } = render(
      <Instrument label="Sidor" value={0} readings={readings(0, 0)} />,
    );
    expect(container.querySelector('.instrument')).toBeNull();
  });

  // A formatted figure is not its own number, which is what `raw` is for.
  it('reads a formatted zero through raw', () => {
    const { container } = render(
      <Instrument label="Öppet belopp" value="0,00 SEK" raw="0.00" readings={readings(0)} />,
    );
    expect(container.querySelector('.instrument')).toBeNull();
  });

  it('draws for one number among zeros — that is a distribution', () => {
    const { container } = render(<Instrument readings={readings(1, 0, 0)} />);
    expect(container.querySelector('.instrument')).not.toBeNull();
    expect(container.textContent).toContain('1');
  });

  // A reading is not always a count. "Aldrig hämtat" is a state, and a state
  // is never zero — the rule is about numbers, and this is not one.
  it('draws for a reading that is not a number at all', () => {
    const { container } = render(<Instrument readings={readings('Aldrig hämtat', 0)} />);
    expect(container.querySelector('.instrument')).not.toBeNull();
    expect(container.textContent).toContain('Aldrig hämtat');
  });
});

// Beslut 11b: one measure per page, and the band is on the page.
//
// The band ran to the window's edge while the register under it stopped at
// --measure: the widest rule on the page ruling the narrowest content on the
// page, with the band's own controls out at an edge no row ever reached. Since
// --skal-raised and the page ground are the same white, that hairline is the
// only thing a reader ever sees of the band, and a rule belongs to the text it
// rules. Pages whose measure is not the default scope --measure to their own
// (.chat-workspace narrows it, .integrations and .invoices widen it) and the
// band follows, which is the whole point: the measure is the page's.
describe('design lock: the band takes the page measure', () => {
  it('.page-header caps its width through var(--measure)', () => {
    const css = readFileSync(join(SRC, 'App.css'), 'utf8');
    const start = css.indexOf('\n.page-header {');
    expect(start, '.page-header rule not found in App.css').toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf('}', start));
    const cap = block.match(/max-width:\s*([^;]+);/);
    expect(cap, '.page-header sets no max-width — the band is back on the window').toBeTruthy();
    expect(cap[1]).toContain('var(--measure)');
  });
});

// Beslut 11c: not measured yet is not zero either.
//
// The half of Beslut 11a the callers threw away. Seven screens computed their
// readings out of an object the fetch had not filled — `counts.open ?? 0`,
// `board?.counts || { active: 0 }`, `documents.length` on an empty array — so
// an unloaded screen reported zeros it had no basis for, 11a believed them,
// and the band opened short and grew when the data landed. Measured on
// Fakturor before the fix: 138px at first paint, 268px 38ms later.
//
// So the third state is real and has to stay distinguishable from the other
// two: nothing stated holds the instrument's row and draws nothing in it.
describe('design lock: an instrument that has not been told anything holds its row', () => {
  it('draws the row, empty, when nothing is stated', () => {
    const { container } = render(
      <Instrument readings={[{ label: 'Pågående', value: undefined }]} />,
    );
    const row = container.querySelector('.instrument');
    expect(row, 'nothing stated collapsed the band instead of holding it').not.toBeNull();
    expect(row.children.length, 'the held row drew something in itself').toBe(0);
    expect(row.textContent).toBe('');
  });

  it('holds the row for a figure whose number has not arrived', () => {
    const { container } = render(
      <Instrument label="Öppet belopp" value={undefined} raw={undefined} />,
    );
    expect(container.querySelector('.instrument')).not.toBeNull();
    expect(container.textContent).toBe('');
  });

  // The distinction is the whole point: a stated zero still means "measured,
  // and there is nothing", and that still removes the instrument.
  it('still removes the instrument once the zeros are actually stated', () => {
    const { container } = render(
      <Instrument readings={[{ label: 'Pågående', value: 0 }]} />,
    );
    expect(container.querySelector('.instrument')).toBeNull();
  });
});

// Beslut 12: the case is one plane.
//
// theme.css states the white language in one sentence — a hairline and an
// inverted surface are the whole elevation system, nothing lifts, nothing
// layers — and Fakturor's case view was the one screen that did not obey it.
// `.case-columns` was a lifted sheet (the only --shadow-sheet in src/) and
// inside it thirteen blocks each drew their own hairline, radius and card
// background: the sheet's edge and the panel's edge saying "a block ends here"
// a pixel apart, on a screen whose --lyft-1 is `none`, so none of it lifted.
// The split that carries the argument is carried by the columns; the air
// between them is the structure.
describe('design lock: the case view draws no box around its own structure', () => {
  const CASE_CONTAINERS = ['.case-columns', '.case-panel', '.case-original'];
  const BOXES = /(?:^|[;{\s])(border(?!-collapse)[a-z-]*|box-shadow|background[a-z-]*)\s*:/i;

  it.each(CASE_CONTAINERS)('%s states nothing but layout', (selector) => {
    const css = readFileSync(join(SRC, 'components/Invoices.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '');
    const start = css.indexOf(`\n${selector} {`);
    expect(start, `${selector} not found in Invoices.css`).toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf('}', start));
    const drawn = block.match(BOXES);
    expect(drawn, `${selector} draws ${drawn && drawn[1]} — the case is back to cards in cards`)
      .toBeNull();
  });
});

// Beslut 12b: a disabled primary gives up its ink.
//
// The primitive's generic disabled state is opacity 0.5, which on a filled ink
// pill renders a solid grey slab — three of them met the reader on the invoice
// case before anything had been touched, reading as broken rather than as
// waiting. theme.css therefore states a quiet disabled primary: the inert
// surface, full opacity, defined after the generic rule so the cascade keeps
// it. This lock holds all three parts, because losing any one of them brings
// the slab back without a test going red.
describe('design lock: a disabled primary gives up its ink', () => {
  it('theme.css quiets .ui-btn--primary:disabled after the generic dimming', () => {
    const generic = THEME.indexOf('.ui-btn:disabled');
    const quiet = THEME.indexOf('.ui-btn--primary:disabled');
    expect(generic, '.ui-btn:disabled not found in theme.css').toBeGreaterThan(-1);
    expect(quiet, '.ui-btn--primary:disabled not found in theme.css — the grey slab is back').toBeGreaterThan(-1);
    expect(quiet, 'the quiet rule must come after the generic one or it loses the cascade').toBeGreaterThan(generic);
    const block = THEME.slice(quiet, THEME.indexOf('}', quiet));
    expect(block, 'the disabled primary must take the inert surface').toContain('background: var(--skal-pressed)');
    expect(block, 'the disabled primary must undo the generic opacity dimming').toContain('opacity: 1');
  });
});

// Beslut 13: no second button vocabulary.
//
// The lock above this file's first describe names the two classes the
// consolidation deleted, which is a lock against a *return*. It said nothing
// about a new set growing quietly beside the primitive, and one had: 1261
// lines of case view with no .ui-btn in them at all — `.case-primary` at 32px
// where the primitive is 36, a 28px picker pill, a 26px ghost in the alias
// list, `.invoices button.link` copied from `.ui-link` with one digit changed.
//
// A private vocabulary grows fastest through the bare `button` tag selector,
// because nothing in the markup names it: the JSX looks like plain HTML and
// the geometry arrives from a stylesheet nobody is reading. So this is a
// census. Every one that exists is listed; a new one fails. The list may only
// shrink, and the case view is why it just did.
const BARE_BUTTON_RULES = new Set([
  // The band states its control once, on purpose — that is what stopped
  // .watches-scan, .tasks-refresh and .invoices-read-in-btn drifting to three
  // different heights. See App.css.
  'App.css :: .page-header button',
  'App.css :: .page-header-actions button',
  'App.css :: .extraction-actions button',
  'App.css :: .mobile-qa-segmented-control button',
  'App.css :: .report-menu button',
  'components/DesktopSettings.css :: .ds-backup-actions button',
  'components/IntegrationConnections.css :: .ic-usercode button',
  'components/Invoices.css :: .composition-legend button',
  'components/Invoices.css :: .composition-segment button',
  'components/Invoices.css :: .invoices-available button',
  'components/MappingPreview.css :: .mp-lookup button',
  'components/website/Website.css :: .ai-input button',
  'components/website/Website.css :: .site-drawer__head button',
  'components/website/Website.css :: .site-error button',
  'components/website/Website.css :: .site-inspector__actions button',
  'components/website/Website.css :: .site-modal__card header button',
]);

describe('design lock: no new button vocabulary beside the primitive', () => {
  it('every bare `button` selector outside theme.css is one already counted', () => {
    const found = new Set();
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css') || file.endsWith('theme.css')) continue;
      const css = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
      for (const rule of css.matchAll(/([^{}();]+)\{/g)) {
        const selector = rule[1].trim();
        if (!selector || selector.startsWith('@')) continue;
        for (const part of selector.split(',')) {
          // Pseudo-classes do not change what element is being styled.
          const bare = part.trim().replace(/::?[a-z-]+(\([^)]*\))?/g, '').trim();
          if (/(^|[\s>+~])button$/.test(bare)) {
            found.add(`${relative(SRC, file).split(sep).join('/')} :: ${bare}`);
          }
        }
      }
    }
    const nya = [...found].filter((s) => !BARE_BUTTON_RULES.has(s)).sort();
    expect(nya, 'a button is being dressed by tag — give it .ui-btn instead').toEqual([]);
  });
});
