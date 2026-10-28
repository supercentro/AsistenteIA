import { expect, test } from '@playwright/test'

// Spanish copy lives in src/lib/strings.es.ts; the smoke test only checks that the app boots.
test('the start page sends an anonymous visitor to the login screen', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
})

test('unknown route shows the not-found page', async ({ page }) => {
  await page.goto('/does-not-exist')

  await expect(page.getByRole('heading', { name: 'Página no encontrada' })).toBeVisible()
})
