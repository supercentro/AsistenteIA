import { useQuery } from '@tanstack/react-query'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { RequireAuth } from './components/RequireAuth'
import { RequireRole } from './components/RequireRole'
import { apiClient } from './lib/apiClient'
import { getSnapshot } from './lib/session'
import { strings } from './lib/strings.es'
import {
  API,
  TOKEN_VALUE,
  errorResponse,
  handlers,
  studentUser,
  teacherUser,
  tokenResponse,
} from './tests/api'
import { server } from './tests/server'
import { renderApp, renderWithProviders } from './tests/utils'

function Probe() {
  useQuery({ queryKey: ['probe'], queryFn: () => apiClient.get('/probe') })
  return <p>restricted content</p>
}

function GuardedRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<p>login screen</p>} />
      <Route element={<RequireAuth />}>
        <Route element={<RequireRole roles={['teacher']} />}>
          <Route path="/teacher-only" element={<Probe />} />
        </Route>
      </Route>
    </Routes>
  )
}

async function signIn(email = 'ana@example.com') {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText(strings.auth.login.email), email)
  await user.type(screen.getByLabelText(strings.auth.login.password), 'a-very-long-password')
  await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))
}

describe('App routing', () => {
  it('sends an anonymous visitor from the start page to the login screen without requesting data', async () => {
    let requests = 0
    server.use(
      http.get(`${API}/subjects`, () => {
        requests += 1
        return HttpResponse.json([])
      }),
    )
    const { currentLocation } = renderApp({ route: '/' })

    expect(
      await screen.findByRole('heading', { name: strings.auth.login.title }),
    ).toBeInTheDocument()
    expect(currentLocation()).toBe('/login')
    expect(requests).toBe(0)
  })

  it('returns an anonymous visitor to the protected page they asked for after signing in', async () => {
    server.use(handlers.login(), handlers.me(), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/subjects' })

    await signIn()

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      strings.subjects.titleStudent,
    )
  })

  it('returns to an internal page recorded as the origin of the redirect', async () => {
    server.use(handlers.login(), handlers.me())
    const { currentLocation } = renderApp({ route: '/login', routeState: { from: '/somewhere' } })

    await signIn()

    await waitFor(() => expect(currentLocation()).toBe('/somewhere'))
  })

  it.each([
    ['an absolute URL', 'https://evil.example/steal'],
    ['a protocol-relative URL', '//evil.example'],
    ['the login route', '/login'],
    ['the register route', '/register'],
    ['a non-string', { pathname: '/x' }],
  ])('ignores %s as a return target', async (_name, from) => {
    server.use(handlers.login(), handlers.me(), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/login', routeState: { from } })

    await signIn()

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it.each(['/login', '/register'])('moves a signed-in user away from %s', async (route) => {
    server.use(handlers.subjects([]))
    const { currentLocation } = renderApp({ route, session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/subjects'))
  })

  it('shows the not-found view with a link to the start for anonymous and signed-in visitors', async () => {
    const anonymous = renderApp({ route: '/does-not-exist' })
    expect(await screen.findByRole('heading', { name: strings.notFound.title })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: strings.notFound.backHome })).toHaveAttribute(
      'href',
      '/',
    )
    anonymous.unmountAndDetach()

    renderApp({ route: '/does-not-exist', session: { user: teacherUser } })
    expect(await screen.findByRole('heading', { name: strings.notFound.title })).toBeInTheDocument()
  })

  it('takes the role from the profile and ignores the claims inside the token', async () => {
    const claims = btoa(JSON.stringify({ role: 'teacher' }))
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json({ ...tokenResponse(), access_token: `h.${claims}.s` }),
      ),
      handlers.me(studentUser),
      handlers.subjects([]),
    )
    renderApp({ route: '/login' })

    await signIn()

    await waitFor(() => expect(getSnapshot().user?.role).toBe('student'))
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      strings.subjects.titleStudent,
    )
  })

  it('ends the session once and shows the login screen with a notice when the API answers 401', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/subjects`, ({ request }) => {
        // Only the requests of this test's session count: a request that an earlier test left in
        // flight (it carries that session's token) can reach this handler late under load.
        if (request.headers.get('authorization') === `Bearer ${TOKEN_VALUE}`) {
          calls += 1
        }
        return errorResponse(401, 'UNAUTHORIZED')
      }),
    )
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(await screen.findByRole('status')).toHaveTextContent(strings.auth.notices.unauthorized)
    expect(getSnapshot().token).toBeNull()
    expect(calls).toBe(1)
  })
})

describe('RequireAuth and RequireRole', () => {
  it('redirects an anonymous visitor to login and requests nothing', async () => {
    let requests = 0
    server.use(
      http.get(`${API}/probe`, () => {
        requests += 1
        return HttpResponse.json({})
      }),
    )
    const { currentLocation } = renderWithProviders(<GuardedRoutes />, { route: '/teacher-only' })

    expect(await screen.findByText('login screen')).toBeInTheDocument()
    expect(currentLocation()).toBe('/login')
    expect(requests).toBe(0)
  })

  it('shows the forbidden view to the wrong role, mounts nothing and requests nothing', async () => {
    let requests = 0
    server.use(
      http.get(`${API}/probe`, () => {
        requests += 1
        return HttpResponse.json({})
      }),
    )
    renderWithProviders(<GuardedRoutes />, {
      route: '/teacher-only',
      session: { user: studentUser },
    })

    expect(
      await screen.findByRole('heading', { name: strings.forbidden.title }),
    ).toBeInTheDocument()
    expect(screen.queryByText('restricted content')).not.toBeInTheDocument()
    expect(requests).toBe(0)
  })

  it('renders the content for an allowed role', async () => {
    server.use(http.get(`${API}/probe`, () => HttpResponse.json({})))
    renderWithProviders(<GuardedRoutes />, {
      route: '/teacher-only',
      session: { user: teacherUser },
    })

    expect(await screen.findByText('restricted content')).toBeInTheDocument()
  })
})
