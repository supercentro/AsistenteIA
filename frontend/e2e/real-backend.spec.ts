import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

/**
 * Runs the authentication flow against the REAL stack (docker compose: frontend 5173, backend
 * 8000, database). Skipped unless E2E_REAL_BACKEND=1, so CI (which has no backend for this suite)
 * never runs it.
 *
 *   E2E_REAL_BACKEND=1 npm run test:e2e -- real-backend
 *   E2E_REAL_BACKEND=1 E2E_SHORT_TOKEN=1 ...   also runs the expiry case; the backend must run
 *                                              with JWT_EXPIRE_MINUTES=1 (the minimum)
 *
 * The test creates one student per run (random email and password, nothing committed) and the
 * application has no delete-account endpoint yet, so remove the rows afterwards:
 *   DELETE FROM users WHERE email LIKE 'e2e-%@example.com';
 * The registration endpoint is rate limited (5 per minute): run the suite once per minute at most.
 */
const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'
const enabled = process.env.E2E_REAL_BACKEND === '1'
const shortToken = process.env.E2E_SHORT_TOKEN === '1'

test.describe('real backend', () => {
  test.skip(!enabled, 'set E2E_REAL_BACKEND=1 with the stack running to enable this suite')
  // The tests share one account created by the first one.
  test.describe.configure({ mode: 'serial' })

  const email = `e2e-${Date.now()}@example.com`
  const password = `pw-${randomUUID()}`

  async function register(page: Page) {
    await page.goto('/register')
    await page.getByLabel('Nombre').fill('E2E Student')
    await page.getByLabel('Correo electrónico').fill(email)
    await page.getByLabel('Contraseña').fill(password)
    await page.getByRole('button', { name: 'Crear cuenta' }).click()
    await expect(page).toHaveURL(/\/login$/)
  }

  async function signIn(page: Page) {
    await page.getByLabel('Correo electrónico').fill(email)
    await page.getByLabel('Contraseña').fill(password)
    await page.getByRole('button', { name: 'Entrar' }).click()
  }

  test('register, sign in, list, sign out and reload against the real API', async ({ page }) => {
    await register(page)
    await signIn(page)
    await expect(page.getByRole('heading', { level: 1, name: 'Mis asignaturas' })).toBeVisible()
    await expect(page.getByText('Todavía no hay asignaturas')).toBeVisible()

    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()

    await signIn(page)
    await page.getByRole('button', { name: 'Cerrar sesión' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
  })

  test('wrong credentials are answered by the server with the generic message', async ({
    page,
  }) => {
    await page.goto('/login')
    await page.getByLabel('Correo electrónico').fill(email)
    await page.getByLabel('Contraseña').fill(`${password}-wrong`)
    await page.getByRole('button', { name: 'Entrar' }).click()

    await expect(page.getByRole('alert')).toHaveText('Correo o contraseña incorrectos.')
  })

  test('a token the server rejects ends the session once (real 401)', async ({ page }) => {
    // The request really reaches the backend; only its Authorization header is tampered with.
    await page.route(`${API}/subjects`, async (route) => {
      await route.continue({
        headers: { ...route.request().headers(), authorization: 'Bearer tampered.token.value' },
      })
    })
    await page.goto('/login')
    await signIn(page)

    await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible()
    await expect(page.getByRole('status')).toContainText('La sesión ya no es válida')
  })

  test('the allowed origin gets CORS headers and the API rejects a missing token', async ({
    request,
    baseURL,
  }) => {
    const preflight = await request.fetch(`${API}/users/me`, {
      method: 'OPTIONS',
      headers: {
        origin: baseURL ?? 'http://localhost:5173',
        'access-control-request-method': 'GET',
        'access-control-request-headers': 'authorization,content-type',
      },
    })
    expect(preflight.status()).toBe(200)
    expect(preflight.headers()['access-control-allow-origin']).toBe(
      baseURL ?? 'http://localhost:5173',
    )

    const anonymous = await request.get(`${API}/users/me`)
    expect(anonymous.status()).toBe(401)
  })

  test.describe('token expiry', () => {
    test.skip(!shortToken, 'set E2E_SHORT_TOKEN=1 with the backend running JWT_EXPIRE_MINUTES=1')
    test.setTimeout(150_000)

    test('the UI signs out by itself and the server rejects the expired token', async ({
      page,
      request,
    }) => {
      let issued = ''
      page.on('response', async (response) => {
        if (response.url().endsWith('/auth/login') && response.status() === 200) {
          issued = ((await response.json()) as { access_token: string }).access_token
        }
      })
      await page.goto('/login')
      await signIn(page)
      await expect(page.getByRole('heading', { level: 1, name: 'Mis asignaturas' })).toBeVisible()

      await expect(page.getByRole('heading', { level: 1, name: 'Iniciar sesión' })).toBeVisible({
        timeout: 100_000,
      })
      await expect(page.getByRole('status')).toContainText('La sesión expiró')

      expect(issued).not.toBe('')
      const response = await request.get(`${API}/users/me`, {
        headers: { authorization: `Bearer ${issued}` },
      })
      expect(response.status()).toBe(401)
    })
  })

  // Last on purpose: it exhausts the login rate limit of this address for about a minute.
  test('a real 429 states the wait: Retry-After is exposed through CORS', async ({
    page,
    request,
  }) => {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await request.post(`${API}/auth/login`, {
        data: { email: 'nobody@example.com', password: 'wrong-password-value' },
      })
    }
    await page.goto('/login')
    await page.getByLabel('Correo electrónico').fill(email)
    await page.getByLabel('Contraseña').fill(password)
    await page.getByRole('button', { name: 'Entrar' }).click()

    await expect(page.getByRole('alert')).toContainText(/Espere \d+ segundos/)
  })
})
