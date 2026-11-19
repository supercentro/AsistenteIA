import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/types/api.generated.ts'
import { errorBody, mockApi, signInHandlers, subject, teacher } from './support/mockApi.ts'

type Enrollment = components['schemas']['Enrollment']

// Spanish copy lives in src/lib/strings.es.ts; the texts used here are the visible labels.
const SUBJECT = subject({ name: 'Quimica General' })
const BASE = `/subjects/${SUBJECT.id}`

function enrollment(email: string, id: string): Enrollment {
  return {
    id: `e-${id}`,
    subject_id: SUBJECT.id,
    student_id: `s-${id}`,
    student_email: email,
    created_at: '2026-11-19T10:00:00Z',
  }
}

async function openSubjectPage(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('tomas@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.getByRole('link', { name: 'Quimica General' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Quimica General' })).toBeVisible()
}

function subjectHandlers(enrollments: () => Enrollment[]) {
  return {
    ...signInHandlers(teacher, [SUBJECT]),
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    [`GET ${BASE}/documents`]: () => ({ status: 200, body: [] }),
    [`GET ${BASE}/enrollments`]: () => ({ status: 200, body: enrollments() }),
  }
}

test('a teacher enrolls a student, sees it listed and removes it with the keyboard', async ({
  page,
}) => {
  let enrolled: Enrollment[] = []
  const posted: unknown[] = []
  await mockApi(page, {
    ...subjectHandlers(() => enrolled),
    [`POST ${BASE}/enrollments`]: (request) => {
      const body = request.postDataJSON() as { student_email: string }
      posted.push(body)
      const created = enrollment(body.student_email.toLowerCase(), '1')
      enrolled = [...enrolled, created]
      return { status: 201, body: created }
    },
    [`DELETE ${BASE}/enrollments/s-1`]: () => {
      enrolled = []
      return { status: 204 }
    },
  })

  await openSubjectPage(page)
  await expect(
    page.getByText('Todavía no hay estudiantes inscritos', { exact: false }),
  ).toBeVisible()
  await page.getByLabel('Correo electrónico del estudiante').fill('Ana@Example.com')
  await page.getByRole('button', { name: 'Inscribir estudiante' }).click()

  const list = page.getByRole('list', { name: 'Estudiantes inscritos en la asignatura' })
  await expect(list.getByText('ana@example.com', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Correo electrónico del estudiante')).toHaveValue('')
  expect(posted).toEqual([{ student_email: 'Ana@Example.com' }])

  // Keyboard only: focus the remove button, open the confirmation, move to confirm, press Enter.
  await page.getByRole('button', { name: 'Quitar a ana@example.com' }).focus()
  await page.keyboard.press('Enter')
  const group = page.getByRole('group', { name: '¿Quitar a ana@example.com de la asignatura?' })
  await expect(group).toBeFocused()
  await expect(group.getByText('No se borra nada', { exact: false })).toBeVisible()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')

  await expect(
    page.getByText('Todavía no hay estudiantes inscritos', { exact: false }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Estudiantes inscritos' })).toBeFocused()
})

test('the failures of enrolling are explained without revealing anything', async ({ page }) => {
  await mockApi(page, {
    ...subjectHandlers(() => []),
    [`POST ${BASE}/enrollments`]: (request) => {
      const email = (request.postDataJSON() as { student_email: string }).student_email
      if (email.startsWith('repetido')) {
        return { status: 409, body: errorBody('CONFLICT') }
      }
      return { status: 404, body: errorBody('NOT_FOUND') }
    },
  })

  await openSubjectPage(page)
  const field = page.getByLabel('Correo electrónico del estudiante')
  await field.fill('nadie@example.com')
  await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
  await expect(
    page.getByText('No se encontró un estudiante registrado con ese correo.'),
  ).toBeVisible()
  await expect(field).toHaveValue('nadie@example.com')
  await expect(page.getByText('server side text')).toHaveCount(0)

  await field.fill('repetido@example.com')
  await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
  await expect(page.getByText('Ese estudiante ya está inscrito en la asignatura.')).toBeVisible()

  await field.fill('sin-arroba')
  await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
  await expect(page.getByText('Ingrese un correo electrónico válido.')).toBeVisible()
})

test('the enrollment section has no horizontal scrolling at 320 px', async ({ page }) => {
  await mockApi(
    page,
    subjectHandlers(() => [enrollment(`${'larguisimo'.repeat(12)}@example.com`, '9')]),
  )
  await page.setViewportSize({ width: 320, height: 700 })

  await openSubjectPage(page)
  await expect(page.getByText('larguisimo', { exact: false }).first()).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)
})
