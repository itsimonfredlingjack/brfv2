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
//
// cleanup/verified-ui Task 5: a fresh-context adversarial verifier found
// two evasions of the original signature set, both realized by the
// pre-existing (non-Gemini) Granskning/Bevakningar/Document-Canvas demo
// tabs once they were noticed as production-reachable: (a) a
// source-document-name-shaped key (sourceDoc/doc/document_name) holding a
// literal filename string, paired with a page-like key, but with NO `quote`
// key — invisible to the original "quote + rects/page" signature; (b) a
// literal multi-sentence body under an `extractedText`-like key,
// impersonating real OCR/parser output. Both are now covered below
// (signatures 6-7). That demo data has since been extracted to the single
// allowlisted module src/demoData.js and dev-gated (src/appModes.js,
// App.jsx) — see docs/evidence/verified-ui-restore.md.

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));

const TEST_FILE_RE = /\.test\.jsx?$/;
const SOURCE_EXT_RE = /\.jsx?$/;

// ALLOWLIST OF EXACTLY ONE FILE: src/demoData.js is the single product
// module permitted to contain pipeline-class data shapes (a literal
// source-document name + page, "extracted" body text, a quote+rects pair,
// etc.) — it is fabricated DEMO scaffolding for the dev-gated
// Granskning/Bevakningar/Document-Canvas tabs, never reachable in a
// production build (see its own header comment). Excluding it from the scan
// below is what lets that fabricated data exist at all without tripping the
// signatures that guard every OTHER product file; the "demoData allowlist"
// describe block at the bottom of this file is what keeps that exclusion
// honest — it fails if demoData.js is ever imported from anywhere other
// than the two dev-gated components, or if those components are ever
// statically (rather than dynamically, behind the import.meta.env.DEV gate)
// imported.
const DEMO_DATA_PATH = path.join(SRC_DIR, 'demoData.js');

// This file is itself named `no-fabrication.test.js`, so TEST_FILE_RE already
// excludes it from the walk below — no separate self-exclusion needed.
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
      full !== DEMO_DATA_PATH
    ) {
      out.push(full);
    }
  }
  return out;
}

