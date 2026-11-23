import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/types/api.generated.ts'
import {
  mockApi,
  signInHandlers,
  student,
  subject,
  teacher,
  type Handlers,
} from './support/mockApi.ts'

// Needs the dev server that Playwright starts (playwright.config.ts sets the build flag to true);
// a server that is already running without the flag shows no link, and the tests fail loudly.
type Activity = components['schemas']['ActivityResponse']

const SUBJECT = subject({ name: 'Quimica General' })
const BASE = `/subjects/${SUBJECT.id}`

function figures(overrides: Partial<Activity> = {}): Activity {
  return {
    window: { start: '2026-03-02', end: '2026-03-29', granularity: 'week', weeks: 4 },
    minimum_group: 5,
    enrolled_students: 12,
    active_students: 8,
    questions: [
      { period_start: '2026-03-02', count: 14 },
      { period_start: '2026-03-09', count: null },
      { period_start: '2026-03-16', count: 9 },
      { period_start: '2026-03-23', count: 7 },
    ],
    no_material_rate: 0.2,
    no_cited_source_rate: 0.45,
    documents: [
      { document_id: null, filename: 'unidad-vieja.pdf', cited_appearances: 6 },
      {
        document_id: '88888888-8888-4888-8888-888888888888',
        filename: 'unidad-2.pdf',
        cited_appearances: null,
      },
    ],
    suppressed: true,
    ...overrides,
  }
}

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill(email)
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
}

/** The session lives in memory only, so a page load would end it: navigate inside the app. */
async function goInApp(page: Page, path: string) {
  await page.evaluate((target) => {
    window.history.pushState({}, '', target)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, path)
}

function handlers(body: Activity, calls: string[]): Handlers {
  return {
    ...signInHandlers(teacher, [SUBJECT]),
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    [`GET ${BASE}/documents`]: () => ({ status: 200, body: [] }),
    [`GET ${BASE}/enrollments`]: () => ({ status: 200, body: [] }),
    [`GET ${BASE}/activity`]: (request) => {
      calls.push(new URL(request.url()).search)
      return { status: 200, body }
    },
  }
}

test('a teacher opens the activity with the keyboard and withheld figures read «Datos insuficientes»', async ({
  page,
}) => {
  const calls: string[] = []
  await mockApi(page, handlers(figures(), calls))
  await signIn(page, 'tomas@example.com')
  await page.getByRole('link', { name: 'Quimica General' }).click()

  await page.getByRole('link', { name: 'Ver actividad' }).focus()
  await page.keyboard.press('Enter')

  await expect(
    page.getByRole('heading', { level: 1, name: 'Actividad de la asignatura' }),
  ).toBeVisible()
  const weekly = page.getByRole('table', { name: 'Preguntas por semana' })
  await expect(weekly.getByRole('row')).toHaveCount(5)
  await expect(weekly.getByRole('row').nth(2)).toContainText('Datos insuficientes')
  await expect(page.getByText('Respuestas sin fuente citada')).toBeVisible()
  expect(calls).toEqual([''])
  await expect(page.getByRole('button', { name: /exportar|comparar/i })).toHaveCount(0)
})

test('with every figure withheld only the enrolled count and an explanation remain', async ({
  page,
}) => {
  const calls: string[] = []
  const body = figures({
    active_students: null,
    questions: figures().questions.map((week) => ({ ...week, count: null })),
    no_material_rate: null,
    no_cited_source_rate: null,
    documents: [],
  })
  await mockApi(page, handlers(body, calls))
  await signIn(page, 'tomas@example.com')

  await goInApp(page, `${BASE}/activity`)

  await expect(
    page.getByText(
      'Todavía no hay datos suficientes para mostrar la actividad de esta asignatura.',
    ),
  ).toBeVisible()
  await expect(page.getByText('Estudiantes inscriptos')).toBeVisible()
})

test('a student who opens the address gets the forbidden page and no request is sent', async ({
  page,
}) => {
  const calls: string[] = []
  await mockApi(page, {
    ...handlers(figures(), calls),
    ...signInHandlers(student, [SUBJECT]),
  })
  await signIn(page, 'ana@example.com')

  await goInApp(page, `${BASE}/activity`)

  await expect(page.getByRole('heading', { name: 'Acceso no permitido' })).toBeVisible()
  expect(calls).toEqual([])
})
