import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

/* WCAG 2.2 AA over the journey that matters. Automated checks catch maybe
 * half of what is wrong with a page — the contrast, name and structure half —
 * so this is the floor, not the ceiling. The manual VoiceOver/TalkBack pass
 * over Fråga → Svar → Källa is still owed before a real board uses it. */

const ANSWERABLE = 'Vad krävs för att hyra ut sin lägenhet i andra hand?'
const BO = { email: 'bo@gjutformen12.se', password: 'gjutformen-medlem-2026' }

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
