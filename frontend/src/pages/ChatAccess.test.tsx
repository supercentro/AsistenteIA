import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import {
  API,
  errorResponse,
  handlers,
  outdatedStudent,
  studentUser,
  teacherUser,
  unconsentedStudent,
} from '../tests/api'
import { CHAT_PAGE, CHAT_SUBJECT, serveChat } from '../tests/chat'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.chat

describe('ChatPage - who may open it', () => {
  it('shows the subject, the conversations, the box and the notice to an enrolled student', async () => {
    serveChat()
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { level: 1, name: 'Biologia' })).toBeVisible()
    expect(await screen.findByText(text.conversations.empty)).toBeVisible()
    expect(screen.getByRole('textbox', { name: text.box.label })).toBeVisible()
    expect(screen.getByText(/Gemini \(Google\)/)).toBeVisible()
    expect(screen.getByText(/datos ficticios/)).toBeVisible()
  })

  it('shows a loading state while the subject and the conversations are requested', async () => {
    serveChat()
    server.use(
      http.get(`${API}/conversations`, async () => {
        await delay(150)
        return HttpResponse.json([])
      }),
    )
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    expect(await screen.findByText(text.conversations.loading)).toBeVisible()
    expect(await screen.findByText(text.conversations.empty)).toBeVisible()
  })

  it('gives a teacher the forbidden screen and sends no chat or conversation request', async () => {
    const state = serveChat()
    renderApp({ route: CHAT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
    expect(state.subjectCalls).toBe(0)
    expect(state.listCalls).toBe(0)
  })

  it('sends a visitor without a session to login', async () => {
    const state = serveChat()
    const { currentLocation } = renderApp({ route: CHAT_PAGE })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(state.subjectCalls).toBe(0)
  })

  it.each([
    ['without consent', unconsentedStudent],
    ['with an outdated consent', outdatedStudent],
  ])('holds a student %s at the consent screen first', async (_name, user) => {
    const state = serveChat()
    server.use(handlers.me(user))
    const { currentLocation } = renderApp({ route: CHAT_PAGE, session: { user } })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(state.subjectCalls).toBe(0)
  })

  it.each([
    [403, 'FORBIDDEN'],
    [404, 'NOT_FOUND'],
  ])('says the subject is not available when the subject answers %s', async (status, code) => {
    serveChat()
    server.use(http.get(`${API}/subjects/${CHAT_SUBJECT.id}`, () => errorResponse(status, code)))
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { name: text.unavailable.title })).toBeVisible()
    expect(screen.getByRole('link', { name: text.back })).toHaveAttribute('href', '/subjects')
    expect(screen.queryByRole('textbox', { name: text.box.label })).not.toBeInTheDocument()
  })

  it.each([
    [403, 'FORBIDDEN'],
    [404, 'NOT_FOUND'],
  ])('says the subject is not available when the conversations answer %s', async (status, code) => {
    serveChat()
    server.use(http.get(`${API}/conversations`, () => errorResponse(status, code)))
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { name: text.unavailable.title })).toBeVisible()
  })

  it('shows an error with a retry control when the conversations fail, and recovers', async () => {
    serveChat()
    let calls = 0
    server.use(
      http.get(`${API}/conversations`, () => {
        calls += 1
        return calls <= 2 ? errorResponse(500, 'INTERNAL_ERROR') : HttpResponse.json([])
      }),
    )
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    await userEvent.setup().click(screen.getByRole('button', { name: strings.states.retry }))

    expect(await screen.findByText(text.conversations.empty)).toBeVisible()
  })

  it('ends the session when the conversations answer 401, without flashing an error', async () => {
    serveChat()
    server.use(http.get(`${API}/conversations`, () => errorResponse(401, 'UNAUTHORIZED')))
    const { currentLocation } = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.errors.byStatus.unauthorized)).not.toBeInTheDocument()
  })

  it('opens the policy draft in a new tab without ending the session', async () => {
    serveChat()
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })

    const link = await screen.findByRole('link', { name: text.policyLink })

    expect(link).toHaveAttribute('href', '/privacy')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('has no serious accessibility violation', async () => {
    serveChat()
    const { container } = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
    await screen.findByText(text.conversations.empty)

    await expectNoSeriousA11yViolations(container)
  })
})
