// Pure gate for dev-only demo/scaffolding UI (cleanup/verified-ui Task 5).
//
// Granskning, Bevakningar, and the Document Canvas they open are leftover
// design-template scaffolding: they render fabricated pipeline-shaped data
// (src/demoData.js — document names, pages, "extracted text", chunks) that
// never touched the real retrieval/verification pipeline. A fresh-context
// adversarial verifier found them production-reachable even after the
// cleanup phase's C1-C4 surfaces were confirmed clean. Simon's resolution:
// keep them for dev-server demos, hide them from anything users deploy.
//
// This is a tiny pure function (not an inline `import.meta.env.DEV` check
// scattered across App.jsx) so the gating decision itself is unit-testable
// without needing a real Vite build, and every call site reads the same
// intent instead of re-deriving it.
export function demoTabsEnabled(isDev) {
  return Boolean(isDev);
}
