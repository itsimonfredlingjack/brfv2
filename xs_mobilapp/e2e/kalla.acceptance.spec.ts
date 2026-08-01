import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* The product journey, end to end, on a phone-sized viewport.
 *
 * ANSWERABLE / UNANSWERABLE come from the seeded golden set
 * (backend/scripts/seed_content.py). The scripted provider quotes a real
 * retrieved sentence, so citations go through the same verification the
 * pilot uses — nothing here is stubbed on the backend side.
 */

const ANSWERABLE = 'Vad krävs för att hyra ut sin lägenhet i andra hand?'
const UNANSWERABLE = 'Vilka regler gäller för bastun?'

const BO = { email: 'bo@gjutformen12.se', password: 'gjutformen-medlem-2026' }
/** Belongs to BOTH Gjutformen 12 (admin) and Sjöutsikten 7 (member). */
const MAX = { email: 'max@demo.se', password: 'max-demo-2026' }

async function login(page: Page, account = BO) {
  await page.goto('./')
  await page.getByLabel('E-post').fill(account.email)
  await page.getByLabel('Lösenord').fill(account.password)
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Logga in' }).click()
  expect((await response).status()).toBe(200)
}

async function loginAs(page: Page, account: typeof MAX, brfName: string) {
  await login(page, account)
  const chooser = page.getByRole('heading', { name: 'Välj förening' })
  if (await chooser.isVisible().catch(() => false)) {
    await page.getByRole('button', { name: new RegExp(brfName) }).click()
  }
  await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()
}

