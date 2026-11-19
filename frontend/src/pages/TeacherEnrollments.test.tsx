import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import {
  API,
  documentItem,
  enrollmentItem,
  errorBody,
  errorResponse,
  studentUser,
  teacherUser,
} from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, serveSubject } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.enrollments
const ENROLLMENTS = `${API}/subjects/${SUBJECT.id}/enrollments`

function ana() {
  return enrollmentItem({ id: 'e1', student_id: 's1', student_email: 'ana@example.com' })
}
function beto() {
  return enrollmentItem({ id: 'e2', student_id: 's2', student_email: 'beto@example.com' })
}

async function openPage(initial = [ana(), beto()]) {
  const state = serveSubject([], initial)
  const view = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
  await screen.findByRole('heading', { name: text.heading })
  return { state, ...view }
}

async function fillAndSubmit(value: string) {
  const user = userEvent.setup()
  const field = await screen.findByRole('textbox', { name: text.form.field })
  await user.clear(field)
  if (value) {
    await user.type(field, value)
  }
  await user.click(screen.getByRole('button', { name: text.form.submit }))
  return { user, field }
}

describe('The enrolled students of the subject page', () => {
  it('lists the students in the order received, by e-mail', async () => {
    await openPage()

    const list = await screen.findByRole('list', { name: text.listLabel })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('ana@example.com')
    expect(rows[1]).toHaveTextContent('beto@example.com')
  })

  it('shows an empty state when nobody is enrolled', async () => {
    await openPage([])

    expect(await screen.findByText(text.empty)).toBeVisible()
    expect(screen.getByRole('textbox', { name: text.form.field })).toBeVisible()
  })

  it('shows a loading state while the list is requested', async () => {
    serveSubject()
    server.use(
      http.get(ENROLLMENTS, async () => {
        await delay(150)
        return HttpResponse.json([ana()])
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(text.loading)).toBeVisible()
    expect(await screen.findByText('ana@example.com')).toBeVisible()
  })

  it('shows an error with a retry control when the list fails, and recovers', async () => {
    serveSubject([documentItem()])
    let calls = 0
    server.use(
      http.get(ENROLLMENTS, () => {
        calls += 1
        return calls <= 2 ? errorResponse(500, 'INTERNAL_ERROR') : HttpResponse.json([ana()])
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(await screen.findByText('apuntes.pdf')).toBeVisible()
    await userEvent.setup().click(
      within(screen.getByRole('region', { name: text.heading })).getByRole('button', {
        name: strings.states.retry,
      }),
    )

    expect(await screen.findByText('ana@example.com')).toBeVisible()
  })

  it.each([
    [404, 'NOT_FOUND', strings.materials.notFound.title],
    [403, 'FORBIDDEN', strings.forbidden.title],
  ])('shows the matching view when the list answers %s', async (status, code, title) => {
    serveSubject()
    server.use(http.get(ENROLLMENTS, () => errorResponse(status, code)))
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
    expect(screen.queryByRole('heading', { name: text.heading })).not.toBeInTheDocument()
  })

  it('does not show the section to a student and sends no enrollment request', async () => {
    const state = serveSubject([], [ana()])
    renderApp({ route: SUBJECT_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
    expect(state.enrollmentCalls).toBe(0)
  })

  it('ends the session when the list answers 401, without flashing an error', async () => {
    serveSubject()
    server.use(http.get(ENROLLMENTS, () => errorResponse(401, 'UNAUTHORIZED')))
    const { currentLocation } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.errors.byStatus.unauthorized)).not.toBeInTheDocument()
  })

  it('shows an e-mail with markup or long text as text that wraps', async () => {
    const tricky = `<b>x</b>${'a'.repeat(120)}@example.com`
    await openPage([enrollmentItem({ student_email: tricky })])

    const row = await screen.findByRole('listitem')
    expect(row.querySelector('b')).toBeNull()
    expect(within(row).getByText(tricky).closest('p')?.className).toContain('break-words')
    expect(within(row).getByText(tricky).tagName).toBe('BDI')
  })

  it('has no serious accessibility violation', async () => {
    const { container } = await openPage()
    await screen.findByText('ana@example.com')

    await expectNoSeriousA11yViolations(container)
  })
})

describe('Enrolling a student by e-mail', () => {
  function acceptEnrollment(state: { enrollments: ReturnType<typeof ana>[] }, bodies: unknown[]) {
    server.use(
      http.post(ENROLLMENTS, async ({ request }) => {
        const body = (await request.json()) as { student_email: string }
        bodies.push(body)
        const created = enrollmentItem({
          id: 'new',
          student_id: 's3',
          student_email: body.student_email.toLowerCase(),
        })
        state.enrollments.push(created)
        return HttpResponse.json(created, { status: 201 })
      }),
    )
  }

  it('sends the e-mail as typed, adds the student with the returned e-mail and clears the field', async () => {
    const { state } = await openPage()
    const bodies: unknown[] = []
    acceptEnrollment(state, bodies)

    const { field } = await fillAndSubmit('Carla@Example.com')

    expect(await screen.findByText('carla@example.com')).toBeVisible()
    expect(bodies).toEqual([{ student_email: 'Carla@Example.com' }])
    await waitFor(() => expect(field).toHaveValue(''))
  })

  it('tells that the student must already have an account', async () => {
    await openPage()
    expect(screen.getByText(/ya debe existir/)).toBeVisible()
  })

  it.each([
    ['empty', '', strings.auth.validation.required],
    ['malformed', 'sin-arroba', strings.auth.validation.emailInvalid],
    ['non-ASCII', 'año@example.com', strings.auth.validation.emailAscii],
    ['too long', `${'a'.repeat(244)}@example.com`, strings.auth.validation.emailTooLong],
  ])('sends nothing for an %s e-mail and focuses the field', async (_name, value, message) => {
    const { state } = await openPage()
    const bodies: unknown[] = []
    acceptEnrollment(state, bodies)

    const { field } = await fillAndSubmit(value)

    const error = await screen.findByText(message)
    expect(bodies).toEqual([])
    await waitFor(() => expect(field).toHaveFocus())
    expect(field.getAttribute('aria-describedby')).toContain(error.id)
  })

  it('answers a 404 with one neutral message, keeps the value and checks the subject again', async () => {
    const { state } = await openPage()
    server.use(http.post(ENROLLMENTS, () => errorResponse(404, 'NOT_FOUND')))
    const before = state.subjectCalls

    const { field } = await fillAndSubmit('nadie@example.com')

    expect(await screen.findByText(text.errors.notFound)).toBeVisible()
    expect(field).toHaveValue('nadie@example.com')
    await waitFor(() => expect(state.subjectCalls).toBeGreaterThan(before))
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('shows the not-found view when the check shows that the subject is gone', async () => {
    serveSubject()
    let subjectCalls = 0
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => {
        subjectCalls += 1
        return subjectCalls === 1 ? HttpResponse.json(SUBJECT) : errorResponse(404, 'NOT_FOUND')
      }),
      http.post(ENROLLMENTS, () => errorResponse(404, 'NOT_FOUND')),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { name: text.heading })

    await fillAndSubmit('nadie@example.com')

    expect(
      await screen.findByRole('heading', { name: strings.materials.notFound.title }),
    ).toBeVisible()
  })

  it('shows the already-enrolled message on 409 and leaves the list as it was', async () => {
    await openPage()
    server.use(http.post(ENROLLMENTS, () => errorResponse(409, 'CONFLICT')))

    const { field } = await fillAndSubmit('ana@example.com')

    expect(await screen.findByText(text.errors.alreadyEnrolled)).toBeVisible()
    expect(field).toHaveValue('ana@example.com')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it.each([
    ['a 422', () => errorResponse(422, 'VALIDATION_ERROR'), strings.errors.byCode.VALIDATION_ERROR],
    [
      'a 429 with Retry-After',
      () => errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '6' }),
      strings.errors.rateLimitedIn(6),
    ],
    ['a 429', () => errorResponse(429, 'RATE_LIMITED'), strings.errors.byCode.RATE_LIMITED],
    ['a 500', () => errorResponse(500, 'INTERNAL_ERROR'), strings.errors.byStatus.server],
    ['a network failure', () => HttpResponse.error(), strings.errors.network],
  ])('shows a Spanish error and keeps the value after %s', async (_name, respond, message) => {
    await openPage()
    server.use(http.post(ENROLLMENTS, () => respond()))

    const { field } = await fillAndSubmit('carla@example.com')

    expect(await screen.findByText(message)).toBeVisible()
    expect(field).toHaveValue('carla@example.com')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('shows the forbidden view when enrolling answers 403', async () => {
    await openPage()
    server.use(http.post(ENROLLMENTS, () => errorResponse(403, 'FORBIDDEN')))

    await fillAndSubmit('carla@example.com')

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
  })

  it('ends the session when enrolling answers 401', async () => {
    const { currentLocation } = await openPage()
    server.use(http.post(ENROLLMENTS, () => errorResponse(401, 'UNAUTHORIZED')))

    await fillAndSubmit('carla@example.com')

    await waitFor(() => expect(currentLocation()).toBe('/login'))
  })

  it('never shows or logs the typed e-mail or the server message', async () => {
    await openPage()
    const logged: string[] = []
    const originals = { warn: console.warn, error: console.error, log: console.log }
    console.warn = (...args: unknown[]) => logged.push(args.join(' '))
    console.error = (...args: unknown[]) => logged.push(args.join(' '))
    console.log = (...args: unknown[]) => logged.push(args.join(' '))
    server.use(
      http.post(ENROLLMENTS, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'secreto@example.com no existe'), { status: 404 }),
      ),
    )
    try {
      await fillAndSubmit('secreto@example.com')
      await screen.findByText(text.errors.notFound)
    } finally {
      Object.assign(console, originals)
    }

    expect(screen.queryByText(/no existe/)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('secreto@example.com no existe')
    expect(logged.join('\n')).not.toContain('secreto@example.com')
  })

  it('disables the submit control while the request is pending', async () => {
    await openPage()
    let calls = 0
    server.use(
      http.post(ENROLLMENTS, async () => {
        calls += 1
        await delay(150)
        return HttpResponse.json(enrollmentItem({ id: 'new', student_email: 'c@example.com' }), {
          status: 201,
        })
      }),
    )

    const { user } = await fillAndSubmit('c@example.com')
    const submit = screen.getByRole('button', {
      name: new RegExp(`${text.form.submitting}|${text.form.submit}`),
    })
    await waitFor(() => expect(submit).toBeDisabled())
    await user.click(submit)

    await waitFor(() => expect(submit).toBeEnabled())
    expect(calls).toBe(1)
  })
})

describe('Removing an enrollment', () => {
  function removalHandler(onCall?: (id: string) => void, status = 204) {
    server.use(
      http.delete(`${ENROLLMENTS}/:studentId`, ({ params }) => {
        onCall?.(String(params.studentId))
        return status === 204
          ? new HttpResponse(null, { status: 204 })
          : errorResponse(
              status,
              { 404: 'NOT_FOUND', 403: 'FORBIDDEN' }[status] ?? 'INTERNAL_ERROR',
            )
      }),
    )
  }

  async function ask(email = 'ana@example.com') {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: text.remove.action(email) }))
    return user
  }

  it('says that nothing is deleted and that enrolling again restores the conversations', async () => {
    await openPage()
    let calls = 0
    removalHandler(() => (calls += 1))

    await ask()

    const panel = screen.getByRole('group', { name: text.remove.question('ana@example.com') })
    expect(panel).toHaveTextContent(/No se borra nada/)
    expect(panel).toHaveTextContent(/vuelve a inscribir/)
    expect(panel).toHaveTextContent(/dejará de ver/)
    expect(panel).not.toHaveTextContent(/irreversible|no se puede deshacer/i)
    expect(calls).toBe(0)
  })

  it('deletes after confirming, removes the row and moves the focus to the section heading', async () => {
    const { state } = await openPage()
    const ids: string[] = []
    removalHandler((id) => {
      ids.push(id)
      state.enrollments = state.enrollments.filter((item) => item.student_id !== id)
    })
    const user = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    await waitFor(() => expect(screen.queryByText('ana@example.com')).not.toBeInTheDocument())
    expect(ids).toEqual(['s1'])
    expect(screen.getByText('beto@example.com')).toBeVisible()
    const heading = screen.getByRole('heading', { name: text.heading })
    await waitFor(() => expect(heading).toHaveFocus())
  })

  it('cancelling sends nothing and keeps the student', async () => {
    await openPage()
    let calls = 0
    removalHandler(() => (calls += 1))
    const user = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.cancel }))

    expect(calls).toBe(0)
    expect(screen.getByText('ana@example.com')).toBeVisible()
    const trigger = screen.getByRole('button', { name: text.remove.action('ana@example.com') })
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('removes the row with a notice when the enrollment no longer existed (404)', async () => {
    const { state } = await openPage()
    // The enrollment was removed elsewhere: the list no longer holds it when it is requested again.
    removalHandler((id) => {
      state.enrollments = state.enrollments.filter((item) => item.student_id !== id)
    }, 404)
    const user = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByText(text.remove.gone)).toBeVisible()
    expect(screen.queryByText('ana@example.com')).not.toBeInTheDocument()
  })

  it('keeps the student and shows an error on that row when the removal fails', async () => {
    await openPage()
    removalHandler(undefined, 500)
    const user = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(screen.getByText('ana@example.com')).toBeVisible()
    expect(screen.getByRole('button', { name: text.remove.confirm })).toBeEnabled()
  })

  it('disables every confirm control while one removal is in flight', async () => {
    await openPage()
    server.use(
      http.delete(`${ENROLLMENTS}/:studentId`, async () => {
        await delay(300)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: text.remove.action('ana@example.com') }),
    )
    await user.click(screen.getByRole('button', { name: text.remove.action('beto@example.com') }))
    const confirms = screen.getAllByRole('button', { name: text.remove.confirm })

    await user.click(confirms[0] as HTMLElement)

    await waitFor(() => expect(confirms[1]).toBeDisabled())
  })

  it('shows the forbidden view when the removal answers 403', async () => {
    await openPage()
    removalHandler(undefined, 403)
    const user = await ask()

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
  })
})

describe('A list answer that was already on its way does not undo a change', () => {
  it('keeps an enrolled student shown when an older refresh answers afterwards', async () => {
    const { state, client } = await openPage([ana()])
    let calls = 0
    server.use(
      http.get(ENROLLMENTS, async () => {
        calls += 1
        await delay(900)
        return HttpResponse.json([ana()])
      }),
      http.post(ENROLLMENTS, async () => {
        const created = enrollmentItem({
          id: 'new',
          student_id: 's3',
          student_email: 'c@example.com',
        })
        state.enrollments.push(created)
        return HttpResponse.json(created, { status: 201 })
      }),
    )

    void client.invalidateQueries({ queryKey: ['enrollments'] })
    await waitFor(() => expect(calls).toBe(1))
    await fillAndSubmit('c@example.com')
    await screen.findByText('c@example.com')
    await act(() => new Promise((resolve) => setTimeout(resolve, 1200)))

    expect(screen.getByText('c@example.com')).toBeVisible()
  })

  it('does not bring back a removed student when an older refresh answers afterwards', async () => {
    const { client } = await openPage([ana(), beto()])
    server.use(
      http.get(ENROLLMENTS, async () => {
        await delay(300)
        return HttpResponse.json([ana(), beto()])
      }),
      http.delete(`${ENROLLMENTS}/:studentId`, () => new HttpResponse(null, { status: 204 })),
    )
    const user = userEvent.setup()

    void client.invalidateQueries({ queryKey: ['enrollments'] })
    await user.click(
      await screen.findByRole('button', { name: text.remove.action('ana@example.com') }),
    )
    await user.click(screen.getByRole('button', { name: text.remove.confirm }))
    await waitFor(() => expect(screen.queryByText('ana@example.com')).not.toBeInTheDocument())
    await act(() => new Promise((resolve) => setTimeout(resolve, 500)))

    expect(screen.queryByText('ana@example.com')).not.toBeInTheDocument()
  })
})
