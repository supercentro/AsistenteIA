import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/types/api.generated.ts'
import { mockApi, signInHandlers, subject, teacher, type Handlers } from './support/mockApi.ts'

// Needs a dev server with both build flags set (playwright.config.ts sets them for the one it
// starts); a server running without them shows no link and the tests fail loudly.
type Ranking = components['schemas']['TopicRankingResponse']
type Topics = components['schemas']['DocumentTopicsResponse']
type Update = components['schemas']['DocumentTopicsUpdate']

const SUBJECT = subject({ name: 'Bases de Datos' })
const BASE = `/subjects/${SUBJECT.id}`
const DOCUMENT = '99999999-9999-4999-8999-999999999999'
const AXE = join(process.cwd(), 'node_modules', 'axe-core', 'axe.min.js')

const RANKING: Ranking = {
  window: { start: '2026-01-05', end: '2026-03-29', granularity: 'week', weeks: 12 },
  minimum_group: 5,
  topics_defined: 2,
  topics: [
    {
      topic_id: '11111111-1111-4111-8111-111111111111',
      title: 'Normalizacion de relaciones con un titulo bastante largo para pantallas angostas',
      document_id: DOCUMENT,
      filename: 'unidad-3-formas-normales-y-dependencias-funcionales.pdf',
      start_page: 1,
      end_page: 4,
      counted_since: '2026-01-05',
      answers: 18,
      also_in: ['repaso-general.pdf'],
    },
  ],
  documents_without_topics: [
    { document_id: DOCUMENT, filename: 'apunte-sin-marcadores.pdf', reason: 'not_defined' },
  ],
  restarted_documents: [],
}

function handlers(writes: Update[], current: { topics: Topics }): Handlers {
  return {
    ...signInHandlers(teacher, [SUBJECT]),
    [`GET ${BASE}/activity/topics`]: () => ({ status: 200, body: RANKING }),
    [`GET ${BASE}/documents/${DOCUMENT}/topics`]: () => ({ status: 200, body: current.topics }),
    [`PUT ${BASE}/documents/${DOCUMENT}/topics`]: (request) => {
      const body = request.postDataJSON() as Update
      writes.push(body)
      current.topics = {
        ...current.topics,
        revision: body.revision + 1,
        source: 'teacher',
        topics: body.topics,
      }
      return { status: 200, body: current.topics }
    },
  }
}

function emptyDocument(): Topics {
  return {
    document_id: DOCUMENT,
    filename: 'apunte-sin-marcadores.pdf',
    editable: true,
    reason: null,
    last_page: 12,
    revision: 0,
    source: null,
    counting_from: null,
    topics: [],
  }
}

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('tomas@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
}

async function goInApp(page: Page, path: string) {
  await page.evaluate((target) => {
    window.history.pushState({}, '', target)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, path)
}

/** Serious and critical violations, colour contrast included (a real browser renders it). */
async function violations(page: Page): Promise<string[]> {
  await page.addScriptTag({ path: AXE })
  return page.evaluate(async () => {
    const axe = (
      window as unknown as {
        axe: { run: () => Promise<{ violations: { id: string; impact: string }[] }> }
      }
    ).axe
    const results = await axe.run()
    return results.violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => v.id)
  })
}

const noHorizontalScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)

test('the ranking reads at 320 px, with bars, a table and no accessibility violation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await mockApi(page, handlers([], { topics: emptyDocument() }))
  await signIn(page)

  await goInApp(page, `${BASE}/activity/topics`)

  await expect(page.getByRole('heading', { level: 1, name: 'Temas más consultados' })).toBeVisible()
  const table = page.getByRole('table', { name: 'Temas y respuestas que citaron su material' })
  await expect(table.getByRole('row')).toHaveCount(2)
  await expect(page.locator('[data-bar]')).toHaveCount(1)
  expect(await noHorizontalScroll(page)).toBe(true)
  expect(await violations(page)).toEqual([])
})

test('a teacher defines the topics of a file without bookmarks with the keyboard', async ({
  page,
}) => {
  const writes: Update[] = []
  await page.setViewportSize({ width: 320, height: 800 })
  await mockApi(page, handlers(writes, { topics: emptyDocument() }))
  await signIn(page)
  await goInApp(page, `${BASE}/activity/topics`)

  await page.getByRole('link', { name: 'Definir temas de apunte-sin-marcadores.pdf' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { level: 1, name: 'Temas del documento' })).toBeVisible()
  await page.getByRole('button', { name: 'Agregar tema' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Título del tema 1')).toBeFocused()
  await page.keyboard.type('Dependencias funcionales')
  await page.keyboard.press('Tab')
  await page.keyboard.type('2')
  await page.keyboard.press('Tab')
  await page.keyboard.type('5')
  expect(await violations(page)).toEqual([])
  await page.keyboard.press('Enter')

  await expect(page.getByText('Temas guardados.')).toBeVisible()
  expect(writes).toEqual([
    { revision: 0, topics: [{ title: 'Dependencias funcionales', start_page: 2, end_page: 5 }] },
  ])
  expect(await noHorizontalScroll(page)).toBe(true)

  // Changing a page now asks for confirmation before anything is sent.
  await page.getByLabel('Hasta la página 1').fill('4')
  await page.getByRole('button', { name: 'Guardar temas' }).click()
  await expect(page.getByRole('group', { name: '¿Guardar el cambio de páginas?' })).toBeFocused()
  expect(writes).toHaveLength(1)
  expect(await violations(page)).toEqual([])

  // Cancelling gives the focus back; a confirmed save leaves it on the heading.
  await page.getByRole('button', { name: 'Cancelar' }).click()
  await expect(page.getByRole('button', { name: 'Guardar temas' })).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: 'Guardar el cambio' }).click()
  await expect.poll(() => writes.length).toBe(2)
  await expect(page.getByRole('heading', { level: 1, name: 'Temas del documento' })).toBeFocused()
})
