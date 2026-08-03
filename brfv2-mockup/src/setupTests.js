import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// `globals: false` in vitest.config.js means Testing Library's own
// afterEach-based auto-cleanup never registers — without this, each test
// renders on top of the previous test's still-mounted DOM.
afterEach(() => {
  cleanup();
});

// jsdom implements neither of these, and the website editor's drag-and-drop
// layer (@dnd-kit, pulled in by @puckeditor/core) constructs one at import time
// — so a test that merely imports the website's component config dies before it
// runs a single assertion. Stubs rather than a polyfill on purpose: nothing
// under test measures anything, and a fake that reported sizes would invite
// tests to assert on numbers jsdom cannot actually produce.
if (typeof globalThis !== 'undefined' && !globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}

    unobserve() {}

    disconnect() {}
  };
}

if (typeof globalThis !== 'undefined' && !globalThis.IntersectionObserver) {
  globalThis.IntersectionObserver = class {
    observe() {}

    unobserve() {}

    disconnect() {}

    takeRecords() { return []; }
  };
}

// jsdom doesn't implement matchMedia — App.jsx's mobile-breakpoint hook
// (useMediaQuery) calls it unconditionally on every render.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
