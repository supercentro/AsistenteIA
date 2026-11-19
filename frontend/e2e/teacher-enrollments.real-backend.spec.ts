import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

/**
 * Enrollment flow against a REAL stack (frontend 5173, backend 8000, database): a teacher creates a
 * subject, enrolls an existing student, removes the enrollment and enrolls again; the student's own
 * session confirms what they can see at each step. Skipped unless E2E_REAL_BACKEND=1 and the
 * accounts are given (teachers can only be created from the command line, see
 * docs/development_guide.md; the student registers through the interface or the API):
 *
 *   E2E_REAL_BACKEND=1 E2E_TEACHER_EMAIL=... E2E_TEACHER_PASSWORD=... \
 *     E2E_STUDENT_EMAIL=... E2E_STUDENT_PASSWORD=... \
 *     npm run test:e2e -- teacher-enrollments.real-backend
 *
 * Fictitious data only. The subject created by the run is deleted through the API at the end, with
 * its enrollments; the accounts stay (there is no account deletion endpoint yet).
 */
const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'
const enabled = process.env.E2E_REAL_BACKEND === '1'
const teacherEmail = process.env.E2E_TEACHER_EMAIL
const teacherPassword = process.env.E2E_TEACHER_PASSWORD
const studentEmail = process.env.E2E_STUDENT_EMAIL
const studentPassword = process.env.E2E_STUDENT_PASSWORD

test.describe('teacher enrollments on the real backend', () => {
  test.skip(
    !enabled || !teacherEmail || !teacherPassword || !studentEmail || !studentPassword,
    'set E2E_REAL_BACKEND=1 and the teacher and student e-mail and password to enable this suite',
  )

  test('enrolls a student, removes the enrollment and enrolls again', async ({ page, request }) => {
    const subjectName = `E2E Quimica ${randomUUID().slice(0, 8)}`
    async function token(email: string, password: string): Promise<string> {
      const login = await request.post(`${API}/auth/login`, { data: { email, password } })
      expect(login.ok()).toBe(true)
      return ((await login.json()) as { access_token: string }).access_token
    }
    async function studentSeesSubject(): Promise<boolean> {
      const headers = { Authorization: `Bearer ${await token(studentEmail!, studentPassword!)}` }
      const list = await request.get(`${API}/subjects`, { headers })
      return ((await list.json()) as { name: string }[]).some((item) => item.name === subjectName)
    }

    try {
      await page.goto('/login')
      await page.getByLabel('Correo electrónico').fill(teacherEmail as string)
      await page.getByLabel('Contraseña').fill(teacherPassword as string)
      await page.getByRole('button', { name: 'Entrar' }).click()
      await page.getByLabel('Nombre').fill(subjectName)
      await page.getByRole('button', { name: 'Crear asignatura' }).click()
      await page.getByRole('link', { name: subjectName }).click()
      await expect(page.getByRole('heading', { level: 1, name: subjectName })).toBeVisible()
      expect(await studentSeesSubject()).toBe(false)

      // An unregistered e-mail gets the neutral message and the page stays usable.
      const field = page.getByLabel('Correo electrónico del estudiante')
      await field.fill(`nadie-${randomUUID().slice(0, 6)}@example.com`)
      await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
      await expect(
        page.getByText('No se encontró un estudiante registrado con ese correo.'),
      ).toBeVisible()

      await field.fill(studentEmail as string)
      await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
      const list = page.getByRole('list', { name: 'Estudiantes inscritos en la asignatura' })
      await expect(
        list.getByText((studentEmail as string).toLowerCase(), { exact: true }),
      ).toBeVisible()
      expect(await studentSeesSubject()).toBe(true)

      await field.fill(studentEmail as string)
      await page.getByRole('button', { name: 'Inscribir estudiante' }).click()
      await expect(
        page.getByText('Ese estudiante ya está inscrito en la asignatura.'),
      ).toBeVisible()

      await page
        .getByRole('button', { name: `Quitar a ${(studentEmail as string).toLowerCase()}` })
        .click()
      await page.getByRole('button', { name: 'Quitar de la asignatura' }).click()
      await expect(
        page.getByText('Todavía no hay estudiantes inscritos', { exact: false }),
      ).toBeVisible()
      expect(await studentSeesSubject()).toBe(false)
    } finally {
      // Restore: the subject (and its enrollments) is removed through the API.
      const headers = { Authorization: `Bearer ${await token(teacherEmail!, teacherPassword!)}` }
      const subjects = (await (await request.get(`${API}/subjects`, { headers })).json()) as {
        id: string
        name: string
      }[]
      const mine = subjects.find((item) => item.name === subjectName)
      if (mine) {
        await request.delete(`${API}/subjects/${mine.id}`, { headers })
      }
    }
  })
})
