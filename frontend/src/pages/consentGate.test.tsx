import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'
import { strings } from '../lib/strings.es'
import {
  API,
  errorBody,
  handlers,
  outdatedStudent,
  studentUser,
  subject,
  teacherUser,
  unconsentedStudent,
} from '../tests/api'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

describe('Consent gate - students are held until consent is current', () => {
  it('holds a student who never accepted, and the requested route is not rendered', async () => {
    server.use(handlers.subjects([subject({ name: 'Algebra secreta' })]))
    const { currentLocation } = renderApp({
      route: '/subjects',
      session: { user: unconsentedStudent },
    })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(screen.queryByText('Algebra secreta')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: strings.subjects.listLabel })).not.toBeInTheDocument()
  })

  it('does not even request the data of the held route', async () => {
    let requested = false
    server.use(handlers.subjects([]))
    server.events.on('request:start', ({ request }) => {
      if (request.url.endsWith('/subjects')) requested = true
    })
    const { currentLocation } = renderApp({
      route: '/subjects',
      session: { user: unconsentedStudent },
    })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(requested).toBe(false)
    server.events.removeAllListeners()
  })

  it('remembers the original target for after the acceptance', async () => {
    const { currentLocation } = renderApp({
      route: '/subjects',
      session: { user: unconsentedStudent },
    })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(screen.getByTestId('location')).toHaveAttribute('data-from', '/subjects')
  })

  it('shows the changed-policy notice to a student with an outdated version', async () => {
    renderApp({ route: '/subjects', session: { user: outdatedStudent } })

    expect(await screen.findByText(strings.consent.changed)).toBeVisible()
  })

  it('holds a student who types the address of the home route', async () => {
    const { currentLocation } = renderApp({
      route: '/',
      session: { user: unconsentedStudent },
    })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
  })

  it('holds a student signing in: login, profile, then the consent screen', async () => {
    server.use(handlers.login(), handlers.me(unconsentedStudent), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/login' })

    const { default: userEvent } = await import('@testing-library/user-event')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(strings.auth.login.email), 'ana@example.com')
    await user.type(screen.getByLabelText(strings.auth.login.password), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
  })

  it('lets a student with current consent through', async () => {
    server.use(handlers.subjects([subject({ name: 'Algebra' })]))
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: studentUser } })

    expect(await screen.findByText('Algebra')).toBeVisible()
    expect(currentLocation()).toBe('/subjects')
  })

  it('never holds a teacher', async () => {
    server.use(handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: teacherUser } })

    expect(await screen.findByText(strings.subjects.emptyTeacher)).toBeVisible()
    expect(currentLocation()).toBe('/subjects')
  })

  it('sends an anonymous visitor to the login screen, not to the consent screen', async () => {
    const { currentLocation } = renderApp({ route: '/subjects' })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })
})

describe('Consent gate - the policy changes during the session', () => {
  it('a 403 CONSENT_REQUIRED from a page request takes the student to the consent screen with the changed notice', async () => {
    server.use(
      http.get(`${API}/subjects`, () =>
        HttpResponse.json(errorBody('CONSENT_REQUIRED'), { status: 403 }),
      ),
    )
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(await screen.findByText(strings.consent.changed)).toBeVisible()
    expect(screen.queryByText(strings.consent.firstTime)).not.toBeInTheDocument()
  })
})
