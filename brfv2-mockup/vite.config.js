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
      '/api': backendTarget,
    },
  },
  plugins: [frozenPrototypeCompatibility(), react()],
})
