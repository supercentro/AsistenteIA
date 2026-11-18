import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import { endSession, getSnapshot, setUser, startSession } from '../lib/session'
import { strings } from '../lib/strings.es'
import {
  API,
  TOKEN_VALUE,
  errorBody,
  handlers,
  outdatedStudent,
  studentUser,
  subject,
  teacherUser,
  unconsentedStudent,
} from '../tests/api'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

afterEach(() => {
  vi.restoreAllMocks()
})

const accepted = { ...studentUser }

function acceptHandler(onBody?: (body: unknown) => void) {
  return http.post(`${API}/users/me/consent`, async ({ request }) => {
    onBody?.(await request.json())
    return HttpResponse.json(accepted)
  })
}

async function tickBox() {
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('checkbox', { name: strings.consent.checkbox(PRIVACY_POLICY_VERSION) }),
  )
  return user
}

describe('ConsentPage - explicit and recorded consent', () => {
  it('shows the version, the policy text, an unticked box and a disabled Accept', async () => {
    server.use(handlers.me(unconsentedStudent), handlers.subjects([]))
    const { container } = renderApp({ route: '/consent', session: { user: unconsentedStudent } })

    const heading = await screen.findByRole('heading', { level: 1, name: strings.consent.title })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(strings.privacy.versionLabel(PRIVACY_POLICY_VERSION))).toBeVisible()
    expect(
      screen.getByRole('heading', { name: strings.privacy.sections.processor.heading }),
    ).toBeVisible()
    expect(
      screen.getByRole('checkbox', { name: strings.consent.checkbox(PRIVACY_POLICY_VERSION) }),
    ).not.toBeChecked()
    expect(screen.getByRole('button', { name: strings.consent.accept })).toBeDisabled()
    expect(screen.getByRole('link', { name: strings.consent.policyLink })).toHaveAttribute(
      'href',
      '/privacy',
    )
    await expectNoSeriousA11yViolations(container)
  })

  it('tells a first-time student apart from one whose policy changed', async () => {
    renderApp({ route: '/consent', session: { user: unconsentedStudent } })
    expect(await screen.findByText(strings.consent.firstTime)).toBeVisible()
  })

  it('shows the changed-policy notice to a student with an outdated version', async () => {
    renderApp({ route: '/consent', session: { user: outdatedStudent } })
    expect(await screen.findByText(strings.consent.changed)).toBeVisible()
  })

  it('keeps Accept disabled while the box is unticked and sends nothing', async () => {
    const posted = vi.fn()
    server.use(acceptHandler(posted))
    renderApp({ route: '/consent', session: { user: unconsentedStudent } })

    const user = await tickBox()
    await user.click(
      screen.getByRole('checkbox', { name: strings.consent.checkbox(PRIVACY_POLICY_VERSION) }),
    )

    expect(screen.getByRole('button', { name: strings.consent.accept })).toBeDisabled()
    expect(posted).not.toHaveBeenCalled()
  })

  it('accepts: sends the current version, replaces the profile and goes to the original target', async () => {
    const posted = vi.fn()
    server.use(acceptHandler(posted), handlers.subjects([subject()]))
    const { currentLocation } = renderApp({
      route: '/consent',
      routeState: { from: '/subjects' },
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(posted).toHaveBeenCalledWith({ consent_version: PRIVACY_POLICY_VERSION })
    expect(getSnapshot().user?.consent_version).toBe(PRIVACY_POLICY_VERSION)
  })

  it('goes to the home route when there is no original target', async () => {
    server.use(acceptHandler(), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/consent', session: { user: outdatedStudent } })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('ignores an unsafe original target', async () => {
    server.use(acceptHandler(), handlers.subjects([]))
    const { currentLocation } = renderApp({
      route: '/consent',
      routeState: { from: 'https://evil.example/steal' },
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('shows the reload message on 422 INVALID_CONSENT_VERSION and keeps the student held', async () => {
    server.use(
      http.post(`${API}/users/me/consent`, () =>
        HttpResponse.json(
          errorBody('INVALID_CONSENT_VERSION', 'echoes 2099-x', { current_version: '2099-x' }),
          { status: 422 },
        ),
      ),
    )
    const { currentLocation } = renderApp({
      route: '/consent',
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.consent.versionChanged)
    expect(screen.queryByText(/2099-x/)).not.toBeInTheDocument()
    expect(currentLocation()).toBe('/consent')
    expect(getSnapshot().user?.consent_version).toBeNull()
  })

  it('shows an error with a retry control on a network failure and leaves the profile', async () => {
    server.use(http.post(`${API}/users/me/consent`, () => HttpResponse.error()))
    const { currentLocation } = renderApp({
      route: '/consent',
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    expect(await screen.findByRole('alert')).toHaveTextContent(strings.errors.network)
    expect(screen.getByRole('button', { name: strings.states.retry })).toBeVisible()
    expect(currentLocation()).toBe('/consent')
    expect(getSnapshot().user?.consent_version).toBeNull()
  })

  it('retries and succeeds after a server error', async () => {
    let calls = 0
    server.use(
      http.post(`${API}/users/me/consent`, () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json(errorBody('SERVICE_UNAVAILABLE'), { status: 503 })
          : HttpResponse.json(accepted)
      }),
      handlers.subjects([]),
    )
    const { currentLocation } = renderApp({
      route: '/consent',
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))
    await user.click(await screen.findByRole('button', { name: strings.states.retry }))

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(calls).toBe(2)
  })

  it('ends the session on 401 as for any other request', async () => {
    server.use(
      http.post(`${API}/users/me/consent`, () =>
        HttpResponse.json(errorBody('UNAUTHORIZED'), { status: 401 }),
      ),
    )
    const { currentLocation } = renderApp({
      route: '/consent',
      session: { user: unconsentedStudent },
    })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(getSnapshot().token).toBeNull()
  })

  it('does not put tokens, emails or the form values in the console or the page on errors', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    )
    server.use(http.post(`${API}/users/me/consent`, () => HttpResponse.error()))
    renderApp({ route: '/consent', session: { user: unconsentedStudent } })

    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))
    await screen.findByRole('alert')

    const logged = spies.flatMap((spy) => spy.mock.calls.flat().map(String)).join(' ')
    expect(logged).not.toContain(TOKEN_VALUE)
    expect(logged).not.toContain(unconsentedStudent.email)
    expect(document.body.textContent).not.toContain(unconsentedStudent.email)
  })
})

describe('ConsentPage - leaving without accepting', () => {
  it('offers sign-out and clears the session', async () => {
    const { currentLocation } = renderApp({
      route: '/consent',
      session: { user: unconsentedStudent },
    })

    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: strings.consent.signOut }))

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(getSnapshot().token).toBeNull()
  })

  it('redirects a student with current consent to the home route', async () => {
    server.use(handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/consent', session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('redirects a teacher to the home route', async () => {
    server.use(handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/consent', session: { user: teacherUser } })

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('redirects an anonymous visitor to the login screen', async () => {
    const { currentLocation } = renderApp({ route: '/consent' })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })
})

describe('ConsentPage - session races and the policy link', () => {
  it('opens the policy in a new tab so that reading it does not end the session', async () => {
    renderApp({ route: '/consent', session: { user: unconsentedStudent } })

    const link = await screen.findByRole('link', { name: strings.consent.policyLink })

    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('does not write the answer of an earlier session into the session that is open now', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.post(`${API}/users/me/consent`, async () => {
        await gate
        return HttpResponse.json(accepted)
      }),
      handlers.subjects([]),
    )
    renderApp({ route: '/consent', session: { user: unconsentedStudent } })
    const user = await tickBox()
    await user.click(screen.getByRole('button', { name: strings.consent.accept }))

    // The first student leaves and another user signs in before the answer arrives.
    act(() => {
      endSession('signed-out')
      startSession('another-session-token', 3600)
      setUser(teacherUser)
    })
    release()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(getSnapshot().user?.id).toBe(teacherUser.id)
    expect(getSnapshot().user?.email).toBe(teacherUser.email)
    expect(getSnapshot().user?.consent_version).toBe(teacherUser.consent_version)
  })
})
