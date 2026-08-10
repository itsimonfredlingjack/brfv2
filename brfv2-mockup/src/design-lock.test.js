// Design lock (Beslut 1, docs/design/2026-08-08-unified-system/IMPLEMENTATION.md):
// .ui-btn is the only button primitive. The legacy classes were deleted in the
// consolidation commit — this test fails if the strings ever reappear under src/.
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

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
  it('every .instrument rule lives in Instrument.css', () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      if (!file.endsWith('.css') || file.endsWith('Instrument.css')) continue;
      const text = readFileSync(file, 'utf8');
      for (const m of text.matchAll(/\.instrument[\w-]*/g)) {
        offenders.push(`${relative(SRC, file)} styles ${m[0]} — put it in Instrument.css`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
