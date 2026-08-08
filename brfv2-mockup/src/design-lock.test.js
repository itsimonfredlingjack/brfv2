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
