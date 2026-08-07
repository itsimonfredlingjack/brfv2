# Inkommande Readable Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Inkommande readable by rebuilding top chrome and detail hierarchy while keeping the thread list and A/B1/B2 invariants.

**Architecture:** Format-first changes in the Integrations shell tabs + `IntakeQueue` FetchBar/filters/detail CSS/JSX. No backend or outcome-model changes. Prove each slice with Vitest, then capture a 1440×900 harness screenshot.

**Tech Stack:** React (Vite) in `brfv2-mockup`, Vitest + Testing Library, Playwright screenshot for evidence, Träff Identitet v2 CSS tokens.

**Spec:** `docs/superpowers/specs/2026-08-07-inkommande-readable-layout-design.md`

## Global Constraints

- Keep epistemic DOM order: message → reading → decision.
- Keep A-only: no permanent “Brevlådan är råmaterial…” manifesto.
- Keep B1: reading depth collapsed by default (`details.reading-depth` closed).
- Keep B2: `.thread-evidence` scrolls; `.thread-decisions` anchored; expanded resolve forms grow upward (no nested scroll in decision).
- Do not change ResolveForm outcomes, validation, or intake API payloads.
- Do not redesign list interaction (master/detail stays).
- Keep Träff Identitet v2 tokens; no new palette.
- Selective commits only (Inkommande files + evidence); leave unrelated WIP alone.
- Visual evidence at 1440×900 via `http://127.0.0.1:5173/brfv2/visual-inkommande.html`.

## File map

| File | Responsibility |
| --- | --- |
| `brfv2-mockup/src/components/Integrations.jsx` | Tab labels + quiet open-count |
| `brfv2-mockup/src/components/Integrations.css` | Tab/count chrome (not article) |
| `brfv2-mockup/src/components/IntakeQueue.jsx` | FetchBar copy/disclosure, filter labels, optional row meta trim, detail structure classes if needed |
| `brfv2-mockup/src/components/IntakeQueue.css` | Source row, filter row, detail hierarchy (message primary / reading secondary / air) |
| `brfv2-mockup/src/IntakeQueue.test.jsx` | Behavioral locks for chrome + hierarchy |
| `brfv2-mockup/src/visual-inkommande.jsx` | Only if harness needs a class hook for evidence |
| `docs/evidence/inkommande-readable-layout.png` | Final visual evidence |

---

### Task 1: Quiet Inkommande tab count

**Files:**
- Modify: `brfv2-mockup/src/components/Integrations.jsx`
- Modify: `brfv2-mockup/src/components/Integrations.css`
- Test: `brfv2-mockup/src/IntakeQueue.test.jsx` is the wrong home for shell tabs — add `brfv2-mockup/src/Integrations.test.jsx` if missing; otherwise extend the nearest existing Integrations test file.

**Interfaces:**
- Consumes: `openEvents` (number) already computed in `Integrations`
- Produces: tab count rendered as quiet mono `.tab-count` (not loud `.pill` chip)

