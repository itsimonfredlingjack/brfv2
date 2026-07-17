import { describe, it, expect } from 'vitest';
import { demoTabsEnabled } from './appModes';

// cleanup/verified-ui Task 5: the three pre-existing demo tabs (Granskning,
// Bevakningar, the Document Canvas they open) are leftover design-template
// scaffolding that render fabricated pipeline-shaped data (src/demoData.js).
// A fresh-context adversarial verifier found they were production-reachable.
// Simon's resolution: dev-gate them — hidden in production builds, intact
// for dev-server demos. This is the single pure gate every call site in
// App.jsx uses; kept separate from `import.meta.env.DEV` itself so the
// gating *logic* is unit-testable without needing a real Vite build.
describe('demoTabsEnabled', () => {
  it('is enabled when isDev is true (dev server / `vite dev`)', () => {
    expect(demoTabsEnabled(true)).toBe(true);
  });

  it('is disabled when isDev is false (production build)', () => {
    expect(demoTabsEnabled(false)).toBe(false);
  });

  it('coerces non-boolean truthy/falsy input defensively (import.meta.env.DEV is always a real boolean, but the helper must not silently pass through a truthy non-boolean)', () => {
    expect(demoTabsEnabled(undefined)).toBe(false);
    expect(demoTabsEnabled(0)).toBe(false);
    expect(demoTabsEnabled(1)).toBe(true);
  });
});
