import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Separate from vite.config.js (which stays app-build-only): keeps the test
// runner's config isolated from the dev-server/build config it doesn't need
// (proxy, base path).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true, // required so @testing-library/jest-dom's side-effect import finds `expect`
    setupFiles: ['./src/test-setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
});
