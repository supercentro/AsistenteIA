import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/types/api.generated.ts'
import { errorBody, mockApi, signInHandlers, subject, teacher } from './support/mockApi.ts'

type Document = components['schemas']['Document']

// Spanish copy lives in src/lib/strings.es.ts; the texts used here are the visible labels.
const SUBJECT = subject({ name: 'Fisica General' })
const BASE = `/subjects/${SUBJECT.id}`

function docItem(overrides: Partial<Document> = {}): Document {
  return {
    id: '44444444-4444-4444-8444-444444444444',
    subject_id: SUBJECT.id,
    filename: 'mecanica.txt',
    content_type: 'text/plain',
    size_bytes: 24,
    status: 'pending',
    error_code: null,
    error_message: null,
    chunks_count: 0,
    created_at: '2026-11-18T10:00:00Z',
    ...overrides,
  }
}

async function signInAsTeacher(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('tomas@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
}

test('a teacher creates a subject, uploads a file, sees it become ready and deletes it', async ({
  page,
}) => {
  const subjects = [] as ReturnType<typeof subject>[]
  let documents: Document[] = []
  let listCalls = 0
  const created: unknown[] = []
  await mockApi(page, {
    ...signInHandlers(teacher),
    'GET /subjects': () => ({ status: 200, body: subjects }),
    'POST /subjects': (request) => {
      created.push(request.postDataJSON())
      subjects.push(SUBJECT)
      return { status: 201, body: SUBJECT }
    },
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    [`GET ${BASE}/documents`]: () => {
      listCalls += 1
      // The worker finishes between two polls: the second answer already says "ready".
      if (listCalls >= 2) {
        documents = documents.map((item) => ({ ...item, status: 'ready', chunks_count: 3 }))
      }
      return { status: 200, body: documents }
    },
    [`POST ${BASE}/documents`]: () => {
      documents = [docItem()]
      return { status: 202, body: documents[0] }
    },
    [`DELETE ${BASE}/documents/${docItem().id}`]: () => {
      documents = []
      return { status: 204 }
    },
  })

  await signInAsTeacher(page)
  await expect(
    page.getByRole('heading', { level: 1, name: 'Asignaturas a mi cargo' }),
  ).toBeVisible()
  await page.getByLabel('Nombre').fill('Fisica General')
  await page.getByRole('button', { name: 'Crear asignatura' }).click()
  await page.getByRole('link', { name: 'Fisica General' }).click()

  await expect(page).toHaveURL(new RegExp(`${BASE}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Fisica General' })).toBeVisible()
  await expect(page.getByText(/documentos ficticios/)).toBeVisible()
  await page.getByLabel('Archivo').setInputFiles({
    name: 'mecanica.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('La mecanica estudia el movimiento.'),
  })
  await page.getByRole('button', { name: 'Subir documento' }).click()

  const row = page.getByRole('listitem').filter({ hasText: 'mecanica.txt' })
  await expect(row.getByText('Pendiente')).toBeVisible()
  await expect(row.getByText('Listo')).toBeVisible({ timeout: 10_000 })
  await expect(row.getByText('3 fragmentos')).toBeVisible()

  await row.getByRole('button', { name: 'Eliminar mecanica.txt' }).click()
  await expect(page.getByText('No se puede deshacer', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Eliminar definitivamente' }).click()
  await expect(
    page.getByText('Todavía no se subió ningún documento', { exact: false }),
  ).toBeVisible()
  expect(created).toEqual([{ name: 'Fisica General' }])
})

test('every failure of the upload and a failed document are explained in Spanish', async ({
  page,
}) => {
  await mockApi(page, {
    ...signInHandlers(teacher, [SUBJECT]),
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    [`GET ${BASE}/documents`]: () => ({
      status: 200,
      body: [
        docItem({
          status: 'failed',
          filename: 'escaneado.pdf',
          content_type: 'application/pdf',
          error_code: 'NO_EXTRACTABLE_TEXT',
          error_message: 'raw parser text that must never be shown',
        }),
      ],
    }),
    [`POST ${BASE}/documents`]: () => ({ status: 415, body: errorBody('UNSUPPORTED_MEDIA_TYPE') }),
  })

  await signInAsTeacher(page)
  await page.getByRole('link', { name: 'Fisica General' }).click()
  await expect(
    page.getByText('No se pudo extraer texto del archivo', { exact: false }),
  ).toBeVisible()
  await expect(page.getByText('raw parser text')).toHaveCount(0)

  await page.getByLabel('Archivo').setInputFiles({
    name: 'programa.exe',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('MZ'),
  })
  await page.getByRole('button', { name: 'Subir documento' }).click()
  await expect(page.getByText('El tipo de archivo no es admitido', { exact: false })).toBeVisible()
  await expect(page.getByText('server side text')).toHaveCount(0)
})

test('the subject page has no horizontal scrolling at 320 px and works with the keyboard', async ({
  page,
}) => {
  await mockApi(page, {
    ...signInHandlers(teacher, [SUBJECT]),
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    [`GET ${BASE}/documents`]: () => ({
      status: 200,
      body: [
        docItem({
          status: 'ready',
          filename: `${'nombre-muy-largo-'.repeat(8)}.pdf`,
          content_type: 'application/pdf',
          chunks_count: 5,
        }),
      ],
    }),
  })
  await page.setViewportSize({ width: 320, height: 700 })

  await signInAsTeacher(page)
  await page.getByRole('link', { name: 'Fisica General' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Fisica General' })).toBeVisible()
  await expect(page.getByText('nombre-muy-largo-', { exact: false }).first()).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)

  await page.getByLabel('Archivo').focus()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Subir documento' })).toBeFocused()
})

test('a student cannot open the subject page of a teacher', async ({ page }) => {
  await mockApi(page, {
    ...signInHandlers(
      {
        ...teacher,
        role: 'student',
        consent_version: '2026-10-v1',
        consent_accepted_at: '2026-11-17T10:00:00Z',
      },
      [],
    ),
  })
  await signInAsTeacher(page)
  await expect(page.getByRole('heading', { level: 1, name: 'Mis asignaturas' })).toBeVisible()
  // The session lives in memory only, so a reload would end it: navigate inside the application.
  await page.evaluate((path) => {
    window.history.pushState({}, '', path)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, BASE)

  await expect(page.getByRole('heading', { name: 'Acceso no permitido' })).toBeVisible()
})
