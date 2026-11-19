import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import { documentService } from '../services/documentService'
import { API, documentItem, errorResponse, subject, teacherUser } from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, serveSubject, noEnrollments } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp, renderWithProviders } from '../tests/utils'
import TeacherSubjectPage from './TeacherSubjectPage'

const text = strings.materials

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function file(name = 'notas.txt') {
  return new File(['contenido'], name, { type: 'text/plain' })
}

describe('Review: a 503 tells how long to wait when the API says so', () => {
  it('adds the wait to the queue-full message of an upload', async () => {
    serveSubject()
    server.use(
      http.post(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        errorResponse(503, 'INGESTION_QUEUE_FULL', { 'Retry-After': '9' }),
      ),
    )
    const user = userEvent.setup({ applyAccept: false })
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await user.upload(await screen.findByLabelText(text.upload.fileLabel), file())
    await user.click(screen.getByRole('button', { name: text.upload.submit }))

    expect(
      await screen.findByText(
        `${strings.errors.byCode.INGESTION_QUEUE_FULL} ${strings.errors.waitSeconds(9)}`,
      ),
    ).toBeVisible()
  })
})

describe('Review: a slow upload', () => {
  it('uses a longer time limit than ordinary requests', async () => {
    const { apiClient } = await import('../lib/apiClient')
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: documentItem() })

    await documentService.upload(SUBJECT.id, file())

    expect(post.mock.calls[0]?.[2]).toMatchObject({ timeout: 120_000 })
  })

  it('tells the teacher to check the list before trying again when the upload times out', async () => {
    serveSubject()
    vi.spyOn(documentService, 'upload').mockRejectedValue(new ApiError({ kind: 'timeout' }))
    const user = userEvent.setup({ applyAccept: false })
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await user.upload(await screen.findByLabelText(text.upload.fileLabel), file())
    await user.click(screen.getByRole('button', { name: text.upload.submit }))

    expect(await screen.findByText(text.upload.timeout)).toBeVisible()
    expect(text.upload.timeout).toMatch(/lista/)
  })
})

