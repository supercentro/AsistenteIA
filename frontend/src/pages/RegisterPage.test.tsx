import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { getSnapshot } from '../lib/session'
import { API, errorResponse, studentUser } from '../tests/api'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const PASSWORD = 'a-very-long-password'

interface Values {
  name?: string
  email?: string
  password?: string
}

async function fill({ name = 'Ana', email = 'ana@example.com', password = PASSWORD }: Values = {}) {
  const user = userEvent.setup()
  const nameInput = await screen.findByLabelText(strings.auth.register.name)
  const emailInput = screen.getByLabelText(strings.auth.register.email)
  const passwordInput = screen.getByLabelText(strings.auth.register.password)
  for (const [input, value] of [
    [nameInput, name],
    [emailInput, email],
    [passwordInput, password],
  ] as const) {
    if (value) {
      await user.click(input)
      await user.paste(value)
    }
  }
  return user
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: strings.auth.register.submit }))
}

function captureRegistrations(
  response: () => Response | Promise<Response> = () =>
    HttpResponse.json(studentUser, { status: 201 }),
) {
  const bodies: unknown[] = []
  server.use(
    http.post(`${API}/auth/register`, async ({ request }) => {
      bodies.push(await request.json())
      return response()
    }),
  )
  return bodies
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RegisterPage - registering', () => {
  it('redirects to the login screen with a notice and does not sign in', async () => {
    const bodies = captureRegistrations()
    const { currentLocation } = renderApp({ route: '/register' })

    await submit(await fill())

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(await screen.findByRole('status')).toHaveTextContent(strings.auth.notices.registered)
    expect(bodies).toHaveLength(1)
    expect(getSnapshot()).toMatchObject({ token: null, user: null })
  })

  it('sends only name, email and password and trims name and email', async () => {
    const bodies = captureRegistrations()
    renderApp({ route: '/register' })

    await submit(await fill({ name: '  Ana  ', email: ' ana@example.com ' }))

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({ name: 'Ana', email: 'ana@example.com', password: PASSWORD })
    expect(Object.keys(bodies[0] as object).sort()).toEqual(['email', 'name', 'password'])
  })

  it('never sends a role even if one is injected into the form values', async () => {
    const bodies = captureRegistrations()
    renderApp({ route: '/register' })

    await submit(await fill({ name: 'role: teacher' }))

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).not.toHaveProperty('role')
  })

  it('says the email is already registered and keeps the other fields', async () => {
    captureRegistrations(() => errorResponse(409, 'CONFLICT', {}, 'ana@example.com already exists'))
    const { currentLocation } = renderApp({ route: '/register' })

    await submit(await fill())

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.auth.errors.emailTaken)
    expect(currentLocation()).toBe('/register')
    expect(screen.getByLabelText(strings.auth.register.name)).toHaveValue('Ana')
    expect(document.body).not.toHaveTextContent('already exists')
  })

  it('shows a generic validation message for a 422 without echoing values', async () => {
    captureRegistrations(() =>
      HttpResponse.json(
        {
          code: 'VALIDATION_ERROR',
          message: 'Request validation failed',
          details: { errors: [{ field: 'name', message: 'bad <b>Ana</b>' }] },
        },
        { status: 422 },
      ),
    )
    renderApp({ route: '/register' })

    await submit(await fill())

    expect(await screen.findByRole('alert')).toHaveTextContent(
      strings.errors.byCode.VALIDATION_ERROR,
    )
    expect(document.body).not.toHaveTextContent('bad')
  })

  it('states the wait when rate limited', async () => {
    captureRegistrations(() => errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '30' }))
    renderApp({ route: '/register' })

    await submit(await fill())

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.errors.rateLimitedIn(30))
  })

  it('sends one request when submitted twice', async () => {
    const bodies = captureRegistrations(async () => {
      await delay(150)
      return HttpResponse.json(studentUser, { status: 201 })
    })
    const { currentLocation } = renderApp({ route: '/register' })

    const user = await fill()
    const button = screen.getByRole('button', { name: strings.auth.register.submit })
    await user.click(button)
    await user.click(button)
    await user.keyboard('{Enter}')

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(bodies).toHaveLength(1)
  })
})

describe('RegisterPage - validation before sending', () => {
  it.each([
    ['an empty name', { name: '' }, strings.auth.validation.required],
    ['a whitespace-only name', { name: '    ' }, strings.auth.validation.required],
    ['a name over 100 characters', { name: 'n'.repeat(101) }, strings.auth.validation.nameTooLong],
    ['an empty email', { email: '' }, strings.auth.validation.required],
    ['a malformed email', { email: 'not-an-email' }, strings.auth.validation.emailInvalid],
    [
      'an email over 255 characters',
      { email: 'e'.repeat(250) + '@example.com' },
      strings.auth.validation.emailTooLong,
    ],
    ['a non-ASCII email', { email: 'aña@example.com' }, strings.auth.validation.emailAscii],
    [
      'a 9-character password',
      { password: 'x'.repeat(9) },
      strings.auth.validation.passwordTooShort,
    ],
    ['an empty password', { password: '' }, strings.auth.validation.required],
    [
      'a password over 128 characters',
      { password: 'p'.repeat(129) },
      strings.auth.validation.passwordTooLong,
    ],
  ] as const)('blocks %s without sending a request', async (_label, values, message) => {
    const bodies = captureRegistrations()
    renderApp({ route: '/register' })

    await submit(await fill(values))

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(bodies).toHaveLength(0)
  })

  it('accepts the boundary lengths (name 100, password 10 and 128)', async () => {
    const bodies = captureRegistrations()
    renderApp({ route: '/register' })

    await submit(await fill({ name: 'n'.repeat(100), password: 'x'.repeat(10) }))
    await waitFor(() => expect(bodies).toHaveLength(1))
  })

  it('moves focus to the first invalid field', async () => {
    renderApp({ route: '/register' })

    await submit(await fill({ name: '', email: 'bad' }))

    await waitFor(() => expect(screen.getByLabelText(strings.auth.register.name)).toHaveFocus())
  })

  it('survives a 100 KB name without freezing or sending anything', async () => {
    const bodies = captureRegistrations()
    renderApp({ route: '/register' })

    await submit(await fill({ name: 'n'.repeat(100_000) }))

    expect(await screen.findByText(strings.auth.validation.nameTooLong)).toBeInTheDocument()
    expect(bodies).toHaveLength(0)
  })
})

describe('RegisterPage - screen', () => {
  it('links back to the login screen', async () => {
    renderApp({ route: '/register' })

    expect(
      await screen.findByRole('link', { name: strings.auth.register.haveAccount }),
    ).toHaveAttribute('href', '/login')
  })

  it('shows the password hint, one level-one heading and no serious accessibility violations', async () => {
    const { container } = renderApp({ route: '/register' })

    expect(await screen.findAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByLabelText(strings.auth.register.password)).toHaveAccessibleDescription(
      strings.auth.register.passwordHint,
    )
    await expectNoSeriousA11yViolations(container)
  })

  it('does not print the password or the email on a failed registration', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    )
    captureRegistrations(() => errorResponse(500, 'INTERNAL_ERROR'))
    renderApp({ route: '/register' })

    await submit(await fill())
    await screen.findByRole('alert')

    const printed = JSON.stringify(spies.flatMap((spy) => spy.mock.calls))
    expect(printed).not.toContain(PASSWORD)
    expect(printed).not.toContain('ana@example.com')
  })
})
