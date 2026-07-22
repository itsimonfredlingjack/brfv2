import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// `globals: false` in vitest.config.js means Testing Library's own
// afterEach-based auto-cleanup never registers — without this, each test
// renders on top of the previous test's still-mounted DOM.
afterEach(() => {
  cleanup();
});

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
