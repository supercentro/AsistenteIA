import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { API, documentItem, errorResponse, teacherUser } from '../tests/api'
import { ERROR_CODES, SUBJECT, SUBJECT_PAGE, serveSubject, noEnrollments } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.materials

afterEach(() => {
  vi.useRealTimers()
})

describe('Status of the documents', () => {
  it.each([
    ['pending', text.status.pending],
    ['processing', text.status.processing],
    ['ready', text.status.ready],
    ['failed', text.status.failed],
  ] as const)('shows the status %s as text', async (status, label) => {
    serveSubject([
      documentItem({ status, error_code: status === 'failed' ? 'CORRUPT_FILE' : null }),
    ])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText(label)).toBeVisible()
  })

  it.each(ERROR_CODES)(
    'explains a failed document with the code %s in its own words',
    async (code) => {
      serveSubject([
        documentItem({
          status: 'failed',
          error_code: code,
          error_message: 'RAW SERVER TEXT with parser details',
          chunks_count: 0,
        }),
      ])
      renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

      const row = await screen.findByRole('listitem')
      expect(within(row).getByText(text.failures[code])).toBeVisible()
      expect(screen.queryByText(/RAW SERVER TEXT/)).not.toBeInTheDocument()
    },
  )

  it('gives every code of the closed list a different explanation', () => {
    const sentences = ERROR_CODES.map((code) => text.failures[code])
    expect(new Set(sentences).size).toBe(ERROR_CODES.length)
    expect(sentences).not.toContain(text.failures.generic)
  })

  it('uses the generic explanation for a code outside the list', async () => {
    serveSubject([
      documentItem({
        status: 'failed',
        error_code: 'SOMETHING_NEW' as never,
        error_message: 'RAW SERVER TEXT',
        chunks_count: 0,
      }),
    ])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText(text.failures.generic)).toBeVisible()
    expect(screen.queryByText(/RAW SERVER TEXT/)).not.toBeInTheDocument()
  })
})

describe('Following the processing', () => {
  it('refreshes by itself while a document is pending and announces when it is ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'pending', chunks_count: 0 })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    expect(await screen.findByText(text.status.pending)).toBeVisible()

    state.documents = [documentItem({ status: 'ready', chunks_count: 7 })]
    await act(() => vi.advanceTimersByTimeAsync(3100))

    const row = await screen.findByRole('listitem')
    await waitFor(() => expect(within(row).getByText(text.status.ready)).toBeVisible())
    expect(within(row).getByText(text.documents.chunks(7))).toBeVisible()
    const announcement = screen.getByText(text.announce.ready('apuntes.pdf'))
    expect(announcement.closest('[aria-live="polite"]')).not.toBeNull()
  })

  it('announces a document that failed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'processing', chunks_count: 0 })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.processing)

    state.documents = [
      documentItem({ status: 'failed', error_code: 'EMBEDDING_FAILED', chunks_count: 0 }),
    ]
    await act(() => vi.advanceTimersByTimeAsync(3100))

    expect(await screen.findByText(text.announce.failed('apuntes.pdf'))).toBeInTheDocument()
  })

  it('stops asking once every document is final', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'pending', chunks_count: 0 })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.pending)

    state.documents = [documentItem({ status: 'ready' })]
    await act(() => vi.advanceTimersByTimeAsync(3100))
    await screen.findByText(text.status.ready)
    const callsWhenFinal = state.listCalls

    await act(() => vi.advanceTimersByTimeAsync(20000))

    expect(state.listCalls).toBe(callsWhenFinal)
  })

  it('never polls when everything is already final', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'ready' })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.ready)

    await act(() => vi.advanceTimersByTimeAsync(20000))

    expect(state.listCalls).toBe(1)
  })

  it('does not keep polling after the teacher leaves the page', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'pending', chunks_count: 0 })])
    const { unmountAndDetach } = renderApp({
      route: SUBJECT_PAGE,
      session: { user: teacherUser },
    })
    await screen.findByText(text.status.pending)
    unmountAndDetach()
    const callsWhenLeft = state.listCalls

    await act(() => vi.advanceTimersByTimeAsync(20000))

    expect(state.listCalls).toBe(callsWhenLeft)
  })

  it('does not poll while the tab is hidden', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const state = serveSubject([documentItem({ status: 'pending', chunks_count: 0 })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.pending)
    const callsBeforeHiding = state.listCalls

    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await act(() => vi.advanceTimersByTimeAsync(20000))
    const callsWhileHidden = state.listCalls
    visibility.mockRestore()

    expect(callsWhileHidden).toBe(callsBeforeHiding)
  })

  it('keeps the last list with a notice when an automatic refresh fails, and keeps trying', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let failing = false
    let calls = 0
    server.use(
      noEnrollments(),
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => {
        calls += 1
        return failing
          ? errorResponse(500, 'INTERNAL_ERROR')
          : HttpResponse.json([documentItem({ status: 'pending', chunks_count: 0 })])
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.pending)

    failing = true
    await act(() => vi.advanceTimersByTimeAsync(3100))
    expect(await screen.findByText(text.documents.pollFailed)).toBeVisible()
    expect(screen.getByText('apuntes.pdf')).toBeVisible()

    const callsAfterFailure = calls
    await act(() => vi.advanceTimersByTimeAsync(6200))
    expect(calls).toBeGreaterThan(callsAfterFailure)
  })

  it('ends the session when an automatic refresh answers 401', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let unauthorized = false
    server.use(
      noEnrollments(),
      http.get(`${API}/subjects/${SUBJECT.id}`, () => HttpResponse.json(SUBJECT)),
      http.get(`${API}/subjects/${SUBJECT.id}/documents`, () =>
        unauthorized
          ? errorResponse(401, 'UNAUTHORIZED')
          : HttpResponse.json([documentItem({ status: 'pending', chunks_count: 0 })]),
      ),
    )
    const { currentLocation } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.pending)

    unauthorized = true
    await act(() => vi.advanceTimersByTimeAsync(3100))

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })

  it('requests the list once when the teacher asks to refresh', async () => {
    const state = serveSubject([documentItem({ status: 'ready' })])
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.status.ready)
    const before = state.listCalls
    state.documents = [documentItem({ status: 'ready', filename: 'renovado.pdf' })]

    await userEvent.setup().click(screen.getByRole('button', { name: text.documents.refresh }))

    expect(await screen.findByText('renovado.pdf')).toBeVisible()
    expect(state.listCalls).toBe(before + 1)
  })
})

