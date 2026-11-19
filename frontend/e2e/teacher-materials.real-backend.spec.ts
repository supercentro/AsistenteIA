import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

/**
 * Teacher flow against a REAL stack (frontend 5173, backend 8000, database and worker): creates a
 * subject, uploads a small text document, waits until the worker has processed it, deletes it.
 * Skipped unless E2E_REAL_BACKEND=1 and a teacher test account is given (teachers can only be
 * created from the command line, see docs/development_guide.md):
 *
 *   E2E_REAL_BACKEND=1 E2E_TEACHER_EMAIL=... E2E_TEACHER_PASSWORD=... \
 *     npm run test:e2e -- teacher-materials.real-backend
 *
 * Fictitious data only. The subject created by the run is deleted through the API at the end, with
 * its documents; the teacher account itself stays (there is no account deletion endpoint yet).
 */
const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'
const enabled = process.env.E2E_REAL_BACKEND === '1'
const email = process.env.E2E_TEACHER_EMAIL
const password = process.env.E2E_TEACHER_PASSWORD

test.describe('teacher materials on the real backend', () => {
  test.skip(
    !enabled || !email || !password,
    'set E2E_REAL_BACKEND=1, E2E_TEACHER_EMAIL and E2E_TEACHER_PASSWORD to enable this suite',
  )

  test('creates a subject, uploads a document, waits for ready and deletes it', async ({
    page,
    request,
  }) => {
    const subjectName = `E2E Fisica ${randomUUID().slice(0, 8)}`
    try {
      await page.goto('/login')
      await page.getByLabel('Correo electrónico').fill(email as string)
      await page.getByLabel('Contraseña').fill(password as string)
      await page.getByRole('button', { name: 'Entrar' }).click()
      await expect(
        page.getByRole('heading', { level: 1, name: 'Asignaturas a mi cargo' }),
      ).toBeVisible()

      await page.getByLabel('Nombre').fill(subjectName)
      await page.getByLabel('Descripción (opcional)').fill('Material ficticio de prueba')
      await page.getByRole('button', { name: 'Crear asignatura' }).click()
      await page.getByRole('link', { name: subjectName }).click()
      await expect(page.getByRole('heading', { level: 1, name: subjectName })).toBeVisible()

      await page.getByLabel('Archivo').setInputFiles({
        name: 'mecanica.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('La mecanica estudia el movimiento y las fuerzas. '.repeat(20)),
      })
      await page.getByRole('button', { name: 'Subir documento' }).click()

      const row = page.getByRole('listitem').filter({ hasText: 'mecanica.txt' })
      await expect(row).toBeVisible()
      await expect(row.getByText('Listo')).toBeVisible({ timeout: 120_000 })
      await expect(row.getByText(/\d+ fragmentos?/)).toBeVisible()

      await row.getByRole('button', { name: 'Eliminar mecanica.txt' }).click()
      await page.getByRole('button', { name: 'Eliminar definitivamente' }).click()
      await expect(
        page.getByText('Todavía no se subió ningún documento', { exact: false }),
      ).toBeVisible()
    } finally {
      // Restore: the subject (and any document left) is removed through the API.
      const login = await request.post(`${API}/auth/login`, {
        data: { email, password },
      })
      if (login.ok()) {
        const { access_token: token } = (await login.json()) as { access_token: string }
        const headers = { Authorization: `Bearer ${token}` }
        const list = await request.get(`${API}/subjects`, { headers })
        const subjects = (await list.json()) as { id: string; name: string }[]
        const mine = subjects.find((item) => item.name === subjectName)
        if (mine) {
          await request.delete(`${API}/subjects/${mine.id}`, { headers })
        }
      }
    }
  })
})
