import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import pkg from './package.json'

// Served at /m by the FastAPI app in production (see backend/app/main.py),
// and proxied to the same backend in dev — so the session cookie, the API
// and the app share one origin in BOTH modes. That is what keeps
// `credentials: 'include'` working without a CORS entry or a token in JS.
const backendTarget = process.env.BRF_BACKEND_URL || 'http://127.0.0.1:8787'
const frontendPort = Number(process.env.BRF_MOBILE_PORT || 5174)

export default defineConfig({
  base: '/m/',
  server: {
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': backendTarget,
    },
  },
  define: {
    // The service worker is a static file, so its bytes never change between
    // releases — which means the browser never treats it as updated and its
    // activate-time cache cleanup never runs. Registering it with a version
    // query makes each release a genuinely new worker that evicts the old
    // cache. Bump package.json's version to cut a release.
    __KALLA_BUILD__: JSON.stringify(pkg.version),
  },
  build: {
    // The whole point of rasterizing pages server-side is that this app never
    // ships a PDF engine. If the bundle ever creeps toward pdf.js territory,
    // the budget in README.md is the thing that noticed.
    chunkSizeWarningLimit: 200,
  },
  plugins: [react()],
})
