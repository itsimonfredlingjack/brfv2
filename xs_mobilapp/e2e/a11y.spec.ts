import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* WCAG 2.2 AA over the journey that matters. Automated checks catch maybe
 * half of what is wrong with a page — the contrast, name and structure half —
 * so this is the floor, not the ceiling. The manual VoiceOver/TalkBack pass
 * over Fråga → Svar → Källa is still owed before a real board uses it. */

const ANSWERABLE = 'Vad krävs för att hyra ut sin lägenhet i andra hand?'
const BO = { email: 'bo@gjutformen12.se', password: 'gjutformen-medlem-2026' }

/** Two findings that between them light up every block on the card: verified
 * facts, the suggestion, the uncertainty, a weak anchor with an alias waiting
 * on someone at a desk, and a decision already taken. */
const FINDINGS = [
  {
    id: 'f-1',
    tenant_id: 'gjutformen-12',
    finding_type: 'invoice_contract_amount',
    created_at: '2026-05-20T09:15:00+00:00',
    invoice_id: 'inv-1',
    source_event_id: null,
    verdict: 'possible_deviation',
    verdict_label: 'möjlig avvikelse',
    verified_facts: [
      { label: 'Leverantör enligt fakturan', value: 'Snösvängen AB', source: 'invoice', citation_index: null },
      { label: 'Fakturabelopp', value: '6 250,00 SEK', source: 'invoice', citation_index: null },
      { label: 'Belopp i citerat villkor', value: '1 250,00 SEK', source: 'document', citation_index: 0 },
    ],
    suggestion: 'Stäm av fakturans belopp mot avtalets timtaxa innan den attesteras.',
    suggested_by: 'regelmotor',
    uncertainty: 'Avtalet anger ingen mängd, så antalet timmar går inte att fastställa.',
    citations: [
      {
        document_id: 'doc-1',
        document_name: 'Snöröjningsavtal 2026',
        page: 2,
        quote: 'Ersättning utgår med 1 250 kronor per timme.',
        quotes: ['Ersättning utgår med 1 250 kronor per timme.'],
        chunk_id: 'c-1',
        rects: [[72, 320, 380, 334]],
        score: 0.82,
        approximate: false,
        corpus_origin: 'synthetic',
      },
    ],
    anchor_strength: 'partial',
    anchor_note:
      'Snöröjningsavtal 2026 skriver "Snösvängen Entreprenad AB", fakturan säger "Snösvängen AB".',
    alias_proposal: {
      invoice_name: 'Snösvängen AB',
      document_name: 'Snösvängen Entreprenad AB',
      document_id: 'doc-1',
      basis: 'Den särskiljande delen "Snösvängen" står ordagrant i Snöröjningsavtal 2026.',
    },
    status: 'open',
    decided_by: null,
    decided_at: null,
    decision_note: null,
  },
  {
    id: 'f-2',
    tenant_id: 'gjutformen-12',
    finding_type: 'invoice_contract_amount',
    created_at: '2026-05-02T09:15:00+00:00',
    invoice_id: 'inv-2',
    source_event_id: null,
    verdict: 'matches',
    verdict_label: 'överensstämmer',
    verified_facts: [
      { label: 'Fakturabelopp', value: '12 500,00 SEK', source: 'invoice', citation_index: null },
      { label: 'Belopp i citerat villkor', value: '12 500,00 SEK', source: 'document', citation_index: null },
    ],
    suggestion: 'Beloppet motsvarar avtalets månadsersättning.',
    suggested_by: 'regelmotor',
    uncertainty: null,
    citations: [],
    anchor_strength: 'org_number',
    anchor_note: 'Kopplingen är gjord på organisationsnummer (556677-8899), som är entydigt.',
    alias_proposal: null,
    status: 'approved',
    decided_by: 'bo@gjutformen12.se',
    decided_at: '2026-05-03T07:40:00+00:00',
    decision_note: 'Stämmer mot avtalet.',
  },
]

/** A board with every state on it at once: something late, something close,
 * something far off, a rhythm, a proposal nobody has approved, and a time
 * limit that could not be dated. */