async function ask(page: Page, question: string) {
  await page.getByPlaceholder('Fråga om föreningens dokument…').fill(question)
  const response = page.waitForResponse(
    (r) => r.url().includes('/api/brf/') && r.url().endsWith('/ask') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Skicka frågan' }).click()
  const result = await response
  expect(result.status()).toBe(200)
  return result.json()
}

test.describe('Fråga → Svar → Källa', () => {
  test('a grounded answer arrives with at least one verified citation', async ({ page }) => {
    await login(page)
    await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()

    const body = await ask(page, ANSWERABLE)

    expect(body.refusal).toBe(false)
    expect(body.citations.length).toBeGreaterThan(0)

    await expect(page.getByTestId('answer-text')).toBeVisible()
    await expect(page.getByTestId('citation-chip').first()).toBeVisible()

    // Provenance is stated, never implied.
    await expect(page.getByText(/Genererat av/)).toBeVisible()
  })

  test('the citation opens the cited page with the passage highlighted in the right place', async ({
    page,
  }) => {
    await login(page)
    const body = await ask(page, ANSWERABLE)
    const citation = body.citations[0]

    await page.getByTestId('citation-chip').first().click()

    // The sheet opened on the CITED document and page — not page 1, not
    // another document.
    const sheet = page.getByRole('dialog', { name: `Källa: ${citation.document_name}` })
    await expect(sheet).toBeVisible()
    await expect(sheet.getByText(`Sida ${citation.page} av`)).toBeVisible()

    const image = page.getByTestId('page-image')
    await expect(image).toBeVisible()

    const highlight = page.getByTestId('citation-highlight').first()
    await expect(highlight).toBeVisible()

    // The highlight fades in with a slight scale-up. Measuring mid-flight
    // reads the transformed box, not the resting one — so wait for the
    // animation to settle before asserting on geometry.
    await highlight.evaluate((element) =>
      Promise.all(element.getAnimations().map((animation) => animation.finished)),
    )

    // ---- the assertion the whole product rests on ----
    // The highlight must land where the backend said the words are. Compare
    // the rendered box against the citation rect expressed as a fraction of
    // the page, using the page dimensions the extraction endpoint reports.
    const extraction = await (
      await page.request.get(
        `/api/brf/gjutformen-12/documents/${citation.document_id}/extraction`,
      )
    ).json()
    const dims = extraction.pages.find((p: { number: number }) => p.number === citation.page)
    expect(dims).toBeTruthy()

    const imageBox = (await image.boundingBox())!
    const highlightBox = (await highlight.boundingBox())!
    const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = citation.rects[0] as number[]

    const actualLeft = (highlightBox.x - imageBox.x) / imageBox.width
    const actualTop = (highlightBox.y - imageBox.y) / imageBox.height
    const actualWidth = highlightBox.width / imageBox.width
    const actualHeight = highlightBox.height / imageBox.height

    expect(actualLeft).toBeCloseTo(x0 / dims.width, 2)
    expect(actualTop).toBeCloseTo(y0 / dims.height, 2)
    expect(actualWidth).toBeCloseTo((x1 - x0) / dims.width, 2)
    expect(actualHeight).toBeCloseTo((y1 - y0) / dims.height, 2)

    // Top-left origin, not flipped: a passage in the upper half of the page
    // must not render in the lower half.
    expect(Math.abs(actualTop - (1 - y1 / dims.height))).toBeGreaterThan(0.01)
  })

  test('the passage is on screen and large enough to read when the sheet opens', async ({
    page,
  }) => {
    /* The decisive moment: the phone gets held out to another person. A
     * highlight that is technically present but rendered at five pixels, or
     * parked below the fold, fails that moment completely. */
    await login(page)
    await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    await page.waitForTimeout(600)

    const viewport = (await page.locator('.sheet__scroll').boundingBox())!
    const highlights = page.getByTestId('citation-highlight')
    const count = await highlights.count()
    expect(count).toBeGreaterThan(0)

    const boxes = []
    for (let i = 0; i < count; i += 1) boxes.push((await highlights.nth(i).boundingBox())!)

    // At least one cited line is fully within the scroller's visible area.
    const onScreen = boxes.filter(
      (b) => b.y >= viewport.y - 1 && b.y + b.height <= viewport.y + viewport.height + 1,
    )
    expect(onScreen.length, 'ingen markerad rad är synlig utan att scrolla').toBeGreaterThan(0)

    // And it is rendered at a size a person can actually read.
    const smallest = Math.min(...boxes.map((b) => b.height))
    expect(smallest, 'den markerade raden är för liten för att läsas').toBeGreaterThanOrEqual(14)
  })

  test('framing toggles between the passage and the whole page', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    await page.waitForTimeout(500)

    const viewport = (await page.locator('.sheet__scroll').boundingBox())!
    const zoomedWidth = (await page.locator('.page').boundingBox())!.width
    const toggle = page.getByTestId('framing-toggle')
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')

    await toggle.click()
    await page.waitForTimeout(400)
    const fittedWidth = (await page.locator('.page').boundingBox())!.width

    // "Hela sidan" fits the page inside the viewport…
    expect(fittedWidth).toBeLessThanOrEqual(viewport.width + 1)
    expect(fittedWidth).toBeLessThan(zoomedWidth)
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')

    // …and going back re-focuses the passage.
    await toggle.click()
    await page.waitForTimeout(400)
    expect((await page.locator('.page').boundingBox())!.width).toBeCloseTo(zoomedWidth, 0)
  })

  test('the sheet states that the citation verified, before you find it on the page', async ({
    page,
  }) => {
    await login(page)
    const body = await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()

    await expect(page.getByText('Verifierat ordagrant i dokumentet')).toBeVisible()
    // The quote is restated in readable type so the other person knows what
    // they are looking for.
    await expect(page.locator('.quotebar__quote')).toContainText(
      body.citations[0].quote.slice(0, 25),
    )
  })

  test('paging away from the cited page drops the highlight and offers a way back', async ({
    page,
  }) => {
    await login(page)
    const body = await ask(page, ANSWERABLE)
    const citation = body.citations[0]

    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('citation-highlight').first()).toBeVisible()

    const forward = page.getByRole('button', { name: 'Nästa sida' })
    const back = page.getByRole('button', { name: 'Föregående sida' })
    if (await forward.isEnabled()) await forward.click()
    else await back.click()

    await expect(page.getByTestId('citation-highlight')).toHaveCount(0)
    await expect(page.getByText(`Markeringen finns på sida ${citation.page}`)).toBeVisible()

    await page.getByRole('button', { name: 'Gå dit' }).click()
    await expect(page.getByTestId('citation-highlight').first()).toBeVisible()
  })

  test('the source sheet closes back to the answer', async ({ page }) => {
    await login(page)
    await ask(page, ANSWERABLE)

    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByRole('dialog')).toBeVisible()

    await page.getByRole('button', { name: 'Stäng källa' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByTestId('answer-text')).toBeVisible()
  })
})

