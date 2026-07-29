import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app/App'
import { RouterProvider } from './app/router'
import { SessionProvider } from './state/session'

import './styles/tokens.css'
import './styles/app.css'

const container = document.getElementById('root')
if (!container) throw new Error('#root saknas')

createRoot(container).render(
  <StrictMode>
    <RouterProvider>
      <SessionProvider>
        <App />
      </SessionProvider>
    </RouterProvider>
  </StrictMode>,
)

// Production only: the dev server has its own module graph, and a service
// worker sitting in front of it makes every edit a cache-invalidation puzzle.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // The ?v= is what makes a release actually replace the previous worker
    // (see vite.config.ts) — the worker reads it back to name its cache.
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js?v=${__KALLA_BUILD__}`)
      .catch(() => {
        // No offline shell. Everything else still works.
      })
  })
}
