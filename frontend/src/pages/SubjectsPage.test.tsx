import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { getSnapshot } from '../lib/session'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, errorResponse, handlers, studentUser, subject, teacherUser } from '../tests/api'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const NEWLINE = String.fromCharCode(10)

describe('SubjectsPage - states', () => {
  it('shows a polite loading status while the request is in flight', async () => {
    server.use(
      http.get(`${API}/subjects`, async () => {
        await delay(200)
        return HttpResponse.json([subject()])
      }),
    )
    renderApp({ route: '/subjects', session: { user: studentUser } })

    expect(await screen.findByText(strings.subjects.loading)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(strings.subjects.loading)
    expect(screen.queryByText(strings.subjects.emptyStudent)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(await screen.findByText('Algebra')).toBeInTheDocument()
  })

  it.each([
    ['student', studentUser, strings.subjects.emptyStudent],
    ['teacher', teacherUser, strings.subjects.emptyTeacher],
  ] as const)('shows the empty message of a %s', async (_role, user, message) => {
    server.use(handlers.subjects([]))
    renderApp({ route: '/subjects', session: { user } })

    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('shows an announced error with a retry that sends the request again', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/subjects`, () => {
        calls += 1
        return calls === 1 ? errorResponse(403, 'FORBIDDEN') : HttpResponse.json([subject()])
      }),
    )
    renderApp({ route: '/subjects', session: { user: studentUser } })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(strings.errors.byCode.FORBIDDEN)
    await userEvent.click(within(alert).getByRole('button', { name: strings.states.retry }))

    expect(await screen.findByText('Algebra')).toBeInTheDocument()
    expect(calls).toBe(2)
  })

  it('does not show the error state when the request is answered with 401: the session ends instead', async () => {
    server.use(http.get(`${API}/subjects`, () => errorResponse(401, 'UNAUTHORIZED')))
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: studentUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.subjects.loadError)).not.toBeInTheDocument()
    expect(getSnapshot().token).toBeNull()
  })
})

describe('SubjectsPage - content', () => {
  it('lists the subjects in the order received with name and description', async () => {
    server.use(
      handlers.subjects([
        subject({ id: '1', name: 'Zoologia', description: 'Animales' }),
        subject({ id: '2', name: 'Algebra', description: null }),
        subject({ id: '3', name: 'Biologia', description: 'Vida' }),
      ]),
    )
    renderApp({ route: '/subjects', session: { user: studentUser } })

    const items = await screen.findAllByRole('listitem')
    expect(items.map((item) => item.querySelector('h2')?.textContent)).toEqual([
      'Zoologia',
      'Algebra',
      'Biologia',
    ])
    expect(within(items[0] as HTMLElement).getByText('Animales')).toBeInTheDocument()
    expect(within(items[1] as HTMLElement).queryByText(/./, { selector: 'p' })).toBeNull()
  })

  it('renders names and descriptions as text, never as markup', async () => {
    server.use(
      handlers.subjects([
        subject({ name: '<b>Negrita</b>', description: '<img src=x onerror="alert(1)">' }),
      ]),
    )
    renderApp({ route: '/subjects', session: { user: teacherUser } })

    expect(await screen.findByText('<b>Negrita</b>')).toBeInTheDocument()
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    expect(document.querySelector('main b')).toBeNull()
  })

  it('wraps long unbroken text and keeps the line breaks of a description', async () => {
    const description = `Primera linea${NEWLINE}Segunda linea`
    server.use(handlers.subjects([subject({ name: 'N'.repeat(150), description })]))
    renderApp({ route: '/subjects', session: { user: studentUser } })

    const heading = await screen.findByRole('heading', { level: 2, name: 'N'.repeat(150) })
    expect(heading.className).toContain('break-words')
    const body = screen.getByText((_content, element) => element?.textContent === description)
    expect(body.className).toContain('whitespace-pre-line')
  })

  it('offers a student the chat link and the history action, and no way to create, edit or enrol', async () => {
    server.use(handlers.subjects([subject()]))
    renderApp({ route: '/subjects', session: { user: studentUser } })

    await screen.findByText('Algebra')
    const buttons = screen.getAllByRole('button').map((button) => button.textContent)
    expect(buttons).toEqual([strings.nav.signOut, strings.chat.history.action])
    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      strings.nav.subjects,
      strings.chat.openChat('Algebra'),
    ])
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('lets the chat link of a subject with a very long name wrap', async () => {
    server.use(handlers.subjects([subject({ name: 'N'.repeat(150) })]))
    renderApp({ route: '/subjects', session: { user: studentUser } })

    const link = await screen.findByRole('link', { name: strings.chat.openChat('N'.repeat(150)) })

    expect(link.className).toContain('break-words')
    expect(link.className).toContain('[overflow-wrap:anywhere]')
  })

  it('offers a teacher the create form and a link per subject, and no delete, edit or enrol', async () => {
    server.use(handlers.subjects([subject()]))
    renderApp({ route: '/subjects', session: { user: teacherUser } })

    await screen.findByText('Algebra')
    const buttons = screen.getAllByRole('button').map((button) => button.textContent)
    expect(buttons).toEqual([strings.nav.signOut, strings.subjects.create.submit])
    const links = screen.getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([strings.nav.subjects, 'Algebra'])
    expect(links[1]).toHaveAttribute('href', `/subjects/${subject().id}`)
  })

  it('uses a cache key per user', async () => {
    server.use(handlers.subjects([subject()]))
    const { client } = renderApp({ route: '/subjects', session: { user: studentUser } })

    await screen.findByText('Algebra')
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((query) => query.queryKey),
    ).toEqual([['subjects', studentUser.id]])
  })
})

describe('Application shell', () => {
  it.each([
    ['student', studentUser, strings.subjects.titleStudent],
    ['teacher', teacherUser, strings.subjects.titleTeacher],
  ] as const)('shows the navigation and copy of a %s', async (_role, user, title) => {
    server.use(handlers.subjects([]))
    renderApp({ route: '/subjects', session: { user } })

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(title)
    const nav = screen.getByRole('navigation', { name: strings.nav.label })
    expect(within(nav).getAllByRole('link')).toHaveLength(1)
    expect(within(nav).getByRole('link', { name: strings.nav.subjects })).toBeInTheDocument()
    expect(screen.getByText(strings.nav.signedInAs(user.name ?? ''))).toBeInTheDocument()
    expect(screen.getByRole('banner')).toHaveTextContent(strings.app.name)
  })

  it('signs out: clears token, profile and cache and shows the login screen with a notice', async () => {
    server.use(handlers.subjects([subject()]))
    const { client, currentLocation } = renderApp({
      route: '/subjects',
      session: { user: studentUser },
    })
    await screen.findByText('Algebra')

    await userEvent.click(screen.getByRole('button', { name: strings.nav.signOut }))

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(getSnapshot()).toMatchObject({ token: null, user: null })
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    expect(await screen.findByRole('status')).toHaveTextContent(strings.auth.notices.signedOut)
  })

  it('never shows the first user data to a second user in the same tab', async () => {
    let requests = 0
    server.use(
      http.get(`${API}/subjects`, ({ request }) => {
        requests += 1
        const first = request.headers.get('authorization') !== null && requests === 1
        return HttpResponse.json([subject({ name: first ? 'Materia de Ana' : 'Materia de Tomas' })])
      }),
      handlers.login(),
      handlers.me(teacherUser),
    )
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: studentUser } })
    await screen.findByText('Materia de Ana')

    await userEvent.click(screen.getByRole('button', { name: strings.nav.signOut }))
    await waitFor(() => expect(currentLocation()).toBe('/login'))
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(strings.auth.login.email), 'tomas@example.com')
    await user.type(screen.getByLabelText(strings.auth.login.password), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: strings.auth.login.submit }))

    expect(await screen.findByText('Materia de Tomas')).toBeInTheDocument()
    expect(screen.queryByText('Materia de Ana')).not.toBeInTheDocument()
    expect(requests).toBe(2)
  })

  it('has a single level-one heading and no serious accessibility violations', async () => {
    server.use(handlers.subjects([subject({ description: 'Texto' })]))
    const { container } = renderApp({ route: '/subjects', session: { user: studentUser } })

    await screen.findByText('Algebra')
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    await expectNoSeriousA11yViolations(container)
  })

  it('has no serious accessibility violations on the not-found view', async () => {
    const { container } = renderApp({ route: '/nothing-here' })

    await screen.findByRole('heading', { name: strings.notFound.title })
    await expectNoSeriousA11yViolations(container)
  })
})