describe('Deleting a document', () => {
  function deleteHandler(onCall?: (id: string) => void, status = 204) {
    server.use(
      http.delete(`${API}/subjects/${SUBJECT.id}/documents/:id`, ({ params }) => {
        onCall?.(String(params.id))
        return status === 204
          ? new HttpResponse(null, { status: 204 })
          : errorResponse(status, status === 404 ? 'NOT_FOUND' : 'INTERNAL_ERROR')
      }),
    )
  }

  async function ask(filename = 'apuntes.pdf') {
    const user = userEvent.setup()
    const button = await screen.findByRole('button', { name: text.remove.action(filename) })
    await user.click(button)
    return { user, button }
  }

  it('asks for confirmation that says it is irreversible, and sends nothing yet', async () => {
    const state = serveSubject([documentItem()])
    let deletes = 0
    deleteHandler(() => (deletes += 1))
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    await ask()

    const panel = screen.getByRole('group', { name: text.remove.confirmQuestion('apuntes.pdf') })
    expect(within(panel).getByText(text.remove.confirmBody)).toBeVisible()
    expect(text.remove.confirmBody).toMatch(/no se puede deshacer/i)
    expect(text.remove.confirmBody).toMatch(/fragmentos/)
    await waitFor(() => expect(panel).toHaveFocus())
    expect(deletes).toBe(0)
    expect(state.documents).toHaveLength(1)
  })

  it('deletes after confirming and removes the row', async () => {
    const state = serveSubject([documentItem({ id: 'doc-1' })])
    const ids: string[] = []
    deleteHandler((id) => {
      ids.push(id)
      state.documents = []
    })
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user } = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    await waitFor(() => expect(screen.queryByText('apuntes.pdf')).not.toBeInTheDocument())
    expect(ids).toEqual(['doc-1'])
    expect(await screen.findByText(text.documents.empty)).toBeVisible()
  })

  it('cancelling sends nothing, keeps the document and returns the focus to the row', async () => {
    serveSubject([documentItem()])
    let deletes = 0
    deleteHandler(() => (deletes += 1))
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user } = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.cancel }))

    expect(deletes).toBe(0)
    expect(screen.getByText('apuntes.pdf')).toBeVisible()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: text.remove.action('apuntes.pdf') })
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('removes the row with a notice when the document no longer existed (404)', async () => {
    serveSubject([documentItem()])
    deleteHandler(undefined, 404)
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user } = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByText(text.remove.gone)).toBeVisible()
    expect(screen.queryByText('apuntes.pdf')).not.toBeInTheDocument()
  })

  it('keeps the document and shows an error when the deletion fails, and allows trying again', async () => {
    serveSubject([documentItem()])
    deleteHandler(undefined, 500)
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user } = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(screen.getByText('apuntes.pdf')).toBeVisible()
    expect(screen.getByRole('button', { name: text.remove.confirm })).toBeEnabled()
  })

  it.each(['pending', 'processing'] as const)(
    'asks the same confirmation for a %s document and sends the request',
    async (status) => {
      const state = serveSubject([documentItem({ status, chunks_count: 0 })])
      let deletes = 0
      deleteHandler(() => {
        deletes += 1
        state.documents = []
      })
      renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
      const { user } = await ask()

      await user.click(screen.getByRole('button', { name: text.remove.confirm }))

      await waitFor(() => expect(deletes).toBe(1))
    },
  )

  it('disables the confirm control while the deletion is pending', async () => {
    serveSubject([documentItem()])
    let deletes = 0
    server.use(
      http.delete(`${API}/subjects/${SUBJECT.id}/documents/:id`, async () => {
        deletes += 1
        await delay(150)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user } = await ask()
    const confirm = screen.getByRole('button', { name: text.remove.confirm })

    await user.click(confirm)
    await waitFor(() => expect(confirm).toBeDisabled())
    await user.click(confirm)

    await waitFor(() => expect(deletes).toBe(1))
  })
})
