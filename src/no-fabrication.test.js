import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Tripwire: fails if any of the three external-agent fabrication incidents
// documented in .superpowers/quarantine/INVENTORY.md reappear in committed
// product source. The committed tree at 55c8aaa was manually verified
// intrusion-free (INVENTORY.md §4); this test turns that one-time grep into
// a permanent, guarded property (mirrors the repo's "prove the negative
// with a tripwire" lesson — NOTES.md egress audit).
//
// Scans src/ product files only; *.test.js(x) and test-setup.js are
// excluded because test fixtures legitimately construct citation-shaped
// objects to exercise the render path (see ChatMessageList.test.jsx).

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));
const SELF_BASENAME = path.basename(fileURLToPath(import.meta.url));

const TEST_FILE_RE = /\.test\.jsx?$/;
const SOURCE_EXT_RE = /\.jsx?$/;

function walkSourceFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walkSourceFiles(full));
    } else if (
      entry.isFile() &&
      SOURCE_EXT_RE.test(entry.name) &&
      !TEST_FILE_RE.test(entry.name) &&
      entry.name !== 'test-setup.js' &&
      entry.name !== SELF_BASENAME
    ) {
      out.push(full);
    }
  }
  return out;
}

// Finds the smallest brace-balanced `{...}` region enclosing index `idx` in
// `content` — i.e. the innermost object-literal-or-block containing the
// match. Used to check whether two keys co-occur in the *same* literal
// rather than merely somewhere in the same file.
function enclosingBraces(content, idx) {
  let depth = 0;
  let start = -1;
  for (let i = idx; i >= 0; i--) {
    if (content[i] === '}') depth++;
    else if (content[i] === '{') {
      if (depth === 0) { start = i; break; }
      depth--;
    }
  }
  if (start === -1) return null;
  depth = 0;
  for (let i = start; i < content.length; i++) {
    if (content[i] === '{') depth++;
    else if (content[i] === '}') {
      depth--;
      if (depth === 0) return content.slice(start, i + 1);
    }
  }
  return null;
}

// Each signature documents the specific quarantined incident it guards
// against (.superpowers/quarantine/INVENTORY.md fabrication catalog, §2).
const SIGNATURES = [
  {
    name: 'searchAdapter module',
    guards:
      'stash@{0}: entirely-fabricated search results (invented pages/dates/quotes/scores) wired through a searchAdapter with no backing backend endpoint (catalog #1-4)',
    test: (content) => /\bsearchAdapter\b/.test(content),
  },
  {
    name: 'chatAdapter module',
    guards:
      'stash@{1}/{2}: chatAdapter wrapping the real chat flow with fake pipeline-progress timing and (worst) silently overriding a correct refusal with a fabricated answer (catalog #5-7)',
    test: (content) => /\bchatAdapter\b/.test(content),
  },
  {
    name: 'getMockFollowUpResponse',
    guards:
      'stash@{2}: the mock-answer generator that replaced a real refusal/empty-citation response with a fabricated confident answer (catalog #7)',
    test: (content) => /_?getMockFollowUpResponse\b/.test(content),
  },
  {
    name: 'mock-chunk chunk id',
    guards:
      'stash@{2}: fake chunk_id values ("mock-chunk-1"/"mock-chunk-2") impersonating real content-hash chunk ids from the indexer (catalog #8)',
    test: (content) => content.includes('mock-chunk'),
  },
  {
    name: 'citation-shaped literal (quote + rects/page in one literal)',
    guards:
      'stash@{2}: hand-authored citation objects pairing a fake quote with fake rects/page/score, structurally indistinguishable from a verified CitationOut (catalog #9-10)',
    test: (content) => {
      const quoteKeyRe = /\bquote\s*:/g;
      let m;
      while ((m = quoteKeyRe.exec(content))) {
        const literal = enclosingBraces(content, m.index);
        if (literal && (/\brects\s*:/.test(literal) || /\bpage\s*:/.test(literal))) {
          return true;
        }
      }
      return false;
    },
  },
];

describe('no-fabrication tripwire', () => {
  const files = walkSourceFiles(SRC_DIR);

  it('scans a non-trivial set of product source files (sanity check: the walk is not vacuous)', () => {
    expect(files.length).toBeGreaterThan(5);
    expect(files.some((f) => f.endsWith('App.jsx'))).toBe(true);
  });

  for (const sig of SIGNATURES) {
    it(`no product source contains signature: ${sig.name}`, () => {
      const hits = files.filter((f) => sig.test(fs.readFileSync(f, 'utf8')));
      expect(hits, `Guards against: ${sig.guards}`).toEqual([]);
    });
  }
});