- [ ] **Step 1: Locate or create the shell test**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && ls src/*Integrations*test* 2>/dev/null; rg -n "integrations-tabs|Inkommande" src --glob '*.test.*'
```

If no Integrations unit test exists, create `brfv2-mockup/src/Integrations.test.jsx` with the same `vi.mock('./api')` style as `IntakeQueue.test.jsx`, mounting `<Integrations brfId="brf-a" isAdmin />` with mocked `listSourceEvents` returning 2 open events.

- [ ] **Step 2: Write the failing test**

```javascript
it('shows the open count as quiet navigation chrome, not a loud badge', async () => {
  // mount Integrations with 2 open events (mock listSourceEvents)
  await waitFor(() => expect(screen.getByRole('tab', { name: /Inkommande/ })).toBeInTheDocument());
  const tab = screen.getByRole('tab', { name: /Inkommande/ });
  expect(tab.querySelector('.tab-count')).toHaveTextContent('2');
  expect(tab.querySelector('.pill')).toBeNull();
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/Integrations.test.jsx
```

Expected: FAIL (`.tab-count` missing; `.pill` still present).

- [ ] **Step 4: Implement minimal change**

In `Integrations.jsx`, replace:

```jsx
{openEvents > 0 && <span className="pill">{openEvents}</span>}
```

with:

```jsx
{openEvents > 0 && <span className="tab-count">{openEvents}</span>}
```

In `Integrations.css`, replace/retire `.integrations-tabs .pill` usage for this count with:

```css
.integrations-tabs .tab-count {
  margin-left: 8px;
  color: var(--ink-muted);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
```

Do not add a filled pill background.

- [ ] **Step 5: Run tests to verify pass**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/Integrations.test.jsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brfv2-mockup/src/components/Integrations.jsx brfv2-mockup/src/components/Integrations.css brfv2-mockup/src/Integrations.test.jsx
git commit -m "$(cat <<'EOF'
feat(ui): quiet Inkommande tab count chrome

EOF
)"
```

---

### Task 2: Source row as toolstrip (not article)

**Files:**
- Modify: `brfv2-mockup/src/components/IntakeQueue.jsx` (`FetchBar`)
- Modify: `brfv2-mockup/src/components/IntakeQueue.css` (`.intake-source*`)
- Test: `brfv2-mockup/src/IntakeQueue.test.jsx`

**Interfaces:**
- Consumes: existing `FetchBar` props `{ mailbox, connected, busy, onFetch, onImportFile, format, lastResult }`
- Produces: single thin source row + one disclosure titled `Om hämtning` for format limits (and only format limits — mailbox-untouched copy stays on ResolveForm)

- [ ] **Step 1: Write failing tests** (extend `describe('fetching')`)

```javascript
it('keeps the source row as a single toolstrip line', async () => {
  mountWith();
  await waitForQueue();
  const source = document.querySelector('.intake-source');
  expect(source).toBeTruthy();
  expect(source.querySelector('.intake-source-row')).toBeTruthy();
  // No permanent gray manifesto paragraph as a sibling article block
  expect(screen.queryByText(/Brevlådan är råmaterial/)).not.toBeInTheDocument();
});

it('puts fetch policy behind Om hämtning, not in the first viewport body', async () => {
  mountWith();
  await waitForQueue();
  const disclosure = screen.getByText('Om hämtning').closest('details');
  expect(disclosure).toBeTruthy();
  expect(disclosure.open).toBe(false);
  expect(screen.queryByText(/halvimporteras/)).not.toBeVisible();
  fireEvent.click(screen.getByText('Om hämtning'));
  expect(screen.getByText(/halvimporteras/)).toBeVisible();
});
```

Update the existing test that looks for summary `Vilka bilagor tas emot` to expect `Om hämtning` instead (same file ~line 471).

- [ ] **Step 2: Run tests to verify fail**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "Om hämtning|toolstrip|Vilka bilagor"
```

Expected: FAIL on new summary label / visibility assertions.

- [ ] **Step 3: Implement**

In `FetchBar`:
- Keep one `.intake-source-row` with state + actions.
- Shorten action labels: `Importera .eml` and `Hämta` (full meaning via `aria-label` / `title` if needed: `Importera en .eml-fil`, `Hämta nytt`).
- Change disclosure summary from `Vilka bilagor tas emot` to `Om hämtning`.
- Keep format note body text (product truth); do not reintroduce manifesto.

In CSS:
- `.intake-source` — no large padded card look; transparent / hairline at most; compact vertical padding (~8–10px).
- `.intake-source-row` — single horizontal toolstrip; wrap only below ~720px (existing media query ok).
- `.intake-format-disclosure` — muted summary, no box competing with tabs.

- [ ] **Step 4: Run fetching tests**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "fetching|Om hämtning|toolstrip|format"
```

Expected: PASS (including existing fetch/import tests).

- [ ] **Step 5: Commit**

```bash
git add brfv2-mockup/src/components/IntakeQueue.jsx brfv2-mockup/src/components/IntakeQueue.css brfv2-mockup/src/IntakeQueue.test.jsx
git commit -m "$(cat <<'EOF'
feat(ui): format Inkommande source row as toolstrip

EOF
)"
```

---

### Task 3: Filter row that fits above the list

**Files:**
- Modify: `brfv2-mockup/src/components/IntakeQueue.jsx` (toolbar labels)
- Modify: `brfv2-mockup/src/components/IntakeQueue.css` (`.intake-toolbar`, `.intake-counts`)
- Test: `brfv2-mockup/src/IntakeQueue.test.jsx`

**Interfaces:**
- Consumes: `filter` state `'open' | 'awaiting' | 'all'` and `counts`
- Produces: compact segmented filters with short visible labels; full names in `aria-label`

Approved visible labels (keep filter semantics):
- open → visible `Att avgöra`, `aria-label="Att ta ställning till"`
- awaiting → visible `Väntar svar`, `aria-label="Väntar svar"`
- all → visible `Alla`, `aria-label="Alla trådar"`

- [ ] **Step 1: Write failing tests**

```javascript
it('exposes compact filter labels that still name the three modes', async () => {
  mountWith();
  await waitForQueue();
  const group = screen.getByRole('group', { name: 'Filtrera kön' });
  expect(within(group).getByRole('button', { name: 'Att ta ställning till' })).toHaveTextContent(/Att avgöra/);
  expect(within(group).getByRole('button', { name: 'Väntar svar' })).toBeInTheDocument();
  expect(within(group).getByRole('button', { name: 'Alla trådar' })).toHaveTextContent(/^Alla/);
});

it('keeps the filter toolbar as its own row above the list', async () => {
  mountWith();
  await waitForQueue();
  const toolbar = document.querySelector('.intake-toolbar');
  const list = document.querySelector('.intake-list');
  expect(toolbar).toBeTruthy();
  expect(list).toBeTruthy();
  expect(toolbar.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
```

Update any existing assertions that query the long visible string `Att ta ställning till` as button name — prefer `getByRole(..., { name: 'Att ta ställning till' })` via aria-label, or `getByText(/Att avgöra/)`.

- [ ] **Step 2: Run to verify fail**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "compact filter|Att avgöra|Filtrera"
```

Expected: FAIL (visible text still long).

- [ ] **Step 3: Implement**

JSX for the three buttons (pattern):

```jsx
<button
  type="button"
  className={filter === 'open' ? 'active' : ''}
  aria-pressed={filter === 'open'}
  aria-label="Att ta ställning till"
  onClick={() => setFilter('open')}
>
  Att avgöra <span className="ui-count">{counts.openThreads || 0}</span>
</button>
```

(and matching for Väntar svar / Alla).

CSS:
- `.intake-toolbar` — full width row; `gap` generous; `flex-wrap: nowrap` at desktop ≥900px; allow wrap only on small screens.
- `.intake-counts` — true segmented control: equal/min widths, no overflow into list; counts stay mono `.ui-count`.
- Ensure toolbar sits **above** `.intake-layout`, never overlapping list cards.

- [ ] **Step 4: Run related tests**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "filter|compact|Att avgöra|awaiting|queue, before"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brfv2-mockup/src/components/IntakeQueue.jsx brfv2-mockup/src/components/IntakeQueue.css brfv2-mockup/src/IntakeQueue.test.jsx
git commit -m "$(cat <<'EOF'
feat(ui): compact Inkommande filter row above the list

EOF
)"
```

---

### Task 4: Detail pane hierarchy (message primary)

**Files:**
- Modify: `brfv2-mockup/src/components/IntakeQueue.css` (primary)
- Modify: `brfv2-mockup/src/components/IntakeQueue.jsx` only if a class hook is missing (prefer CSS)
- Test: `brfv2-mockup/src/IntakeQueue.test.jsx`

**Interfaces:**
- Consumes: existing `ThreadDetail` structure (`.detail-head`, `.detail-section.messages`, `ReadingPanel`, `.thread-decisions`)
- Produces: visual hierarchy via classes already present; optional `.message--primary` not required if `.message-body` can carry weight

- [ ] **Step 1: Write failing structural/CSS-hook tests**

```javascript
describe('readable detail hierarchy', () => {
  it('keeps message before reading before decision', async () => {
    mountWith();
    await waitForQueue();
    const evidence = document.querySelector('.thread-evidence');
    const messages = evidence.querySelector('.detail-section.messages');
    const reading = evidence.querySelector('.detail-section.reading');
    const decisions = document.querySelector('.thread-decisions');
    expect(messages.compareDocumentPosition(reading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(evidence.compareDocumentPosition(decisions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('marks reading as secondary chrome relative to the message', async () => {
    mountWith();
    await waitForQueue();
    const reading = document.querySelector('.detail-section.reading');
    expect(reading.classList.contains('reading--secondary')).toBe(true);
    expect(reading.querySelector('details.reading-depth')?.open ?? false).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "readable detail"
```

Expected: FAIL (`reading--secondary` missing).

- [ ] **Step 3: Implement hierarchy**

In `ReadingPanel` root:

```jsx
<section className="detail-section reading reading--secondary">
```

CSS intent (use tokens; exact px may match nearby scale):

```css
/* Message is the read target */
.detail-section.messages { background: transparent; }
.message-body {
  font-size: var(--text-base);
  line-height: 1.65;
  padding: 16px 18px;
  background: var(--field);
  border: 1px solid var(--border);
  border-radius: var(--radius-block);
}

