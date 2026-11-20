import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

/**
 * The student's chat against a REAL stack (frontend 5173, backend 8000, database, worker and the
 * real Gemini API, free tier). It makes ONE real model call per run, with fictitious material. It
 * is never run in CI. Skipped unless E2E_REAL_BACKEND=1 and the accounts are given (the student
 * must have accepted the privacy draft already; teachers are created from the command line, see
 * docs/development_guide.md):
 *
 *   E2E_REAL_BACKEND=1 E2E_TEACHER_EMAIL=... E2E_TEACHER_PASSWORD=... \
 *     E2E_STUDENT_EMAIL=... E2E_STUDENT_PASSWORD=... \
 *     npm run test:e2e -- student-chat.real-backend
 *
 * Setup and cleanup go through the API: a subject with a small fictitious text document is
 * created, the student is enrolled, and at the end the subject (with its documents, enrollments
 * and conversations) is deleted. The accounts stay (no account deletion endpoint yet).
 */
const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'
const enabled = process.env.E2E_REAL_BACKEND === '1'
const teacherEmail = process.env.E2E_TEACHER_EMAIL
const teacherPassword = process.env.E2E_TEACHER_PASSWORD
const studentEmail = process.env.E2E_STUDENT_EMAIL
const studentPassword = process.env.E2E_STUDENT_PASSWORD

test.describe('student chat on the real backend', () => {
  test.skip(
    !enabled || !teacherEmail || !teacherPassword || !studentEmail || !studentPassword,
    'set E2E_REAL_BACKEND=1 and the teacher and student e-mail and password to enable this suite',
  )

  test('asks one question, reads the answer and its sources, and deletes the conversation', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)
    const subjectName = `E2E Biologia ${randomUUID().slice(0, 8)}`
    async function token(email: string, password: string): Promise<string> {
      const login = await request.post(`${API}/auth/login`, { data: { email, password } })
      expect(login.ok()).toBe(true)
      return ((await login.json()) as { access_token: string }).access_token
    }
    const teacherHeaders = {
      Authorization: `Bearer ${await token(teacherEmail!, teacherPassword!)}`,
    }
    let subjectId = ''

    try {
      const created = await request.post(`${API}/subjects`, {
        headers: teacherHeaders,
        data: { name: subjectName },
      })
      expect(created.status()).toBe(201)
      subjectId = ((await created.json()) as { id: string }).id
      const upload = await request.post(`${API}/subjects/${subjectId}/documents`, {
        headers: teacherHeaders,
        multipart: {
          file: {
            name: 'mitocondrias.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from(
              'Las mitocondrias son los organulos que producen la energia de la celula en forma de ATP. '.repeat(
                6,
              ),
            ),
          },
        },
      })
      expect(upload.status()).toBe(202)
      await expect
        .poll(
          async () => {
            const list = await request.get(`${API}/subjects/${subjectId}/documents`, {
              headers: teacherHeaders,
            })
            return ((await list.json()) as { status: string }[])[0]?.status
          },
          { timeout: 90_000 },
        )
        .toBe('ready')
      const enrolled = await request.post(`${API}/subjects/${subjectId}/enrollments`, {
        headers: teacherHeaders,
        data: { student_email: studentEmail },
      })
      expect(enrolled.status()).toBe(201)

      await page.goto('/login')
      await page.getByLabel('Correo electrónico').fill(studentEmail as string)
      await page.getByLabel('Contraseña').fill(studentPassword as string)
      await page.getByRole('button', { name: 'Entrar' }).click()
      await page.getByRole('link', { name: `Preguntar sobre ${subjectName}` }).click()
      await expect(page.getByRole('heading', { level: 1, name: subjectName })).toBeVisible()

      await page
        .getByRole('textbox', { name: 'Pregunta' })
        .fill('Que son las mitocondrias segun el material?')
      await page.getByRole('button', { name: 'Enviar' }).click()

      // The model's answer is not predictable: only its shape is checked.
      const log = page.getByRole('log', { name: 'Mensajes de la conversación' })
      await expect(log.getByText('Asistente')).toBeVisible({ timeout: 60_000 })
      await expect(log.getByText('Material consultado')).toBeVisible()
      await expect(log.getByText('mitocondrias.txt').first()).toBeVisible()
      await expect(
        page.getByText('Fragmentos del material asociados a esta respuesta', { exact: false }),
      ).toBeVisible()

      await page.getByRole('button', { name: /^Eliminar la conversación/ }).click()
      await page.getByRole('button', { name: 'Eliminar conversación' }).click()
      await expect(
        page.getByText('Todavía no hay conversaciones en esta asignatura.'),
      ).toBeVisible()
    } finally {
      if (subjectId) {
        await request.delete(`${API}/subjects/${subjectId}`, { headers: teacherHeaders })
      }
    }
  })
})
