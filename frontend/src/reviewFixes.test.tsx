import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { endSession, getSnapshot, startSession } from './lib/session'
import { strings } from './lib/strings.es'
import { API, TOKEN_VALUE, errorResponse, handlers, studentUser } from './tests/api'
import { server } from './tests/server'
import { renderApp } from './tests/utils'

describe('login when the profile request is answered with 401', () => {
  it('shows one generic error and leaves no session behind', async () => {
    server.use(
      handlers.login(),
      http.get(`${API}/users/me`, () => errorResponse(401, 'UNAUTHORIZED')),
    )
    const { currentLocation } = renderApp({ route: '/login' })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(strings.auth.login.email), 'ana@example.com')
    await user.type(screen.getByLabelText(strings.auth.login.password), 'a-very-long-password')

    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))

    const alerts = await screen.findAllByRole('alert')
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toHaveTextContent(strings.auth.errors.loginIncomplete)
    expect(getSnapshot()).toMatchObject({ token: null, user: null })
    expect(currentLocation()).toBe('/login')
  })
})

describe('a session that has a token but no profile yet', () => {
  it('shows the loading state on a protected route and requests nothing', async () => {
    let requests = 0
    server.use(
      http.get(`${API}/subjects`, () => {
        requests += 1
        return HttpResponse.json([])
      }),
    )
    startSession(TOKEN_VALUE, 3600)
    renderApp({ route: '/subjects' })

    expect(await screen.findByRole('status')).toHaveTextContent(strings.states.loading)
    expect(requests).toBe(0)
  })
})

describe('keyboard use', () => {
  it('signs in and signs out with the keyboard only, in a logical order', async () => {
    server.use(handlers.login(), handlers.me(studentUser), handlers.subjects([]))
    renderApp({ route: '/login' })
    const user = userEvent.setup()
    await screen.findByLabelText(strings.auth.login.email)

    await user.tab()
    expect(screen.getByLabelText(strings.auth.login.email)).toHaveFocus()
    await user.keyboard('ana@example.com')
    await user.tab()
    expect(screen.getByLabelText(strings.auth.login.password)).toHaveFocus()
    await user.keyboard('a-very-long-password')
    await user.tab()
    expect(screen.getByRole('button', { name: strings.auth.login.submit })).toHaveFocus()
    await user.keyboard('{Enter}')

    await screen.findByRole('heading', { level: 1, name: strings.subjects.titleStudent })
    await user.tab()
    expect(screen.getByRole('link', { name: strings.nav.subjects })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: strings.nav.signOut })).toHaveFocus()
    await user.keyboard('{Enter}')

    expect(
      await screen.findByRole('heading', { level: 1, name: strings.auth.login.title }),
    ).toBeInTheDocument()
  })

  it('registers with the keyboard only', async () => {
    server.use(handlers.register())
    const { currentLocation } = renderApp({ route: '/register' })
    const user = userEvent.setup()
    await screen.findByLabelText(strings.auth.register.name)

    await user.tab()
    await user.keyboard('Ana')
    await user.tab()
    await user.keyboard('ana@example.com')
    await user.tab()
    await user.keyboard('a-very-long-password')
    await user.tab()
    expect(screen.getByRole('button', { name: strings.auth.register.submit })).toHaveFocus()
    await user.keyboard('{Enter}')

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })
})

describe('what the next user is sent back to', () => {
  it('does not carry the previous user page after a deliberate sign-out', async () => {
    server.use(handlers.subjects([]))
    const { client } = renderApp({ route: '/subjects', session: { user: studentUser } })
    await screen.findByRole('heading', { level: 1, name: strings.subjects.titleStudent })

    await userEvent.click(screen.getByRole('button', { name: strings.nav.signOut }))

    await screen.findByRole('heading', { level: 1, name: strings.auth.login.title })
    expect(screen.getByTestId('location').getAttribute('data-from')).toBe('')
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })

  it('keeps the page when the session ended by itself', async () => {
    server.use(handlers.subjects([]))
    renderApp({ route: '/subjects', session: { user: studentUser } })
    await screen.findByRole('heading', { level: 1, name: strings.subjects.titleStudent })

    endSession('expired')

    await screen.findByRole('heading', { level: 1, name: strings.auth.login.title })
    expect(screen.getByTestId('location').getAttribute('data-from')).toBe('/subjects')
  })
})