test.describe('Refusals', () => {
  test('an unsupported question refuses safely, with no answer and no citations', async ({
    page,
  }) => {
    await login(page)
    const body = await ask(page, UNANSWERABLE)

    expect(body.refusal).toBe(true)
    expect(['low_relevance', 'insufficient_data']).toContain(body.refusal_reason)
    expect(body.citations).toHaveLength(0)

    await expect(page.getByTestId('answer-text')).toHaveCount(0)
    await expect(page.getByTestId('citation-chip')).toHaveCount(0)
    await expect(page.getByText('Inget svar visas utan belägg.')).toBeVisible()
  })

  test('a refusal is presented as correct behavior, not as an error', async ({ page }) => {
    await login(page)
    await ask(page, UNANSWERABLE)

    // status, not alert: the product refusing is not the product failing.
    await expect(page.getByRole('status').filter({ hasText: 'Inget svar visas utan belägg.' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})

test.describe('Recovery', () => {
  test('an expired session explains itself and keeps the question', async ({ page, context }) => {
    /* This happens mid-conversation, standing in front of someone. Being
     * silently returned to a login form with the question gone reads as the
     * app breaking. */
    await login(page)
    await context.clearCookies()

    await page.getByPlaceholder('Fråga om föreningens dokument…').fill(ANSWERABLE)
    await page.getByRole('button', { name: 'Skicka frågan' }).click()

    await expect(page.getByText('Din session har gått ut')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Logga in' })).toBeVisible()

    // Log back in — the question is waiting, not retyped.
    await page.getByLabel('E-post').fill(BO.email)
    await page.getByLabel('Lösenord').fill(BO.password)
    await page.getByRole('button', { name: 'Logga in' }).click()
    await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()
    await expect(page.getByPlaceholder('Fråga om föreningens dokument…')).toHaveValue(ANSWERABLE)
  })

  test('going back to the answer list returns you to where you were', async ({ page }) => {
    await login(page)
    // Enough answers that the list overflows on any phone in the matrix —
    // the behavior under test is restoration, not screen height.
    for (let i = 0; i < 9; i += 1) {
      await ask(page, ANSWERABLE)
      await page.getByRole('link', { name: 'Fråga' }).click()
    }

    // Let the just-navigated screen settle. Opening a screen scrolls it to
    // the top on the next frame; scrolling inside that frame would be racing
    // the app rather than testing it.
    await expect(page.getByText('Tidigare svar')).toBeVisible()
    await page.waitForTimeout(300)

    await page.evaluate(() => window.scrollTo(0, 200))
    await page.waitForTimeout(200)
    const before = await page.evaluate(() => window.scrollY)
    expect(before, 'listan gick inte att scrolla — testet mäter inget').toBeGreaterThan(40)

    await page.getByRole('button').filter({ hasText: ANSWERABLE }).first().click()
    await expect(page.getByTestId('answer-text')).toBeVisible()

    await page.goBack()
    await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()
    await page.waitForTimeout(400)
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(before - 60)
  })
})

test.describe('Bibliotek', () => {
  test('lists the förening’s documents and opens one at page 1', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Bibliotek' }).click()

    await expect(page.getByRole('heading', { name: 'Bibliotek' })).toBeVisible()
    const rows = page.getByRole('button').filter({ hasText: 'Stadgar' })
    await expect(rows.first()).toBeVisible()

    await rows.first().click()
    await page.getByRole('button', { name: 'Öppna dokumentet' }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByTestId('page-image')).toBeVisible()
    // Browsing a document is not a citation — no highlight is invented.
    await expect(page.getByTestId('citation-highlight')).toHaveCount(0)
  })
})

test.describe('Granskning', () => {
  /* Against the real endpoint: a member's session cookie is the whole
   * credential, and a förening that has imported nothing has no findings.
   * "Nothing has come in" is a state the screen owes an answer to — a
   * spinner that never resolves would be the same screen for both. */
  test('a member with no findings is told so, and is offered no way to decide', async ({ page }) => {
    await login(page)
    await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()

    const response = page.waitForResponse((r) => r.url().endsWith('/integrations/findings'))
    await page.getByRole('link', { name: 'Granskning' }).click()
    expect((await response).status()).toBe(200)

    await expect(page.getByRole('heading', { name: 'Granskning' })).toBeVisible()
    await expect(page.getByText('Inga fynd ännu')).toBeVisible()
    await expect(page.getByTestId('readonly-note')).toContainText('görs i webbappen')
  })
})

test.describe('Offline', () => {
  test('asking is refused up front, and an already-seen page still renders', async ({
    page,
    context,
  }) => {
    await login(page)
    const body = await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    await page.getByRole('button', { name: 'Stäng källa' }).click()

    await context.setOffline(true)
    await page.getByRole('link', { name: 'Fråga' }).click()

    await expect(page.getByText('Du är offline. Frågor kräver uppkoppling.').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Skicka frågan' })).toBeDisabled()

    // The answer and its page survive without a connection.
    await page.getByRole('button').filter({ hasText: ANSWERABLE }).first().click()
    await expect(page.getByTestId('answer-text')).toBeVisible()
    expect(body.citations.length).toBeGreaterThan(0)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()

    await context.setOffline(false)
  })
})

test.describe('Tenant isolation on the device', () => {
  test('switching förening removes the previous förening’s answers from the phone', async ({
    page,
  }) => {
    await loginAs(page, MAX, 'Gjutformen')
    await ask(page, ANSWERABLE)
    await page.getByRole('link', { name: 'Fråga' }).click()
    await expect(page.getByText(ANSWERABLE)).toBeVisible()

    // Switch to the other förening.
    await page.getByRole('link', { name: 'Konto och inställningar' }).click()
    await page.getByRole('button', { name: /Byt förening/ }).click()
    await page.getByRole('button', { name: /Sjöutsikten/ }).click()

    await expect(page.getByRole('heading', { name: 'Fråga' })).toBeVisible()
    await expect(page.getByText('Inga frågor ännu')).toBeVisible()

    // And switching back does not resurrect it.
    await page.getByRole('link', { name: 'Konto och inställningar' }).click()
    await page.getByRole('button', { name: /Byt förening/ }).click()
    await page.getByRole('button', { name: /Gjutformen/ }).click()
    await expect(page.getByText(ANSWERABLE)).toHaveCount(0)
  })

  test('logging out leaves nothing behind for the next person to log in', async ({ page }) => {
    await login(page)
    const body = await ask(page, ANSWERABLE)
    await page.getByTestId('citation-chip').first().click()
    await expect(page.getByTestId('page-image')).toBeVisible()
    await page.getByRole('button', { name: 'Stäng källa' }).click()

    await page.getByRole('link', { name: 'Konto och inställningar' }).click()
    await page.getByRole('button', { name: 'Logga ut' }).click()
    await expect(page.getByRole('button', { name: 'Logga in' })).toBeVisible()

    // Nothing survives in IndexedDB — not the answer, not the page image.
    const leftovers = await page.evaluate(async () => {
      const names = ['kalla-journal', 'kalla-pages', 'kalla-meta']
      const counts: Record<string, number> = {}
      for (const name of names) {
        counts[name] = await new Promise<number>((resolve) => {
          const request = indexedDB.open(name)
          request.onerror = () => resolve(-1)
          request.onsuccess = () => {
            const db = request.result
            const storeName = db.objectStoreNames[0]
            if (!storeName) {
              db.close()
              resolve(0)
              return
            }
            const countRequest = db.transaction(storeName, 'readonly').objectStore(storeName).count()
            countRequest.onsuccess = () => {
              db.close()
              resolve(countRequest.result)
            }
            countRequest.onerror = () => {
              db.close()
              resolve(-1)
            }
          }
        })
      }
      return counts
    })

    expect(leftovers['kalla-journal']).toBe(0)
    expect(leftovers['kalla-pages']).toBe(0)
    expect(leftovers['kalla-meta']).toBe(0)

    // A second user logging in on the same device sees a clean app.
    await login(page)
    await expect(page.getByText('Inga frågor ännu')).toBeVisible()
    await expect(page.getByText(body.citations[0].quote.slice(0, 30))).toHaveCount(0)
  })
})