/* Detail subject: one calm header, not a second newspaper */
.detail-head {
  padding: 16px 22px 12px;
  border-bottom: 1px solid var(--border);
}
.detail-head h3 {
  font-family: var(--font-serif);
  font-size: var(--text-xl); /* was likely text-2xl — step down one */
  line-height: 1.3;
  letter-spacing: -0.02em;
}

/* Reading is bihang */
.detail-section.reading--secondary {
  background: transparent;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
.reading--secondary .detail-section-head h4 {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: none;
}
.reading--secondary .reading-headline {
  font-size: var(--text-sm);
  color: var(--ink-muted);
}

/* Decision foot stays B2 — do not restyle outcomes */
```

Do **not** move decision DOM. Do **not** open reading depth by default.

- [ ] **Step 4: Run detail + resolve tests**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "readable detail|detail layout|what the app believes|resolving"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brfv2-mockup/src/components/IntakeQueue.jsx brfv2-mockup/src/components/IntakeQueue.css brfv2-mockup/src/IntakeQueue.test.jsx
git commit -m "$(cat <<'EOF'
feat(ui): hierarchy Inkommande detail — message primary, reading secondary

EOF
)"
```

---

### Task 5: Trim list row meta (minimal)

**Files:**
- Modify: `brfv2-mockup/src/components/IntakeQueue.jsx` (`ThreadRow`)
- Modify: `brfv2-mockup/src/components/IntakeQueue.css` (`.thread-meta`, `.thread-row-state`)
- Test: `brfv2-mockup/src/IntakeQueue.test.jsx`

**Interfaces:**
- Consumes: `thread.{ subject, latest_sender_display, latest_sender, latest_at, open_count, resolved }`
- Produces: same choose-from-list behavior; quieter meta

- [ ] **Step 1: Write / adjust test**

Existing test `shows a thread as something to choose, not something to decide from` must still pass. Add:

```javascript
it('keeps list rows choose-dense: subject, sender, date — not a decision form', async () => {
  mountWith();
  await waitForQueue();
  const row = document.querySelector('.thread-row');
  expect(row.querySelector('.thread-subject')).toBeTruthy();
  expect(row.querySelector('.thread-meta')).toBeTruthy();
  expect(row.querySelector('.thread-meta').textContent).not.toMatch(/meddelande|bilaga/i);
});
```

(If current meta already lacks those words, the test locks the invariant.)

- [ ] **Step 2: Run to verify current state**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "choose-dense|something to choose"
```

If already PASS with no code change, skip Step 3 implementation beyond CSS demotion of `.thread-row-state` / `.thread-meta` size/color. If FAIL, trim markup.

- [ ] **Step 3: Implement minimal trim**

Keep:

```jsx
<span className="thread-subject">{thread.subject}</span>
<span className="thread-meta">
  {thread.latest_sender_display || thread.latest_sender}
  {' · '}<span className="thread-date">{formatDate(thread.latest_at)}</span>
</span>
```

Open count may remain as a small mono state on the right; style it quieter (`color: var(--ink-subtle)`). Do not add category chips back onto rows.

- [ ] **Step 4: Run list tests**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx -t "queue, before|choose"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brfv2-mockup/src/components/IntakeQueue.jsx brfv2-mockup/src/components/IntakeQueue.css brfv2-mockup/src/IntakeQueue.test.jsx
git commit -m "$(cat <<'EOF'
feat(ui): quiet Inkommande list row meta

EOF
)"
```

---

### Task 6: Full suite + visual evidence

**Files:**
- Create: `docs/evidence/inkommande-readable-layout.png`
- Modify only if harness needs a tweak: `brfv2-mockup/src/visual-inkommande.jsx`

- [ ] **Step 1: Run full IntakeQueue (+ Integrations) unit tests**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm test -- --run src/IntakeQueue.test.jsx src/Integrations.test.jsx
```

Expected: all PASS.

- [ ] **Step 2: Start Vite and capture 1440×900**

```bash
cd /home/aidev/Projects/brfv2/brfv2-mockup && npm run dev -- --host 127.0.0.1 --port 5173
# other terminal:
cd /home/aidev/Projects/brfv2/brfv2-mockup && npx playwright screenshot --viewport-size=1440,900 --wait-for-timeout=1500 \
  "http://127.0.0.1:5173/brfv2/visual-inkommande.html" \
  "../docs/evidence/inkommande-readable-layout.png"
```

Harness must use `.main-layout` row (sidebar + main), not stacked `.app-shell` children — already fixed in prior iteration; do not regress.

- [ ] **Step 3: Manual checklist against the PNG**

1. Top is toolstrip (no manifesto body under title).
2. Filters fit calmly above list.
3. Message is visually primary in detail.
4. Reading collapsed / secondary.
5. Decision footer reachable in viewport (B2).
6. List still recognizable and quieter than chrome/detail noise.

- [ ] **Step 4: Commit evidence**

```bash
git add docs/evidence/inkommande-readable-layout.png
git commit -m "$(cat <<'EOF'
test(ui): evidence for Inkommande readable layout

EOF
)"
```

---

## Spec coverage self-check

| Spec requirement | Task |
| --- | --- |
| Quiet tabs / count | Task 1 |
| Source row toolstrip + policy disclosure | Task 2 |
| No permanent manifesto | Task 2 (+ existing test) |
| Filters fit above list | Task 3 |
| Message primary / reading secondary / decision foot | Task 4 (+ B2 keep) |
| List minimal trim | Task 5 |
| 1440×900 evidence + success criteria | Task 6 |
| Keep A/B1/B2 + outcomes | Global constraints + Tasks 4/6 regression tests |

## Placeholder scan

None intentional. Filter visible labels are fixed to `Att avgöra` / `Väntar svar` / `Alla`. Disclosure title fixed to `Om hämtning`.
