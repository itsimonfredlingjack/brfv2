import { test, expect } from '@playwright/test';

const cases = [
  {
    name: 'ready',
    url: 'http://127.0.0.1:15174/brfv2/',
    primary: 'Gemma 4 12B',
    secondary: 'Self-hosted · e2e-ready',
  },
  {
    name: 'fake',
    url: 'http://127.0.0.1:15173/brfv2/',
    primary: 'Testleverantör – inte redo',
    secondary: 'Testläge',
  },
  {
    name: 'none',
    url: 'http://127.0.0.1:15175/brfv2/',
    primary: 'Ingen modell konfigurerad',
    secondary: 'Ingen modell',
  },
  {
    name: 'unavailable',
    url: 'http://127.0.0.1:15176/brfv2/',
    primary: 'Modellstatus ej tillgänglig',
    secondary: null,
  },
];

for (const readiness of cases) {
  test(`provider readiness: ${readiness.name}`, async ({ page }) => {
    await page.goto(readiness.url);
    await expect(page.getByRole('heading', { name: 'Träff' })).toBeVisible();
    await expect(page.getByText(readiness.primary, { exact: true })).toBeVisible();
    if (readiness.secondary) {
      await expect(page.getByText(readiness.secondary, { exact: true })).toBeVisible();
    }
    const status = page.getByLabel(new RegExp(`Modellstatus: ${readiness.primary}`));
    await expect(status).toBeVisible();
    if (readiness.name !== 'ready') {
      await expect(status).not.toHaveClass(/ready/);
    }
  });
}
