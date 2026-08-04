import { test, expect } from '@playwright/test';

/**
 * Every piece of visible text, measured against the surface it actually sits on.
 *
 * This exists because "is it readable" kept being answered with taste. It is a
 * ratio: WCAG AA wants 4.5:1 for normal text and 3:1 for large text, and a
 * design either clears that or it does not. The first run of this audit found
 * eleven styles below the line and the worst at 3.87:1 — none of which anyone
 * had spotted by looking.
 *
 * What it measures that a colour-token review cannot: the *composited*
 * background. A label inheriting `--muted-foreground` reads differently on the
 * page, inside a card, and inside a tinted block within that card, and the
 * only way to know is to walk the ancestor chain and flatten the alphas the way
 * the compositor does.
 *
 * **Coverage.** It audits the workspaces the running instance actually offers,
 * rather than a hardcoded list. Under `playwright.config.js` the backend is
 * `scripts.e2e_server`, which builds the product app without the desktop
 * routes — so Inkommande, Fakturor, Bevakningar, Uppgifter and Hemsidan are not
 * reachable here and are *not* covered by this run. What is covered is the
 * shell, the document library, the chat and the reader: the foundation every
 * one of those workspaces inherits its surfaces and text colours from.
 *
 * To cover the rest, point it at an instance that serves `/api/desktop/state`:
 *
 *     BRF_AUDIT_URL=http://127.0.0.1:5174/brfv2/ npx playwright test contrast
 */

const ACCOUNT = { email: 'max@demo.se', password: 'max-demo-2026' };

/** Runs in the page. Flattens alpha the way the compositor does. */
const AUDIT = () => {
  const channel = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const luminance = ([r, g, b]) =>
    0.2126 * channel(r / 255) + 0.7152 * channel(g / 255) + 0.0722 * channel(b / 255);

  const parse = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    if (parts.some(Number.isNaN)) return null;
    return { rgb: [parts[0], parts[1], parts[2]], alpha: parts.length > 3 ? parts[3] : 1 };
  };

  const composite = (front, back) =>
    front.rgb.map((c, i) => c * front.alpha + back[i] * (1 - front.alpha));

  // The page's own ground, so an element with no opaque ancestor still resolves.
  const ground = parse(getComputedStyle(document.body).backgroundColor)?.rgb ?? [255, 255, 255];

  const backgroundUnder = (element) => {
    const layers = [];
    for (let node = element; node && node !== document.documentElement; node = node.parentElement) {
      const layer = parse(getComputedStyle(node).backgroundColor);
      if (layer && layer.alpha > 0) layers.push(layer);
    }
    let result = ground;
    for (let i = layers.length - 1; i >= 0; i -= 1) result = composite(layers[i], result);
    return result;
  };

  const contrast = (a, b) => {
    const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (high + 0.05) / (low + 0.05);
  };

  const findings = [];
  const seen = new Set();

  for (const element of document.querySelectorAll('body *')) {
    // Only elements that own text. A wrapper inherits its children's text and
    // would otherwise be measured once per nesting level.
    const text = [...element.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim())
      .map((node) => node.textContent.trim())
      .join(' ');
    if (!text) continue;

    const box = element.getBoundingClientRect();
    if (box.width < 2 || box.height < 2) continue;

    const style = getComputedStyle(element);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    // Deliberately dimmed content (a settled card, a disabled control) is not a
    // contrast defect; it is a state the reader is being told about.
    if (Number(style.opacity) < 0.6) continue;

    const foreground = parse(style.color);
    if (!foreground || foreground.alpha === 0) continue;

    const background = backgroundUnder(element);
    const ratio = contrast(composite(foreground, background), background);

    const size = parseFloat(style.fontSize);
    const bold = Number(style.fontWeight) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const required = large ? 3 : 4.5;

    // One entry per distinct style, not per element: a table of forty rows is
    // one decision, and reporting it forty times hides the other thirty-nine.
    const key = `${style.color}|${size}|${style.fontWeight}|${element.className}`;
    if (seen.has(key)) continue;
    seen.add(key);

    findings.push({
      ratio: Math.round(ratio * 100) / 100,
      required,
      size: Math.round(size * 10) / 10,
      weight: style.fontWeight,
      selector: (element.className || element.tagName).toString().slice(0, 40),
      sample: text.slice(0, 44),
    });
  }

  return findings;
};

const report = (rows) =>
  rows
    .sort((a, b) => a.ratio - b.ratio)
    .map(
      (r) =>
        `  ${String(r.ratio).padStart(5)}:1 (needs ${r.required}:1)  ${String(r.size).padStart(4)}px/${r.weight}` +
        `  ${r.selector}  «${r.sample}»`,
    )
    .join('\n');

test('every visible text style clears WCAG AA against the surface it sits on', async ({ page }) => {
  const base = process.env.BRF_AUDIT_URL ?? './';
  const failures = [];
  let stylesChecked = 0;

  const audit = async (where) => {
    const rows = await page.evaluate(AUDIT);
    stylesChecked += rows.length;
    rows.filter((r) => r.ratio < r.required).forEach((r) => failures.push({ ...r, where }));
  };

  await page.goto(base);
  await page.getByLabel('E-postadress').waitFor();
  await audit('inloggning');

  await page.getByLabel('E-postadress').fill(ACCOUNT.email);
  await page.getByLabel('Lösenord').fill(ACCOUNT.password);
  await page.getByRole('button', { name: 'Logga in' }).click();
  await expect(page.getByText('Aktiv förening')).toBeVisible();

  // Whatever this instance actually offers — the desktop-only workspaces are
  // absent unless the backend serves /api/desktop/state.
  const workspaces = await page.locator('.sidebar-menu .nav-item').allInnerTexts();
  for (const name of workspaces) {
    const label = name.trim();
    if (!label) continue;
    await page.getByRole('button', { name: label, exact: true }).click();
    await page.waitForTimeout(1200);
    await audit(label);
  }

  // The reader is where the association's own documents are read, and it is the
  // one surface that carries a white page inside the interface.
  await page.getByRole('button', { name: 'Dokument', exact: true }).click();
  const firstDocument = page.getByRole('button', { name: /^Öppna / }).first();
  if (await firstDocument.count()) {
    await firstDocument.click();
    await page.getByTestId('pdf-page-indicator').waitFor();
    await page.waitForTimeout(800);
    await audit('dokumentläsaren');
  }

  expect(stylesChecked, 'the audit found no text at all — the walk is broken').toBeGreaterThan(40);
  expect(
    failures,
    `${failures.length} of ${stylesChecked} text styles are below WCAG AA:\n${report(failures)}\n`,
  ).toEqual([]);
});
