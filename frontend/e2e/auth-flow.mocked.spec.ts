import { expect, test, type Page } from '@playwright/test'
import { errorBody, mockApi, signInHandlers, student, subject, teacher } from './support/mockApi.ts'

// Spanish copy lives in src/lib/strings.es.ts; the texts used here are the visible labels.
async function signIn(page: Page, email: string) {
  await page.getByLabel('Correo electrónico').fill(email)
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
}

test('registers a student, is sent to the login screen with a notice and signs in', async ({
  page,
}) => {
  await mockApi(page, {
    ...signInHandlers(student, [subject({ name: 'Algebra Lineal', description: 'Unidad 1' })]),
    'POST /auth/register': () => ({ status: 201, body: student }),
  })
  await page.goto('/register')

  await page.getByLabel('Nombre').fill('Ana Estudiante')
  await page.getByLabel('Correo electrónico').fill('ana@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Crear cuenta' }).click()

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('status')).toContainText('La cuenta se creó correctamente')

  await signIn(page, 'ana@example.com')

  await expect(page.getByRole('heading', { level: 1, name: 'Mis asignaturas' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: 'Algebra Lineal' })).toBeVisible()
  await expect(page.getByText('Unidad 1')).toBeVisible()
})

test('a teacher signs in and sees the teacher view without management controls', async ({
  page,
}) => {
  await mockApi(page, signInHandlers(teacher, [subject()]))
  await page.goto('/login')

  await signIn(page, 'tomas@example.com')

  await expect(
    page.getByRole('heading', { level: 1, name: 'Asignaturas a mi cargo' }),
  ).toBeVisible()
  await expect(page.getByRole('button')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
})

test('sends the token to protected endpoints only', async ({ page }) => {
  const { seen } = await mockApi(page, signInHandlers(student, []))
  await page.goto('/login')

  await signIn(page, 'ana@example.com')
  await expect(page.getByText('Todavía no hay asignaturas')).toBeVisible()

  const login = seen.find((call) => call.key === 'POST /auth/login')
  const profile = seen.find((call) => call.key === 'GET /users/me')
  expect(login?.authorization).toBeNull()
  expect(profile?.authorization).toBe('Bearer e2e.fake.token')
})

test('wrong credentials show one message and stay on the login screen', async ({ page }) => {
  await mockApi(page, {
    'POST /auth/login': () => ({ status: 401, body: errorBody('INVALID_CREDENTIALS') }),
  })
  await page.goto('/login')

  await signIn(page, 'ana@example.com')

  await expect(page.getByRole('alert')).toHaveText('Correo o contraseña incorrectos.')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('server side text')).toHaveCount(0)
})

test('a rate limit states the wait from Retry-After', async ({ page }) => {
  await mockApi(page, {
    'POST /auth/login': () => ({
      status: 429,
      body: errorBody('RATE_LIMITED'),
      headers: { 'retry-after': '17' },
    }),
  })
  await page.goto('/login')

  await signIn(page, 'ana@example.com')

  await expect(page.getByRole('alert')).toContainText('Espere 17 segundos')
})

test('reloading the page ends the session: the login screen is shown again', async ({ page }) => {
  await mockApi(page, signInHandlers(student, [subject()]))
  await page.goto('/login')
  await signIn(page, 'ana@example.com')
  await expect(page.getByRole('heading', { level: 2, name: 'Algebra' })).toBeVisible()

  await page.reload()

  await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
  const stored = await page.evaluate(() => ({
    local: window.localStorage.length,
    session: window.sessionStorage.length,
    cookie: document.cookie,
  }))
  expect(stored).toEqual({ local: 0, session: 0, cookie: '' })
})

test('a 401 in the middle of the session returns to the login screen with a notice', async ({
  page,
}) => {
  let subjectsCalls = 0
  await mockApi(page, {
    ...signInHandlers(student, []),
    'GET /subjects': () => {
      subjectsCalls += 1
      return { status: 401, body: errorBody('UNAUTHORIZED') }
    },
  })
  await page.goto('/login')

  await signIn(page, 'ana@example.com')

  await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('La sesión ya no es válida')
  expect(subjectsCalls).toBe(1)
})

test('signing out clears the session and shows the notice', async ({ page }) => {
  await mockApi(page, signInHandlers(student, [subject()]))
  await page.goto('/login')
  await signIn(page, 'ana@example.com')
  await expect(page.getByRole('heading', { level: 2, name: 'Algebra' })).toBeVisible()

  await page.getByRole('button', { name: 'Cerrar sesión' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('La sesión se cerró correctamente')
})

test.describe('narrow viewport', () => {
  test.use({ viewport: { width: 320, height: 640 } })

  test('the login form and a subject with a very long name fit without horizontal scrolling', async ({
    page,
  }) => {
    await mockApi(
      page,
      signInHandlers(student, [subject({ name: 'N'.repeat(140), description: 'D'.repeat(400) })]),
    )
    await page.goto('/login')
    await expect(page.getByLabel('Correo electrónico')).toBeVisible()
    const loginFits = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    )
    expect(loginFits).toBe(true)

    await signIn(page, 'ana@example.com')
    await expect(page.getByRole('heading', { level: 2 })).toBeVisible()

    const listFits = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    )
    expect(listFits).toBe(true)
  })
})
