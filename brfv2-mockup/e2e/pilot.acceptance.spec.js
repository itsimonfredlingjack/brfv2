import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const uploadFixture = path.join(here, 'fixtures', 'pilot-upload.pdf');

const max = {
  email: 'max@demo.se',
  password: 'max-demo-2026',
};

async function login(page, account = max) {
  await page.goto('./');
  await page.getByLabel('E-postadress').fill(account.email);
  await page.getByLabel('Lösenord').fill(account.password);
  const loginResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/auth/login') && response.request().method() === 'POST'
  );
  await page.getByRole('button', { name: 'Logga in' }).click();
  expect((await loginResponse).status()).toBe(200);
  await expect(page.getByText('Aktiv förening')).toBeVisible();
}

async function openChat(page) {
  await page.getByRole('button', { name: 'AI-chatt' }).click();
  await expect(page.getByRole('heading', { name: 'Fråga dokumenten' })).toBeVisible();
}

async function ask(page, question) {
  await openChat(page);
  const input = page.getByPlaceholder('Fråga rakt in i högen…');
  await input.fill(question);
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/brf/')
      && response.url().endsWith('/ask')
      && response.request().method() === 'POST'
  );
  await page.getByRole('button', { name: 'Skicka fråga' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  return response.json();
}

async function currentDocuments(page, brfId) {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/brf/${id}/documents`, { credentials: 'include' });
    if (!response.ok) throw new Error(`documents ${id}: ${response.status}`);
    return response.json();
  }, brfId);
}

test.describe.serial('BRF Eken pilot acceptance contract', () => {
  test('login establishes the correct active association and tenant-scoped real library', async ({ page }) => {
    await login(page);

    const association = page.getByRole('combobox', { name: 'Byt aktiv förening' });
    await expect(association).toHaveValue('gjutformen-12');
    await expect(page.getByText('Dokument för Brf Gjutformen 12.')).toBeVisible();
    await expect(page.getByText('Admin', { exact: true })).toBeVisible();

    const gjutformen = await currentDocuments(page, 'gjutformen-12');
    const sjoutsikten = await currentDocuments(page, 'sjoutsikten-7');
    expect(gjutformen.length).toBeGreaterThan(0);
    expect(sjoutsikten.length).toBeGreaterThan(0);
    expect(gjutformen.map((doc) => doc.name)).toContain('Stadgar Brf Gjutformen 12.pdf');
    expect(sjoutsikten.map((doc) => doc.name)).toContain('Stadgar Brf Sjöutsikten 7.pdf');
    expect(new Set(gjutformen.map((doc) => doc.id))).not.toEqual(new Set(sjoutsikten.map((doc) => doc.id)));

    await expect(page.getByRole('button', { name: 'Öppna Stadgar Brf Gjutformen 12.pdf' })).toBeVisible();
    await expect(page.getByText('Stadgar Brf Sjöutsikten 7.pdf', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Ladda upp dokument' })).toBeVisible();
  });

  test('grounded answer resolves to the exact document, page, PDF and highlight', async ({ page }) => {
    await login(page);
    const documents = await currentDocuments(page, 'gjutformen-12');

    const body = await ask(page, 'Var har styrelsen sitt säte?');
    expect(body.refusal).toBe(false);
    expect(body.provider).toBe('fake');
    expect(body.model).toBe('');
    expect(body.citations).toHaveLength(1);

    const citation = body.citations[0];
    expect(citation.document_name).toBe('Stadgar Brf Gjutformen 12.pdf');
    expect(citation.page).toBe(1);
    expect(citation.quote).toContain('Styrelsen har sitt säte i Göteborgs kommun');
    expect(citation.rects.length).toBeGreaterThan(0);
    expect(documents.some((doc) => doc.id === citation.document_id && doc.name === citation.document_name)).toBe(true);

    await expect(page.getByText('Testleverantör – inte redo')).toBeVisible();
    const citationControl = page.getByRole('button', {
      name: new RegExp(`${citation.document_name}.*s\\.${citation.page}`),
    });
    await expect(citationControl).toBeVisible();

    const pdfResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/api/brf/gjutformen-12/documents/${citation.document_id}/pdf`)
    );
    await citationControl.click();
    expect((await pdfResponse).status()).toBe(200);

    await expect(page.getByRole('heading', { name: citation.document_name })).toBeVisible();
    await expect(page.getByTestId('pdf-page-indicator')).toContainText('Sida 1 av 3');
    const highlights = page.getByTestId('citation-highlight');
    await expect(highlights.first()).toBeVisible();
    expect(await highlights.count()).toBeGreaterThan(0);
    const box = await highlights.first().boundingBox();
    expect(box?.width).toBeGreaterThan(0);
    expect(box?.height).toBeGreaterThan(0);

    await expect(page.getByRole('button', { name: /Kvalitetskontroll/ })).toBeDisabled();
    await expect(page.getByRole('button', { name: /Fråga dokumentet/ })).toBeDisabled();
    await expect(page.getByText('Utanför pilotens omfattning')).toBeVisible();
    await expect(page.getByText('Behöver granskas')).toHaveCount(0);
  });

  test('unsupported questions produce a safe refusal without citations', async ({ page }) => {
    await login(page);
    const body = await ask(page, 'Vilka regler gäller för bastun?');

    expect(body.refusal).toBe(true);
    expect(['low_relevance', 'insufficient_data']).toContain(body.refusal_reason);
    expect(body.citations).toHaveLength(0);
    await expect(page.getByText('Ej belagt')).toBeVisible();
    await expect(page.locator('.chat-citations')).toHaveCount(0);
  });

  test('administrator upload is synchronously ingested, listed, indexed and queryable', async ({ page }) => {
    await login(page);
    const uploadResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith('/api/brf/gjutformen-12/documents')
        && response.request().method() === 'POST'
    );

    await page.locator('input[type="file"]').setInputFiles(uploadFixture);
    const uploadResponse = await uploadResponsePromise;
    expect(uploadResponse.status()).toBe(200);
    const uploaded = await uploadResponse.json();
    expect(uploaded.name).toBe('pilot-upload.pdf');
    expect(uploaded.pages).toBe(1);
    expect(uploaded.words).toBeGreaterThan(0);
    expect(uploaded.chunks).toBeGreaterThan(0);

    const uploadedDocumentControl = page.getByRole('button', { name: 'Öppna pilot-upload.pdf' });
    await expect(uploadedDocumentControl).toBeVisible();
    await expect(uploadedDocumentControl.getByText('Ny', { exact: true })).toBeVisible();

    const body = await ask(page, 'Vilken färgkod använder pilotens kontrollprotokoll?');
    expect(body.refusal).toBe(false);
    expect(body.citations).toHaveLength(1);
    expect(body.citations[0].document_id).toBe(uploaded.id);
    expect(body.citations[0].document_name).toBe('pilot-upload.pdf');
    expect(body.citations[0].page).toBe(1);
    expect(body.citations[0].quote).toContain('KOPPARFYREN-77');

    const citation = page.getByRole('button', { name: /pilot-upload\.pdf.*s\.1/ });
    await citation.click();
    await expect(page.getByRole('heading', { name: 'pilot-upload.pdf' })).toBeVisible();
    await expect(page.getByTestId('pdf-page-indicator')).toContainText('Sida 1 av 1');
    await expect(page.getByTestId('citation-highlight').first()).toBeVisible();
  });

  test('member UI and backend both deny upload and deletion', async ({ page }) => {
    await login(page);
    const association = page.getByRole('combobox', { name: 'Byt aktiv förening' });
    await association.selectOption('sjoutsikten-7');
    await expect(association).toHaveValue('sjoutsikten-7');
    await expect(page.getByText('Medlem', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ladda upp dokument' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^Ta bort / })).toHaveCount(0);

    const docs = await currentDocuments(page, 'sjoutsikten-7');
    const statuses = await page.evaluate(async ({ docId }) => {
      const form = new FormData();
      form.append('file', new Blob(['not a pdf'], { type: 'application/pdf' }), 'forbidden.pdf');
      const upload = await fetch('/api/brf/sjoutsikten-7/documents', {
        method: 'POST', credentials: 'include', body: form,
      });
      const deletion = await fetch(`/api/brf/sjoutsikten-7/documents/${docId}`, {
        method: 'DELETE', credentials: 'include',
      });
      return { upload: upload.status, deletion: deletion.status };
    }, { docId: docs[0].id });
    expect(statuses).toEqual({ upload: 403, deletion: 403 });
    expect((await currentDocuments(page, 'sjoutsikten-7')).some((doc) => doc.id === docs[0].id)).toBe(true);
  });

  test('association switch clears documents, completed citations and pending answers without late leakage', async ({ page }) => {
    await login(page);
    const completed = await ask(page, 'Var har styrelsen sitt säte?');
    expect(completed.citations[0].document_name).toBe('Stadgar Brf Gjutformen 12.pdf');
    await expect(page.getByText(/Stadgar Brf Gjutformen 12\.pdf s\.1/)).toBeVisible();

    const input = page.getByPlaceholder('Fråga rakt in i högen…');
    await input.fill('När ska årsavgiften betalas?');
    await page.getByRole('button', { name: 'Skicka fråga' }).click();
    await expect(page.getByText('Söker i högen…')).toBeVisible();

    const association = page.getByRole('combobox', { name: 'Byt aktiv förening' });
    await association.selectOption('sjoutsikten-7');
    await expect(association).toHaveValue('sjoutsikten-7');
    await expect(page.getByText('Söker i högen…')).toHaveCount(0);
    await expect(page.getByText(/Stadgar Brf Gjutformen 12\.pdf s\.1/)).toHaveCount(0);
    await page.waitForTimeout(900);
    await expect(page.getByText(/Årsavgiften betalas månadsvis/)).toHaveCount(0);

    await page.getByRole('button', { name: 'Dokument' }).click();
    await expect(page.getByRole('button', { name: 'Öppna Stadgar Brf Sjöutsikten 7.pdf' })).toBeVisible();
    await expect(page.getByText('Stadgar Brf Gjutformen 12.pdf', { exact: true })).toHaveCount(0);
    await expect(page.getByText('pilot-upload.pdf', { exact: true })).toHaveCount(0);
  });

  test('pilot navigation exposes no fictional global search or future administration actions', async ({ page }) => {
    await login(page);
    await expect(page.getByText('PILOT', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Hem' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Inställningar' })).toHaveCount(0);
    await expect(page.getByPlaceholder('Sök efter avtal, paragrafer eller ämnen...')).toHaveCount(0);
    await expect(page.getByText('Hittade 5 träffar i 3 dokument.')).toHaveCount(0);
  });
});
