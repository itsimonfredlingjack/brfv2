import { defineConfig, devices } from '@playwright/test'

/* Real backend, real auth, real tenant scoping, real storage, real retrieval,
 * real citation verification, real page rasterization, real highlight
 * placement. Only generation is deterministic (BRF_LLM=scripted), so the
 * suite can assert on exact answers without a GPU in the loop.
 *
 * Ports sit above brfv2-mockup's (18787-18790 / 15173-15176) so both
 * acceptance suites can run at the same time.
 */

const host = '127.0.0.1'
const backendPort = 18791
const frontendPort = 15177

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: `http://${host}:${frontendPort}/m/`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'pixel-7',
      use: { ...devices['Pixel 7'], browserName: 'chromium' },
    },
    {
      // iPhone 14 geometry on the chromium engine: only chromium is
      // installed by `make setup`, and what is being checked here is layout
      // and touch behavior at 390x844@3x, not WebKit itself.
      name: 'iphone-14-viewport',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: `cd ../backend && BRF_LLM=scripted BRF_EMBEDDER=hashed uv run python -m scripts.e2e_server --port ${backendPort}`,
      url: `http://${host}:${backendPort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `BRF_MOBILE_PORT=${frontendPort} BRF_BACKEND_URL=http://${host}:${backendPort} npm run dev -- --host ${host}`,
      url: `http://${host}:${frontendPort}/m/`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
