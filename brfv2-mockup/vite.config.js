import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { frozenPrototypeCompatibility } from './src/webkitCompat.js'

const backendTarget = process.env.BRF_BACKEND_URL || 'http://127.0.0.1:8787'
const frontendPort = Number(process.env.BRF_FRONTEND_PORT || 5173)

export default defineConfig({
  base: '/brfv2/',
  server: {
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        // The desktop delivery compares `Origin` against its own origin exactly
        // (backend/app/desktop.py — `desktop_http_boundary`) and 403s anything
        // else. Browsers omit Origin on GET but send it on POST, so without
        // this rewrite every read succeeds and every write fails — login first
        // of all. Forwarding the target's own origin lets `vite dev` sit in
        // front of a running desktop backend; it changes nothing in a build,
        // since `server.proxy` exists only in dev.
        headers: { Origin: backendTarget },
      },
    },
  },
  plugins: [frozenPrototypeCompatibility(), react()],
})