const WATCH_BASE = {
  tenant_id: 'gjutformen-12',
  derivation: 'Avtalet löper till 2026-12-31, med tre månaders uppsägningstid.',
  recurrence: 'none',
  responsible: 'Anna Ek',
  remind_lead_days: 30,
  citations: [
    {
      document_id: 'doc-1',
      document_name: 'Städavtal 2024',
      page: 2,
      quote: 'Uppsägning ska ske skriftligen senast tre månader före avtalstidens utgång.',
      quotes: ['Uppsägning ska ske skriftligen senast tre månader före avtalstidens utgång.'],
      chunk_id: 'c-1',
      rects: [[72, 320, 380, 334]],
      score: 0.86,
      approximate: false,
      corpus_origin: 'synthetic',
    },
  ],
  source_document_id: 'doc-1',
  source_document_name: 'Städavtal 2024',
  created_at: '2026-07-01T09:00:00+00:00',
  decided_by: 'bo@gjutformen12.se',
  decided_at: '2026-07-02T07:40:00+00:00',
  decision_note: null,
  succeeded_by: null,
  status_label: 'bevakas',
  remind_at: '2026-08-31',
  next_due_after: null,
}

const WATCHES = {
  today: '2026-08-01',
  proposed: [
    {
      ...WATCH_BASE,
      id: 'w-proposed',
      kind: 'warranty',
      kind_label: 'Garanti',
      status: 'proposed',
      status_label: 'väntar på godkännande',
      title: 'Garantin på takarbetet går ut 2027-04-14',
      due_date: '2027-04-14',
      derived_due_date: '2027-04-14',
      responsible: '',
      bucket: 'later',
      days_left: 256,
    },
  ],
  buckets: {
    overdue: [
      {
        ...WATCH_BASE,
        id: 'w-overdue',
        kind: 'inspection',
        kind_label: 'Besiktning eller kontroll',
        status: 'approved',
        title: 'Beställ OVK-besiktning, senast 2026-07-20',
        due_date: '2026-07-20',
        derived_due_date: '2026-07-20',
        responsible: '',
        bucket: 'overdue',
        days_left: -12,
      },
    ],
    soon: [
      {
        ...WATCH_BASE,
        id: 'w-soon',
        kind: 'notice_deadline',
        kind_label: 'Uppsägning',
        status: 'approved',
        title: 'Säg upp eller ompröva städavtalet senast 2026-08-20',
        due_date: '2026-08-20',
        derived_due_date: '2026-09-30',
        bucket: 'soon',
        days_left: 19,
      },
    ],
    later: [
      {
        ...WATCH_BASE,
        id: 'w-later',
        kind: 'expiry',
        kind_label: 'Avtalet upphör',
        status: 'approved',
        title: 'Hissavtalet upphör 2026-12-31',
        due_date: '2026-12-31',
        derived_due_date: '2026-12-31',
        bucket: 'later',
        days_left: 152,
      },
    ],
    recurring: [
      {
        ...WATCH_BASE,
        id: 'w-recurring',
        kind: 'recurring_obligation',
        kind_label: 'Återkommande skyldighet',
        status: 'approved',
        title: 'Lämna in brandskyddskontrollen senast 2026-11-01',
        due_date: '2026-11-01',
        derived_due_date: '2026-11-01',
        recurrence: 'yearly',
        bucket: 'recurring',
        days_left: 92,
        next_due_after: '2027-11-01',
      },
    ],
  },
  bucketLabels: { overdue: 'Försenat', soon: 'Snart', later: 'Senare', recurring: 'Återkommande' },
  kindLabels: {
    notice_deadline: 'Uppsägning',
    expiry: 'Avtalet upphör',
    warranty: 'Garanti',
    inspection: 'Besiktning eller kontroll',
    recurring_obligation: 'Återkommande skyldighet',
  },
  statusLabels: {
    proposed: 'väntar på godkännande',
    approved: 'bevakas',
    dismissed: 'avfärdad',
    done: 'avklarad',
  },
  settled: [],
  unresolved: [
    {
      id: 'u-1',
      tenant_id: 'gjutformen-12',
      what: 'Garantitiden är fem år från slutbesiktningen.',
      why: 'Slutbesiktningens datum står inte i handlingen, så garantins slut går inte att räkna fram.',
      citations: WATCH_BASE.citations,
      source_document_id: 'doc-1',
      source_document_name: 'Städavtal 2024',
      created_at: '2026-07-01T09:00:00+00:00',
    },
  ],
}

const scan = (page: Page) =>
  new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])

async function login(page: Page) {
  await page.goto('./')
  await page.getByLabel('E-post').fill(BO.email)
  await page.getByLabel('Lösenord').fill(BO.password)
  await page.getByRole('button', { name: 'Logga in' }).click()
  await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()
}

async function ask(page: Page, question: string) {
  await page.getByPlaceholder('Fråga om föreningens dokument…').fill(question)
  const response = page.waitForResponse((r) => r.url().endsWith('/ask'))
  await page.getByRole('button', { name: 'Skicka frågan' }).click()
  await response
}

