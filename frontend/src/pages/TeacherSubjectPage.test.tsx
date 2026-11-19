import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, documentItem, errorResponse, studentUser, subject, teacherUser } from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, serveSubject } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.materials

const TRICKY_NAME = `<img src=x onerror=alert(1)>${'n'.repeat(200)}.pdf`

describe('TeacherSubjectPage - the owner opens the page', () => {
  it('shows the subject and its documents in the order received', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () =>
        HttpResponse.json(subject({ name: 'Algebra lineal', description: 'Unidad 1' })),
      ),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        HttpResponse.json([
          documentItem({ id: 'a', filename: 'segundo.pdf', size_bytes: 2048, chunks_count: 12 }),
          documentItem({
            id: 'b',
            filename: 'primero.md',
            content_type: 'text/markdown',
            size_bytes: 10,
            status: 'pending',
            chunks_count: 0,
          }),
        ]),
      ),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { level: 1, name: 'Algebra lineal' })).toBeVisible()
    expect(screen.getByText('Unidad 1')).toBeVisible()
    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]!).getByText('segundo.pdf')).toBeVisible()
    expect(within(rows[0]!).getByText(text.documents.types['application/pdf']!)).toBeVisible()
    expect(within(rows[0]!).getByText(text.documents.size(2048))).toBeVisible()
    expect(within(rows[0]!).getByText(text.documents.chunks(12))).toBeVisible()
    expect(within(rows[0]!).getByText(text.status.ready)).toBeVisible()
    expect(within(rows[1]!).getByText('primero.md')).toBeVisible()
    expect(within(rows[1]!).getByText(text.status.pending)).toBeVisible()
    expect(screen.getByRole('link', { name: text.back })).toHaveAttribute('href', '/subjects')
  })

  it('shows file and subject names as text, wrapped, never as markup', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () =>
        HttpResponse.json(subject({ name: '<i>Algebra</i>' })),
      ),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        HttpResponse.json([documentItem({ filename: TRICKY_NAME })]),
      ),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { level: 1, name: '<i>Algebra</i>' })).toBeVisible()
    const row = await screen.findByRole('listitem')
    expect(row.querySelector('img')).toBeNull()
    expect(document.querySelector('main i')).toBeNull()
    expect(within(row).getByText(TRICKY_NAME).closest('p')?.className).toContain('break-words')
  })

  it('shows a loading state, then an empty state that points to the upload', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, async () => {
        await delay(150)
        return HttpResponse.json([])
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(text.documents.loading)).toBeVisible()
    expect(await screen.findByText(text.documents.empty)).toBeVisible()
    expect(screen.getByLabelText(text.upload.fileLabel)).toBeVisible()
  })

  it('shows an error with a retry control when the documents fail, and recovers', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => {
        calls += 1
        return calls <= 2
          ? errorResponse(500, 'INTERNAL_ERROR')
          : HttpResponse.json([documentItem()])
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(screen.queryByText('server side text')).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: strings.states.retry }))

    expect(await screen.findByText('apuntes.pdf')).toBeVisible()
  })

  it('has no serious accessibility violation with documents of every status', async () => {
    serveSubject([
      documentItem({ id: 'a', status: 'ready' }),
      documentItem({ id: 'b', status: 'pending', chunks_count: 0 }),
      documentItem({ id: 'c', status: 'failed', error_code: 'CORRUPT_FILE', chunks_count: 0 }),
    ])
    const { container } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findAllByRole('listitem')

    await expectNoSeriousA11yViolations(container)
  })
})

describe('TeacherSubjectPage - who may open it', () => {
  it('shows a not-found view without revealing whether the subject exists (404)', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => errorResponse(404, 'NOT_FOUND')),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => errorResponse(404, 'NOT_FOUND')),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: text.notFound.title })).toBeVisible()
    expect(screen.getByRole('link', { name: text.back })).toHaveAttribute('href', '/subjects')
    expect(screen.queryByLabelText(text.upload.fileLabel)).not.toBeInTheDocument()
  })

  it('shows the not-found view when only the document list answers 404', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => errorResponse(404, 'NOT_FOUND')),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: text.notFound.title })).toBeVisible()
  })

  it('shows the forbidden screen to a student and requests nothing about the subject', async () => {
    const state = serveSubject([documentItem()])
    renderApp({ route: SUBJECT_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
    expect(state.subjectCalls).toBe(0)
    expect(state.listCalls).toBe(0)
  })

  it('sends a visitor without a session to login', async () => {
    const state = serveSubject()
    const { currentLocation } = renderApp({ route: SUBJECT_PAGE })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(state.subjectCalls).toBe(0)
  })

  it('ends the session when the API answers 401, without flashing an error', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => errorResponse(401, 'UNAUTHORIZED')),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => errorResponse(401, 'UNAUTHORIZED')),
    )
    const { currentLocation } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.errors.byStatus.unauthorized)).not.toBeInTheDocument()
  })
})
