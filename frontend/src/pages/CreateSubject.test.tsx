import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, errorResponse, handlers, subject, teacherUser } from '../tests/api'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'
import type { Subject } from '../types/api'

const text = strings.subjects.create

/** A list that grows with every accepted POST, as the real backend would answer. */
function statefulSubjects(initial: Subject[] = []) {
  const stored = [...initial]
  const bodies: unknown[] = []
  server.use(
    http.get(`${API}/subjects`, () => HttpResponse.json(stored)),
    http.post(`${API}/subjects`, async ({ request }) => {
      const body = (await request.json()) as { name: string; description?: string }
      bodies.push(body)
      const created = subject({
        id: '55555555-5555-4555-8555-555555555555',
        name: body.name,
        description: body.description ?? null,
      })
      stored.push(created)
      return HttpResponse.json(created, { status: 201 })
    }),
  )
  return { bodies }
}

async function openForm() {
  const user = userEvent.setup()
  const name = await screen.findByRole('textbox', { name: text.name })
  const description = screen.getByRole('textbox', { name: text.description })
  const submit = screen.getByRole('button', { name: text.submit })
  return { user, name, description, submit }
}

describe('Create subject form (teacher)', () => {
  it('creates a subject, shows it in the list and clears the form', async () => {
    const { bodies } = statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, description, submit } = await openForm()

    await user.type(name, '  Fisica  ')
    await user.type(description, 'Mecanica clasica')
    await user.click(submit)

    expect(await screen.findByRole('link', { name: 'Fisica' })).toBeInTheDocument()
    expect(bodies).toEqual([{ name: 'Fisica', description: 'Mecanica clasica' }])
    await waitFor(() => expect(name).toHaveValue(''))
    expect(description).toHaveValue('')
  })

  it('does not send a blank description', async () => {
    const { bodies } = statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, description, submit } = await openForm()

    await user.type(name, 'Quimica')
    await user.type(description, '   ')
    await user.click(submit)

    await screen.findByRole('link', { name: 'Quimica' })
    expect(bodies).toEqual([{ name: 'Quimica' }])
  })

  it('sends nothing for a blank name and focuses the first invalid field', async () => {
    const { bodies } = statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, submit } = await openForm()

    await user.type(name, '   ')
    await user.click(submit)

    const error = await screen.findByText(text.validation.nameRequired)
    expect(bodies).toEqual([])
    await waitFor(() => expect(name).toHaveFocus())
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(name.getAttribute('aria-describedby')).toContain(error.id)
  })

  it('rejects a name over 150 characters and a description over 2000, without a request', async () => {
    const { bodies } = statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, description, submit } = await openForm()

    await user.click(name)
    await user.paste('N'.repeat(151))
    await user.click(description)
    await user.paste('D'.repeat(2001))
    await user.click(submit)

    expect(await screen.findByText(text.validation.nameTooLong)).toBeVisible()
    expect(screen.getByText(text.validation.descriptionTooLong)).toBeVisible()
    expect(bodies).toEqual([])
    await waitFor(() => expect(name).toHaveFocus())
  })

  it('focuses the description when only the description is invalid', async () => {
    statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, description, submit } = await openForm()

    await user.type(name, 'Valida')
    await user.click(description)
    await user.paste('D'.repeat(2001))
    await user.click(submit)

    await screen.findByText(text.validation.descriptionTooLong)
    await waitFor(() => expect(description).toHaveFocus())
  })

  it('says the name is already used on 409 and keeps the values', async () => {
    server.use(
      handlers.subjects([]),
      http.post(`${API}/subjects`, () => errorResponse(409, 'CONFLICT')),
    )
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, description, submit } = await openForm()

    await user.type(name, 'Algebra')
    await user.type(description, 'Unidad 1')
    await user.click(submit)

    expect(await screen.findByText(text.nameTaken)).toBeVisible()
    expect(name).toHaveValue('Algebra')
    expect(description).toHaveValue('Unidad 1')
  })

  it.each([
    ['a 422', () => errorResponse(422, 'VALIDATION_ERROR'), strings.errors.byCode.VALIDATION_ERROR],
    ['a 500', () => errorResponse(500, 'INTERNAL_ERROR'), strings.errors.byStatus.server],
    ['a network failure', () => HttpResponse.error(), strings.errors.network],
  ])('shows a Spanish error and keeps the values after %s', async (_name, response, message) => {
    server.use(
      handlers.subjects([]),
      http.post(`${API}/subjects`, () => response()),
    )
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, submit } = await openForm()

    await user.type(name, 'Algebra')
    await user.click(submit)

    expect(await screen.findByText(message)).toBeVisible()
    expect(name).toHaveValue('Algebra')
    expect(screen.queryByText('server side text')).not.toBeInTheDocument()
  })

  it('ends the session when the API answers 401', async () => {
    server.use(
      handlers.subjects([]),
      http.post(`${API}/subjects`, () => errorResponse(401, 'UNAUTHORIZED')),
    )
    const { currentLocation } = renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, submit } = await openForm()

    await user.type(name, 'Algebra')
    await user.click(submit)

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })

  it('disables the submit control while the request is pending', async () => {
    let calls = 0
    server.use(
      handlers.subjects([]),
      http.post(`${API}/subjects`, async () => {
        calls += 1
        await delay(150)
        return HttpResponse.json(subject(), { status: 201 })
      }),
    )
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, submit } = await openForm()

    await user.type(name, 'Algebra')
    await user.click(submit)

    await waitFor(() => expect(submit).toBeDisabled())
    await user.click(submit)
    await waitFor(() => expect(submit).toBeEnabled())
    expect(calls).toBe(1)
  })

  it('shows markup in a subject name literally', async () => {
    statefulSubjects()
    renderApp({ route: '/subjects', session: { user: teacherUser } })
    const { user, name, submit } = await openForm()

    await user.type(name, '<b>Negrita</b>')
    await user.click(submit)

    expect(await screen.findByRole('link', { name: '<b>Negrita</b>' })).toBeInTheDocument()
    expect(document.querySelector('main b')).toBeNull()
  })

  it('has no serious accessibility violation', async () => {
    server.use(handlers.subjects([subject()]))
    const { container } = renderApp({ route: '/subjects', session: { user: teacherUser } })
    await screen.findByRole('textbox', { name: text.name })

    await expectNoSeriousA11yViolations(container)
  })
})
