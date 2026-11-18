import { expect, test, type Page } from '@playwright/test'
import {
  POLICY_VERSION,
  errorBody,
  mockApi,
  signInHandlers,
  student,
  subject,
  teacher,
  unconsentedStudent,
} from './support/mockApi.ts'

// Spanish copy lives in src/lib/strings.es.ts; the texts used here are the visible labels.
async function signIn(page: Page, email: string) {
  await page.getByLabel('Correo electrónico').fill(email)
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
}

test('a student without consent is held, reads the policy, accepts and reaches the subjects', async ({
  page,
}) => {
  const posted: unknown[] = []
  await mockApi(page, {
    ...signInHandlers(unconsentedStudent, [subject({ name: 'Algebra Lineal' })]),
    'POST /users/me/consent': (request) => {
      posted.push(request.postDataJSON())
      return { status: 200, body: { ...unconsentedStudent, consent_version: POLICY_VERSION } }
    },
  })
  await page.goto('/login')
  await signIn(page, 'ana@example.com')

  await expect(page).toHaveURL(/\/consent$/)
  await expect(
    page.getByRole('heading', { level: 1, name: 'Aceptar la política de privacidad' }),
  ).toBeFocused()
  await expect(page.getByRole('heading', { name: 'Tratamiento por Gemini (Google)' })).toBeVisible()
  const accept = page.getByRole('button', { name: 'Aceptar y continuar' })
  await expect(accept).toBeDisabled()

  await page.getByRole('checkbox').check()
  await accept.click()

  await expect(page.getByRole('heading', { level: 1, name: 'Mis asignaturas' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: 'Algebra Lineal' })).toBeVisible()
  expect(posted).toEqual([{ consent_version: POLICY_VERSION }])
})

test('the policy page is public and has no horizontal scrolling at 320 px', async ({ page }) => {
  const { seen } = await mockApi(page, {})
  await page.setViewportSize({ width: 320, height: 700 })
  await page.goto('/privacy')

  await expect(
    page.getByRole('heading', { level: 1, name: 'Política de privacidad' }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Cómo borrar las conversaciones' })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)
  expect(seen).toEqual([])
})

test('a version rejected by the API keeps the student held with a reload message', async ({
  page,
}) => {
  await mockApi(page, {
    ...signInHandlers(unconsentedStudent, []),
    'POST /users/me/consent': () => ({ status: 422, body: errorBody('INVALID_CONSENT_VERSION') }),
  })
  await page.goto('/login')
  await signIn(page, 'ana@example.com')

  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Aceptar y continuar' }).click()

  await expect(page.getByRole('alert')).toContainText('La política cambió mientras tanto')
  await expect(page).toHaveURL(/\/consent$/)
})

test('a student can leave from the consent screen and nothing else is reachable', async ({
  page,
}) => {
  await mockApi(page, signInHandlers(unconsentedStudent, [subject()]))
  await page.goto('/login')
  await signIn(page, 'ana@example.com')
  await expect(page).toHaveURL(/\/consent$/)

  await page.getByRole('button', { name: 'Cerrar sesión' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
})

test('a teacher and a student with current consent are never sent to the consent screen', async ({
  page,
}) => {
  await mockApi(page, signInHandlers(teacher, [subject()]))
  await page.goto('/login')
  await signIn(page, 'tomas@example.com')
  await expect(page).toHaveURL(/\/subjects$/)
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()

  await mockApi(page, signInHandlers(student, [subject()]))
  await signIn(page, 'ana@example.com')
  await expect(page).toHaveURL(/\/subjects$/)
})
