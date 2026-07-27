import { defineConfig, devices } from '@playwright/test';

const host = '127.0.0.1';
const mainBackend = 18787;
const readyBackend = 18788;
const noneBackend = 18789;
const unavailableBackend = 18790;
const mainFrontend = 15173;
const readyFrontend = 15174;
const noneFrontend = 15175;
const unavailableFrontend = 15176;

const backendServer = (port, env) => ({
  command: `cd ../backend && ${env} uv run python -m scripts.e2e_server --port ${port}`,
  url: `http://${host}:${port}/api/health`,
  reuseExistingServer: false,
  timeout: 120_000,
});

const frontendServer = (port, backendPort) => ({
  command: `BRF_FRONTEND_PORT=${port} BRF_BACKEND_URL=http://${host}:${backendPort} npm run dev -- --host ${host}`,
  url: `http://${host}:${port}/brfv2/`,
  reuseExistingServer: false,
  timeout: 120_000,
});

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  retries: 0,
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: `http://${host}:${mainFrontend}/brfv2/`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    backendServer(mainBackend, 'BRF_LLM=scripted BRF_EMBEDDER=hashed BRF_SCRIPTED_LLM_DELAY_MS=650'),
    backendServer(readyBackend, 'BRF_LLM=selfhosted BRF_EMBEDDER=hashed BRF_LLM_BASE_URL=http://127.0.0.1:9/v1 BRF_LLM_MODEL=gemma4:e12b BRF_LLM_RUNTIME_LABEL=e2e-ready'),
    backendServer(noneBackend, 'BRF_LLM=disabled BRF_EMBEDDER=hashed'),
    frontendServer(mainFrontend, mainBackend),
    frontendServer(readyFrontend, readyBackend),
    frontendServer(noneFrontend, noneBackend),
    frontendServer(unavailableFrontend, unavailableBackend),
  ],
});