test.describe('Tillgänglighet', () => {
  test('inloggningen har inga automatiskt upptäckbara brister', async ({ page }) => {
    await page.goto('./')
    await expect(page.getByRole('button', { name: 'Logga in' })).toBeVisible()
    expect((await scan(page).analyze()).violations).toEqual([])
  })

  test('Fråga och Bibliotek är rena', async ({ page }) => {
    await login(page)
    expect((await scan(page).analyze()).violations).toEqual([])

    await page.getByRole('link', { name: 'Bibliotek' }).click()
    await expect(page.getByRole('heading', { name: 'Bibliotek' })).toBeVisible()
    expect((await scan(page).analyze()).violations).toEqual([])
  })

  /* The e2e backend seeds documents and users, not an imported invoice, so a
   * populated findings screen only exists behind a stub. What is under test
   * here is this client's rendering of a finding — contrast, structure, names
   * — and a stub carries that honestly. The real endpoint is exercised
   * against the real backend in the acceptance suite. */
  test('granskningen är ren med fynd på skärmen', async ({ page }) => {
    await page.route('**/integrations/findings', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FINDINGS),
      }),
    )

    await login(page)
    await page.getByRole('link', { name: 'Granskning' }).click()
    await expect(page.getByRole('heading', { name: 'Granskning' })).toBeVisible()
    await expect(page.getByTestId('finding')).toHaveCount(2)

    expect((await scan(page).analyze()).violations).toEqual([])
  })

  /* Same reasoning as the findings screen: the e2e backend seeds documents,
   * not a scanned archive of dated obligations, so a populated board only
   * exists behind a stub. What is under test is this client's rendering of
   * one — contrast, heading structure, and that "late" survives greyscale. */
  test('bevakningarna är rena med hela tavlan på skärmen', async ({ page }) => {
    await page.route('**/watches', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(WATCHES),
      }),
    )

    await login(page)
    await page.getByRole('link', { name: 'Bevakningar' }).click()
    await expect(page.getByRole('heading', { name: 'Bevakningar', level: 1 })).toBeVisible()
    await expect(page.getByTestId('watch')).toHaveCount(5)
    await expect(page.getByTestId('unresolved')).toHaveCount(1)

    expect((await scan(page).analyze()).violations).toEqual([])
  })

  test('en försenad bevakning läses som försenad utan färg', async ({ page }) => {
    await page.route('**/watches', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(WATCHES),
      }),
    )

    await login(page)
    await page.getByRole('link', { name: 'Bevakningar' }).click()

    // Greyscale: whatever is left has to carry the state on its own.
    await page.emulateMedia({ forcedColors: 'active' })
    const late = page.locator('[data-bucket="overdue"]')
    await expect(late.getByText('Försenat')).toBeVisible()
    await expect(late.getByText(/12 dagar sedan/)).toBeVisible()
    // …and nobody is named, which is a fact, not an empty cell.
    await expect(late.getByTestId('watch-responsible')).toHaveText('ej utsedd')
  })

  test('svaret och källan är rena', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)
    await expect(page.getByTestId('answer-text')).toBeVisible()
    expect((await scan(page).analyze()).violations).toEqual([])

    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    expect((await scan(page).analyze()).violations).toEqual([])
  })

  test('sidbilden beskrivs med det verifierade citatet, inte med "PDF-sida"', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()

    const alt = await page.getByTestId('page-image').getAttribute('alt')
    expect(alt).toContain('markerad passage')
    // The quote itself is in the alt text — that is what a screen-reader user
    // needs from this image; "sida 4" alone describes the container.
    expect((alt ?? '').length).toBeGreaterThan(40)
  })

  test('källan fångar fokus och lämnar tillbaka det', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)

    const chip = page.getByTestId('citation-chip').first()
    await chip.click()

    // Focus moves into the dialog…
    await expect(page.getByRole('button', { name: 'Stäng källa' })).toBeFocused()

    // …and Escape both closes it and hands focus back to the chip that opened it.
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(chip).toBeFocused()
  })

  test('sidan går att panorera med tangentbord', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    await page.waitForTimeout(500)

    const region = page.locator('.sheet__scroll')
    await region.focus()
    await expect(region).toBeFocused()

    const before = await region.evaluate((el) => el.scrollTop)
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await page.waitForTimeout(250)
    expect(await region.evaluate((el) => el.scrollTop)).not.toBe(before)
  })

  test('varje interaktiv yta når 44px i minsta led', async ({ page }) => {
    await login(page)
    const targets = page.locator('.tabbar__item, .avatar, .composer__send')
    const count = await targets.count()
    expect(count).toBeGreaterThan(0)

    for (let index = 0; index < count; index += 1) {
      const box = await targets.nth(index).boundingBox()
      expect(box, `mål ${index} saknar box`).toBeTruthy()
      expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(40)
    }
  })
})
