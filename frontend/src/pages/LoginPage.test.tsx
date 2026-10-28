import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { endSession, getSnapshot } from '../lib/session'
import {
  API,
  TOKEN_VALUE,
  errorResponse,
  handlers,
  studentUser,
  subject,
  teacherUser,
  tokenResponse,
} from '../tests/api'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const PASSWORD = 'a-very-long-password'

async function fillAndSubmit(email = 'ana@example.com', password = PASSWORD) {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText(strings.auth.login.email), email)
  await user.type(screen.getByLabelText(strings.auth.login.password), password)
  await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))
  return user
}

function collectConsole() {
  return (['log', 'info', 'warn', 'error', 'debug'] as const).map((level) =>
    vi.spyOn(console, level).mockImplementation(() => undefined),
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('LoginPage - signing in', () => {
  it('signs a student in: login, then the profile, then the subject list', async () => {
    const order: string[] = []
    server.use(
      http.post(`${API}/auth/login`, () => {
        order.push('login')
        return HttpResponse.json(tokenResponse())
      }),
      http.get(`${API}/users/me`, () => {
        order.push('me')
        return HttpResponse.json(studentUser)
      }),
      handlers.subjects([subject()]),
    )
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit()

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(order).toEqual(['login', 'me'])
    expect(getSnapshot().user?.role).toBe('student')
  })

  it('signs a teacher in with the teacher profile', async () => {
    server.use(handlers.login(), handlers.me(teacherUser), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit('tomas@example.com')

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(getSnapshot().user?.role).toBe('teacher')
  })

  it('sends only the email and the password and trims the email', async () => {
    let body: unknown
    server.use(
      http.post(`${API}/auth/login`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(tokenResponse())
      }),
      handlers.me(),
      handlers.subjects([]),
    )
    renderApp({ route: '/login' })

    await fillAndSubmit('  ana@example.com  ')

    await waitFor(() => expect(body).toEqual({ email: 'ana@example.com', password: PASSWORD }))
  })

  it('shows one message for wrong credentials, with no hint and no server text', async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        errorResponse(401, 'INVALID_CREDENTIALS', {}, 'password for ana@example.com is wrong'),
      ),
    )
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      strings.auth.errors.invalidCredentials,
    )
    expect(currentLocation()).toBe('/login')
    expect(getSnapshot().token).toBeNull()
    expect(document.body).not.toHaveTextContent('password for ana@example.com')
  })

  it('discards the token when the profile cannot be loaded', async () => {
    server.use(
      handlers.login(),
      http.get(`${API}/users/me`, () => errorResponse(500, 'INTERNAL_ERROR')),
    )
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.auth.errors.loginIncomplete)
    expect(getSnapshot()).toMatchObject({ token: null, user: null })
    expect(currentLocation()).toBe('/login')
  })

  it('does not leave a session notice behind after a failed profile load', async () => {
    server.use(
      handlers.login(),
      http.get(`${API}/users/me`, () => errorResponse(500, 'INTERNAL_ERROR')),
    )
    renderApp({ route: '/login' })
    await fillAndSubmit()
    await screen.findByRole('alert')

    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('treats an invalid token lifetime as a failed login', async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json({ access_token: TOKEN_VALUE, token_type: 'bearer', expires_in: 0 }),
      ),
      handlers.me(),
    )
    renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.auth.errors.loginIncomplete)
    expect(getSnapshot().token).toBeNull()
  })
})

describe('LoginPage - validation before sending', () => {
  async function submitAndCountLoginRequests(email: string, password: string) {
    let calls = 0
    server.use(
      http.post(`${API}/auth/login`, () => {
        calls += 1
        return HttpResponse.json(tokenResponse())
      }),
    )
    renderApp({ route: '/login' })
    const user = userEvent.setup()
    const emailInput = await screen.findByLabelText(strings.auth.login.email)
    const passwordInput = screen.getByLabelText(strings.auth.login.password)
    // paste() keeps the very long values fast.
    if (email) {
      await user.click(emailInput)
      await user.paste(email)
    }
    if (password) {
      await user.click(passwordInput)
      await user.paste(password)
    }
    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))
    return () => calls
  }

  it('blocks empty fields and focuses the first invalid one', async () => {
    const calls = await submitAndCountLoginRequests('', '')

    expect(await screen.findAllByText(strings.auth.validation.required)).toHaveLength(2)
    expect(calls()).toBe(0)
    await waitFor(() => expect(screen.getByLabelText(strings.auth.login.email)).toHaveFocus())
    expect(screen.getByLabelText(strings.auth.login.email)).toHaveAttribute('aria-invalid', 'true')
  })

  it('blocks an email longer than 255 characters', async () => {
    const calls = await submitAndCountLoginRequests('a'.repeat(250) + '@example.com', PASSWORD)

    expect(await screen.findByText(strings.auth.validation.emailTooLong)).toBeInTheDocument()
    expect(calls()).toBe(0)
  })

  it('blocks an email with non-ASCII characters', async () => {
    const calls = await submitAndCountLoginRequests('aña@example.com', PASSWORD)

    expect(await screen.findByText(strings.auth.validation.emailAscii)).toBeInTheDocument()
    expect(calls()).toBe(0)
  })

  it('blocks a password longer than 128 characters', async () => {
    const calls = await submitAndCountLoginRequests('ana@example.com', 'p'.repeat(129))

    expect(await screen.findByText(strings.auth.validation.passwordTooLong)).toBeInTheDocument()
    expect(calls()).toBe(0)
  })

  it('does not require the registration minimum length for an existing password', async () => {
    server.use(handlers.login(), handlers.me(), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit('ana@example.com', 'short')

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('survives a 100 KB value without freezing or sending anything', async () => {
    const calls = await submitAndCountLoginRequests('x'.repeat(100_000), 'y'.repeat(100_000))

    expect(await screen.findByText(strings.auth.validation.emailTooLong)).toBeInTheDocument()
    expect(screen.getByText(strings.auth.validation.passwordTooLong)).toBeInTheDocument()
    expect(calls()).toBe(0)
  })

  it('does not send control characters typed in the password as anything but text', async () => {
    let body: { password?: string } = {}
    server.use(
      http.post(`${API}/auth/login`, async ({ request }) => {
        body = (await request.json()) as { password?: string }
        return errorResponse(401, 'INVALID_CREDENTIALS')
      }),
    )
    renderApp({ route: '/login' })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(strings.auth.login.email), 'ana@example.com')
    await user.click(screen.getByLabelText(strings.auth.login.password))
    await user.paste('pass\u0000word‮!')
    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))

    await screen.findByRole('alert')
    expect(body.password).toBe('pass\u0000word‮!')
  })
})

