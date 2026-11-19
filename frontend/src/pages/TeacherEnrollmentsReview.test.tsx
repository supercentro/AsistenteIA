import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, enrollmentItem, errorResponse, teacherUser } from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, serveSubject } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.enrollments
const ENROLLMENTS = `${API}/subjects/${SUBJECT.id}/enrollments`

const ana = () => enrollmentItem({ id: 'e1', student_id: 's1', student_email: 'ana@example.com' })
const beto = () => enrollmentItem({ id: 'e2', student_id: 's2', student_email: 'beto@example.com' })

async function enroll(email: string) {
  const user = userEvent.setup()
  const field = await screen.findByRole('textbox', { name: text.form.field })
  await user.type(field, email)
  await user.click(screen.getByRole('button', { name: text.form.submit }))
  return { user, field }
}

describe('Review: a removal that answers 404 may mean that the subject is gone', () => {
  it('shows the not-found view when the subject no longer exists', async () => {
    serveSubject([], [ana()])
    let subjectCalls = 0
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}`, () => {
        subjectCalls += 1
        return subjectCalls === 1 ? HttpResponse.json(SUBJECT) : errorResponse(404, 'NOT_FOUND')
      }),
      http.delete(`${ENROLLMENTS}/:studentId`, () => errorResponse(404, 'NOT_FOUND')),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: text.remove.action('ana@example.com') }),
    )

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(
      await screen.findByRole('heading', { name: strings.materials.notFound.title }),
    ).toBeVisible()
  })

  it('keeps the page and the notice when only the enrollment was gone', async () => {
    const state = serveSubject([], [ana(), beto()])
    server.use(
      http.delete(`${ENROLLMENTS}/:studentId`, () => {
        state.enrollments = state.enrollments.filter((item) => item.student_id !== 's1')
        return errorResponse(404, 'NOT_FOUND')
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: text.remove.action('ana@example.com') }),
    )

    await user.click(screen.getByRole('button', { name: text.remove.confirm }))

    expect(await screen.findByText(text.remove.gone)).toBeVisible()
    expect(screen.queryByText('ana@example.com')).not.toBeInTheDocument()
    expect(screen.getByText('beto@example.com')).toBeVisible()
  })
})

describe('Review: enrolling while the list is not loaded never shows a one-row list', () => {
  it('loads the whole list after enrolling when the list had failed', async () => {
    const state = serveSubject([], [ana(), beto()])
    let listCalls = 0
    server.use(
      http.get(ENROLLMENTS, () => {
        listCalls += 1
        return listCalls <= 2
          ? errorResponse(500, 'INTERNAL_ERROR')
          : HttpResponse.json(state.enrollments)
      }),
      http.post(ENROLLMENTS, () => {
        const created = enrollmentItem({
          id: 'new',
          student_id: 's3',
          student_email: 'carla@example.com',
        })
        state.enrollments.push(created)
        return HttpResponse.json(created, { status: 201 })
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(strings.errors.byStatus.server)

    await enroll('carla@example.com')

    expect(await screen.findByText('ana@example.com')).toBeVisible()
    expect(screen.getByText('beto@example.com')).toBeVisible()
    expect(screen.getByText('carla@example.com')).toBeVisible()
  })

  it('shows the whole list, not only the new student, when enrolling during the first load', async () => {
    const state = serveSubject([], [ana()])
    server.use(
      http.get(ENROLLMENTS, async () => {
        await delay(400)
        return HttpResponse.json(state.enrollments)
      }),
      http.post(ENROLLMENTS, () => {
        const created = enrollmentItem({
          id: 'new',
          student_id: 's3',
          student_email: 'carla@example.com',
        })
        state.enrollments.push(created)
        return HttpResponse.json(created, { status: 201 })
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    await enroll('carla@example.com')

    expect(await screen.findByText('ana@example.com')).toBeVisible()
    expect(await screen.findByText('carla@example.com')).toBeVisible()
  })
})

describe('Review: stale messages and assertions that prove the behaviour', () => {
  it('clears the enrollment error when the teacher edits the field', async () => {
    serveSubject([], [])
    server.use(http.post(ENROLLMENTS, () => errorResponse(409, 'CONFLICT')))
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const { user, field } = await enroll('ana@example.com')
    await screen.findByText(text.errors.alreadyEnrolled)

    await user.type(field, 'x')

    expect(screen.queryByText(text.errors.alreadyEnrolled)).not.toBeInTheDocument()
  })

  it('renders the neutral 404 message without any word about teachers', async () => {
    serveSubject([], [])
    server.use(http.post(ENROLLMENTS, () => errorResponse(404, 'NOT_FOUND')))
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await enroll('alguien@example.com')

    const alert = await screen.findByText(text.errors.notFound)

    expect(alert.closest('[role="alert"]')?.textContent).not.toMatch(/docente|profesor|teacher/i)
  })

  it('sends a single request when Enter is pressed twice in the field', async () => {
    serveSubject([], [])
    let calls = 0
    server.use(
      http.post(ENROLLMENTS, async () => {
        calls += 1
        await delay(200)
        return HttpResponse.json(enrollmentItem({ id: 'new', student_email: 'c@example.com' }), {
          status: 201,
        })
      }),
    )
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    const user = userEvent.setup()
    const field = await screen.findByRole('textbox', { name: text.form.field })
    await user.type(field, 'c@example.com')

    await user.keyboard('{Enter}{Enter}')

    await waitFor(() => expect(screen.getByText('c@example.com', { exact: true })).toBeVisible())
    expect(calls).toBe(1)
  })

  it('has no serious accessibility violation in the empty, error and confirmation states', async () => {
    serveSubject([], [ana()])
    const { container } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText('ana@example.com')
    server.use(http.post(ENROLLMENTS, () => errorResponse(409, 'CONFLICT')))
    const user = userEvent.setup()

    await user.type(screen.getByRole('textbox', { name: text.form.field }), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: text.form.submit }))
    await screen.findByText(text.errors.alreadyEnrolled)
    await expectNoSeriousA11yViolations(container)

    await user.click(screen.getByRole('button', { name: text.remove.action('ana@example.com') }))
    await screen.findByRole('group', { name: text.remove.question('ana@example.com') })
    await expectNoSeriousA11yViolations(container)
  })

  it('has no serious accessibility violation with no enrolled student', async () => {
    serveSubject([], [])
    const { container } = renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
    await screen.findByText(text.empty)

    await expectNoSeriousA11yViolations(container)
  })
})