// Same walk, but WITHOUT the demoData.js exclusion — used only by the
// "demoData allowlist" tests below, which need to see demoData.js itself
// (to resolve import specifiers against it) and every product file that
// might import it or the dev-gated components.
function walkAllProductFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walkAllProductFiles(full));
    } else if (
      entry.isFile() &&
      SOURCE_EXT_RE.test(entry.name) &&
      !TEST_FILE_RE.test(entry.name) &&
      entry.name !== 'test-setup.js'
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

// Finds the string literal (quote/double-quote/backtick) that starts at or
// immediately after `content[idx]`, handling backslash escapes. Returns
// { body, end } (body excludes the surrounding quote chars) or null if the
// literal never closes within the file.
function readStringLiteralAt(content, idx) {
  const quoteChar = content[idx];
  if (quoteChar !== '"' && quoteChar !== "'" && quoteChar !== '`') return null;
  for (let i = idx + 1; i < content.length; i++) {
    if (content[i] === '\\') { i++; continue; }
    if (content[i] === quoteChar) return { body: content.slice(idx + 1, i), end: i };
  }
  return null;
}

// Each signature documents the specific quarantined incident it guards
// against (.superpowers/quarantine/INVENTORY.md fabrication catalog, §2, or
// — for signatures 6-7 — the Task 5 adversarial verifier's evasion report).
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
    // Brief says "literal object/array" — scoped to object literals only,
    // since a bare array literal (`[...]`) has no `key: value` pairs of its
    // own to match `quote:`/`rects:`/`page:` against. Every catalogued
    // fabrication is an object literal (catalog #9-10), including when
    // nested inside an array (e.g. `citations: [{ quote: ..., rects: ... }]`)
    // — enclosingBraces() below finds the innermost `{...}` around the
    // `quote:` match regardless of any enclosing `[...]`, so array-nested
    // citation objects are already caught without special-casing arrays.
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
  {
    // Task 5 adversarial verifier's first evasion: the quarantined stashes'
    // citation objects always paired `quote:` with `rects:`/`page:`, so
    // signature 5 keys off `quote:`. The pre-existing demo tabs' `cardData`/
    // `timelineData` objects have NO `quote` key at all — they pair a
    // source-document-name-shaped key (sourceDoc/doc/document_name) holding
    // a LITERAL filename string with a `page:` key instead
    // (`{ sourceDoc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 }`) — structurally
    // a citation-lookalike (names a source + a page) without ever writing
    // the word "quote". Scoped to a literal STRING value (not a bare
    // identifier/member-expression read like `c.document_name`) because
    // real code legitimately reads `c.document_name`/`hit.document_name`
    // off verified response objects everywhere in the render path — only a
    // hand-authored literal filename is the fabrication signal.
    name: 'source-document-name literal + page-like key (citation-lookalike without a `quote` key)',
    guards:
      'Task 5 adversarial verifier: cardData/timelineData-shaped objects pairing a literal source-document filename (sourceDoc/doc/document_name) with a page key — a citation-lookalike that evades the quote+rects/page signature because it never writes `quote`',
    test: (content) => {
      const nameKeyRe = /\b(?:sourceDoc|doc|document_name)\s*:\s*(['"`])/g;
      let m;
      while ((m = nameKeyRe.exec(content))) {
        const literal = readStringLiteralAt(content, m.index + m[0].length - 1);
        if (!literal) continue;
        const enclosing = enclosingBraces(content, m.index);
        if (enclosing && /\bpage\s*:/.test(enclosing)) return true;
      }
      return false;
    },
  },
  {
    // Task 5 adversarial verifier's second evasion: a long literal string
    // under an `extractedText`-like key impersonates real OCR/parser output
    // (the qaDocuments.pagesContent[].extractedText shape) without ever
    // calling a parser. Length-gated (>40 chars) so a short placeholder or
    // a variable read (`extractedText: someVar` has no opening quote to
    // match at all) doesn't false-positive.
    name: 'extractedText-shaped literal (fabricated OCR/parser body text)',
    guards:
      'Task 5 adversarial verifier: literal multi-sentence body text assigned under an extractedText-like key, presented as if it came from a real extraction/OCR pass',
    test: (content) => {
      const keyRe = /\bextractedText\s*:\s*(['"`])/g;
      let m;
      while ((m = keyRe.exec(content))) {
        const literal = readStringLiteralAt(content, m.index + m[0].length - 1);
        if (literal && literal.body.length > 40) return true;
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

// ---- demoData.js allowlist: keeps the single-file exclusion above honest ----
//
// Parses (regex-based, not a full JS parser — sufficient for this repo's
// import style) both static `import ... from '...'` and dynamic `import(...)`
// specifiers out of every product file, resolves relative specifiers to
// actual paths, and checks who reaches demoData.js and the dev-gated
// components that are allowed to import it.
function extractImportSpecifiers(content) {
  const specifiers = [];
  const staticRe = /\bimport\s+(?:[\s\S]*?\sfrom\s+)?(['"])([^'"]+)\1/g;
  let m;
  while ((m = staticRe.exec(content))) specifiers.push({ type: 'static', spec: m[2] });
  const dynRe = /\bimport\(\s*(['"])([^'"]+)\1\s*\)/g;
  while ((m = dynRe.exec(content))) specifiers.push({ type: 'dynamic', spec: m[2] });
  return specifiers;
}

function resolveRelativeImport(fromFile, spec) {
  if (!spec.startsWith('.')) return null; // not a relative product-file import (e.g. 'react', 'lucide-react')
  const resolved = path.resolve(path.dirname(fromFile), spec);
  const candidates = [resolved, `${resolved}.js`, `${resolved}.jsx`];
  return candidates.find((c) => fs.existsSync(c) && fs.statSync(c).isFile()) || null;
}

describe('demoData allowlist (cleanup/verified-ui Task 5)', () => {
  const DEV_GATED_COMPONENTS = [
    path.join(SRC_DIR, 'components', 'DemoWorkspace.jsx'),
    path.join(SRC_DIR, 'components', 'DocumentView.jsx'),
  ];
  const allProductFiles = walkAllProductFiles(SRC_DIR);

  it('src/demoData.js exists — the one product file allowlisted out of the general scan above', () => {
    expect(fs.existsSync(DEMO_DATA_PATH)).toBe(true);
  });

  it('demoData.js is imported ONLY by the dev-gated components, never by App.jsx or any other product file', () => {
    const importers = [];
    for (const file of allProductFiles) {
      if (file === DEMO_DATA_PATH) continue;
      const content = fs.readFileSync(file, 'utf8');
      for (const { spec } of extractImportSpecifiers(content)) {
        if (resolveRelativeImport(file, spec) === DEMO_DATA_PATH) {
          importers.push(file);
          break;
        }
      }
    }
    expect(importers.sort()).toEqual([...DEV_GATED_COMPONENTS].sort());
  });

  it('the dev-gated components are reachable only from inside the dev-gated boundary: DemoWorkspace.jsx (the code-splitting boundary App.jsx dynamically imports) is never statically imported by anything, and DocumentView.jsx is never statically imported by anything OTHER than DemoWorkspace.jsx itself (which is fine — it is already inside the dev-gated chunk)', () => {
    const DEMO_WORKSPACE = path.join(SRC_DIR, 'components', 'DemoWorkspace.jsx');
    const DOCUMENT_VIEW = path.join(SRC_DIR, 'components', 'DocumentView.jsx');
    // Only DemoWorkspace.jsx is allowed to statically import DocumentView.jsx
    // — that's the one edge fully inside the dev-gated chunk. A stray
    // top-level `import` of either file from OUTSIDE that boundary would
    // defeat code-splitting and ship demo data into every production bundle.
    const allowedStaticImporters = {
      [DEMO_WORKSPACE]: [],
      [DOCUMENT_VIEW]: [DEMO_WORKSPACE],
    };
    for (const [target, allowed] of Object.entries(allowedStaticImporters)) {
      const staticImporters = [];
      for (const file of allProductFiles) {
        if (file === target) continue;
        const content = fs.readFileSync(file, 'utf8');
        for (const { type, spec } of extractImportSpecifiers(content)) {
          if (type === 'static' && resolveRelativeImport(file, spec) === target) {
            staticImporters.push(file);
          }
        }
      }
      const unexpected = staticImporters.filter((f) => !allowed.includes(f));
      expect(unexpected, `${path.basename(target)} unexpectedly statically imported by: ${unexpected.join(', ')}`).toEqual([]);
    }
  });

  it('App.jsx reaches DemoWorkspace only via a dynamic import() literal-guarded by import.meta.env.DEV (the pattern Vite/esbuild dead-code-eliminates in production builds)', () => {
    const appContent = fs.readFileSync(path.join(SRC_DIR, 'App.jsx'), 'utf8');
    expect(appContent).toMatch(/import\.meta\.env\.DEV\s*\?\s*React\.lazy\(\s*\(\)\s*=>\s*import\(['"]\.\/components\/DemoWorkspace['"]\)\s*\)\s*:\s*null/);
  });
});