describe('LoginPage - submitting', () => {
  it('sends one request when submitted twice and disables the control meanwhile', async () => {
    let calls = 0
    server.use(
      http.post(`${API}/auth/login`, async () => {
        calls += 1
        await delay(150)
        return HttpResponse.json(tokenResponse())
      }),
      handlers.me(),
      handlers.subjects([]),
    )
    renderApp({ route: '/login' })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(strings.auth.login.email), 'ana@example.com')
    await user.type(screen.getByLabelText(strings.auth.login.password), PASSWORD)
    const button = screen.getByRole('button', { name: strings.auth.login.submit })

    await user.click(button)
    await user.click(button)
    await user.keyboard('{Enter}')

    expect(screen.getByRole('button', { name: strings.auth.login.submitting })).toBeDisabled()
    await waitFor(() => expect(getSnapshot().user).not.toBeNull())
    expect(calls).toBe(1)
  })

  it('states the wait when rate limited', async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '17' }),
      ),
    )
    renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.errors.rateLimitedIn(17))
  })

  it('shows the generic rate limit message when Retry-After is not trustworthy', async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        errorResponse(429, 'RATE_LIMITED', { 'Retry-After': 'soon' }),
      ),
    )
    renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.errors.byCode.RATE_LIMITED)
  })

  it('reports an unavailable service and allows trying again', async () => {
    let calls = 0
    server.use(
      http.post(`${API}/auth/login`, () => {
        calls += 1
        return calls === 1
          ? errorResponse(503, 'SERVICE_UNAVAILABLE')
          : HttpResponse.json(tokenResponse())
      }),
      handlers.me(),
      handlers.subjects([]),
    )
    const { currentLocation } = renderApp({ route: '/login' })

    const user = await fillAndSubmit()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      strings.errors.byCode.SERVICE_UNAVAILABLE,
    )

    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))
    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('reports a network failure', async () => {
    server.use(http.post(`${API}/auth/login`, () => HttpResponse.error()))
    renderApp({ route: '/login' })

    await fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.errors.network)
  })
})

describe('LoginPage - notices and navigation', () => {
  it('shows the registered notice coming from the registration screen', async () => {
    renderApp({ route: '/login', routeState: { registered: true } })

    expect(await screen.findByRole('status')).toHaveTextContent(strings.auth.notices.registered)
  })

  it.each([
    ['expired', strings.auth.notices.expired],
    ['unauthorized', strings.auth.notices.unauthorized],
  ] as const)('shows why the previous session ended (%s)', async (reason, text) => {
    server.use(handlers.subjects([]))
    renderApp({ session: { user: studentUser } })
    endSession(reason)

    expect(await screen.findByText(text)).toHaveAttribute('role', 'status')
  })

  it('offers a link to the registration screen', async () => {
    renderApp({ route: '/login' })

    expect(
      await screen.findByRole('link', { name: strings.auth.login.createAccount }),
    ).toHaveAttribute('href', '/register')
  })

  it('has a single level-one heading and no serious accessibility violations', async () => {
    const { container } = renderApp({ route: '/login' })

    expect(await screen.findAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(strings.auth.login.title)
    await expectNoSeriousA11yViolations(container)
  })
})

describe('LoginPage - sensitive data', () => {
  it('prints neither the password, the token nor the email on a failed login', async () => {
    const spies = collectConsole()
    server.use(http.post(`${API}/auth/login`, () => errorResponse(500, 'INTERNAL_ERROR')))
    renderApp({ route: '/login' })

    await fillAndSubmit('ana@example.com', PASSWORD)
    await screen.findByRole('alert')

    const printed = JSON.stringify(spies.flatMap((spy) => spy.mock.calls))
    expect(printed).not.toContain(PASSWORD)
    expect(printed).not.toContain('ana@example.com')
    expect(printed).not.toContain(TOKEN_VALUE)
    expect(document.body.textContent).not.toContain(PASSWORD)
  })

  it('never puts credentials or the token in the URL', async () => {
    server.use(handlers.login(), handlers.me(), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/login' })

    await fillAndSubmit()
    await waitFor(() => expect(currentLocation()).toBe('/subjects'))

    expect(window.location.href).not.toContain(TOKEN_VALUE)
    expect(window.location.href).not.toContain(PASSWORD)
  })
})