describe('Review: an answer that was already on its way does not undo a change', () => {
  it('keeps a deleted document deleted when an older refresh answers afterwards', async () => {
    let calls = 0
    const gone = new Set<string>()
    server.use(
      noEnrollments(),
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, async () => {
        calls += 1
        if (calls > 1) {
          await delay(300)
        }
        return HttpResponse.json(gone.has('a') ? [] : [documentItem({ id: 'a' })])
      }),
      http.delete(`${API}/subjects/${SUBJECT.id}/documents/:id`, () => {
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText('apuntes.pdf')

    await user.click(screen.getByRole('button', { name: text.documents.refresh }))
    await user.click(screen.getByRole('button', { name: text.remove.action('apuntes.pdf') }))
    await user.click(screen.getByRole('button', { name: text.remove.confirm }))
    await waitFor(() => expect(screen.queryByText('apuntes.pdf')).not.toBeInTheDocument())
    await act(() => new Promise((resolve) => setTimeout(resolve, 500)))

    expect(screen.queryByText('apuntes.pdf')).not.toBeInTheDocument()
  })

  it('keeps an uploaded document shown when an older refresh answers afterwards', async () => {
    let calls = 0
    server.use(
      noEnrollments(),
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, async () => {
        calls += 1
        if (calls > 1) {
          await delay(300)
        }
        return HttpResponse.json([documentItem({ id: 'old', filename: 'viejo.pdf' })])
      }),
      http.post(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        HttpResponse.json(documentItem({ id: 'new', filename: 'nuevo.pdf', status: 'ready' }), {
          status: 202,
        }),
      ),
    )
    const user = userEvent.setup({ applyAccept: false })
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText('viejo.pdf')

    await user.click(screen.getByRole('button', { name: text.documents.refresh }))
    await user.upload(screen.getByLabelText(text.upload.fileLabel), file('nuevo.pdf'))
    await user.click(screen.getByRole('button', { name: text.upload.submit }))
    await screen.findByText('nuevo.pdf')
    await act(() => new Promise((resolve) => setTimeout(resolve, 500)))

    expect(screen.getByText('nuevo.pdf')).toBeVisible()
  })
})

describe('Review: names are isolated from the text around them', () => {
  it('wraps a file name in a bidirectional isolate', async () => {
    const name = `fdp.‮txt`
    serveSubject([documentItem({ filename: name })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    const row = await screen.findByRole('listitem')
    const isolate = row.querySelector('bdi')
    expect(isolate).not.toBeNull()
    expect(isolate?.textContent).toBe(name)
  })
})

function Jump({ to }: { to: string }) {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate(to)}>
      jump
    </button>
  )
}

describe('Review: moving to another subject does not keep the previous refusal', () => {
  it('shows the next subject after the previous one answered 404 to an upload', async () => {
    const other = subject({ id: '66666666-6666-4666-8666-666666666666', name: 'Quimica' })
    serveSubject()
    server.use(
      http.post(`${API}/subjects/${SUBJECT.id}/documents`, () => errorResponse(404, 'NOT_FOUND')),
      noEnrollments(),
      http.get(`${API}/subjects/${other.id}`, () => HttpResponse.json(other)),
      http.get(`${API}/subjects/${other.id}/documents`, () => HttpResponse.json([])),
    )
    renderWithProviders(
      <>
        <Jump to={`/subjects/${other.id}`} />
        <Routes>
          <Route path="/subjects/:subjectId" element={<TeacherSubjectPage />} />
        </Routes>
      </>,
      { route: SUBJECT_PAGE, session: { user: teacherUser } },
    )
    const user = userEvent.setup({ applyAccept: false })
    await user.upload(await screen.findByLabelText(text.upload.fileLabel), file())
    await user.click(screen.getByRole('button', { name: text.upload.submit }))
    expect(await screen.findByRole('heading', { name: text.notFound.title })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'jump' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Quimica' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: text.notFound.title })).not.toBeInTheDocument()
  })
})

describe('Review: a failed refresh of the subject keeps the page', () => {
  it('keeps the upload form and the documents when the subject cannot be refreshed', async () => {
    let subjectCalls = 0
    server.use(
      noEnrollments(),
      http.get(`${API}/subjects/${SUBJECT.id}`, () => {
        subjectCalls += 1
        return subjectCalls === 1
          ? HttpResponse.json(SUBJECT)
          : errorResponse(500, 'INTERNAL_ERROR')
      }),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        HttpResponse.json([documentItem()]),
      ),
    )
    const { client } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText('apuntes.pdf')

    await act(() => client.invalidateQueries({ queryKey: ['subject'] }))
    await waitFor(() => expect(subjectCalls).toBeGreaterThan(1))

    expect(screen.getByLabelText(text.upload.fileLabel)).toBeVisible()
    expect(screen.getByText('apuntes.pdf')).toBeVisible()
  })
})

describe('Review: announcements, focus and the deletions of other rows', () => {
  it('announces every document that finished in the same refresh', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([
      documentItem({ id: 'a', filename: 'uno.pdf', status: 'pending', chunks_count: 0 }),
      documentItem({ id: 'b', filename: 'dos.pdf', status: 'processing', chunks_count: 0 }),
    ])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText('uno.pdf')

    state.documents = [
      documentItem({ id: 'a', filename: 'uno.pdf', status: 'ready' }),
      documentItem({ id: 'b', filename: 'dos.pdf', status: 'ready' }),
    ]
    await act(() => vi.advanceTimersByTimeAsync(3100))

    const live = (
      await screen.findByText(text.announce.ready('uno.pdf'), { exact: false })
    ).closest('[aria-live="polite"]') as HTMLElement
    expect(live).toHaveTextContent(text.announce.ready('uno.pdf'))
    expect(live).toHaveTextContent(text.announce.ready('dos.pdf'))
  })

  it('moves the focus to the documents heading after a deletion', async () => {
    const state = serveSubject([documentItem({ id: 'a' })])
    server.use(
      http.delete(`${API}/subjects/${SUBJECT.id}/documents/:id`, () => {
        state.documents = []
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await user.click(await screen.findByRole('button', { name: text.remove.action('apuntes.pdf') }))

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    const heading = await screen.findByRole('heading', { name: text.documents.heading })
    await waitFor(() => expect(heading).toHaveFocus())
  })

  it('returns the focus to the upload button when the upload ends', async () => {
    serveSubject()
    server.use(
      http.post(`${API}/subjects/${SUBJECT.id}/documents`, async () => {
        await delay(100)
        return errorResponse(415, 'UNSUPPORTED_MEDIA_TYPE')
      }),
    )
    const user = userEvent.setup({ applyAccept: false })
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await user.upload(await screen.findByLabelText(text.upload.fileLabel), file())
    const submit = screen.getByRole('button', { name: text.upload.submit })

    await user.click(submit)

    await screen.findByText(strings.errors.byCode.UNSUPPORTED_MEDIA_TYPE)
    await waitFor(() => expect(submit).toHaveFocus())
  })

  it('disables every confirm control while one deletion is in flight', async () => {
    serveSubject([
      documentItem({ id: 'a', filename: 'uno.pdf' }),
      documentItem({ id: 'b', filename: 'dos.pdf' }),
    ])
    server.use(
      http.delete(`${API}/subjects/${SUBJECT.id}/documents/:id`, async () => {
        await delay(300)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await user.click(await screen.findByRole('button', { name: text.remove.action('uno.pdf') }))
    await user.click(screen.getByRole('button', { name: text.remove.action('dos.pdf') }))
    const confirms = screen.getAllByRole('button', { name: text.remove.confirm })
    expect(confirms).toHaveLength(2)

    await user.click(confirms[0] as HTMLElement)

    await waitFor(() => expect(confirms[1]).toBeDisabled())
  })

  it('polls again when the tab becomes visible', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'pending', chunks_count: 0 })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.pending)

    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await act(() => vi.advanceTimersByTimeAsync(10000))
    const whileHidden = state.listCalls
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await act(() => vi.advanceTimersByTimeAsync(10000))

    expect(state.listCalls).toBeGreaterThan(whileHidden)
  })
})
