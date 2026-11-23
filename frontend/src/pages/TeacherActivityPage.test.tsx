import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { focusManager } from '@tanstack/react-query'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import {
  ACTIVITY_PAGE,
  activity,
  allSuppressed,
  failActivity,
  serveActivity,
} from '../tests/activity'
import { API, studentUser, teacherUser } from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, serveSubject } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.activity
const FLAG = 'VITE_TEACHER_ACTIVITY_ENABLED'

const ALLOWED_NEGATIONS = new Set(['documents.note']) // «no mide comprensión ni uso del material»
const JUDGEMENT =
  /(?<![\p{L}])(calidad|err(or|ór|óne|one)\p{L}*|incorrect\p{L}*|correct\p{L}*|equivoc\p{L}*|acert\p{L}*|fall(a|e|i|o)\p{L}*|buen\p{L}*|mal(o|a|os|as)?|mejor\p{L}*|peor\p{L}*|útil\p{L}*|util(es|idad)?|aprend\p{L}*|entend\p{L}*|entien\p{L}*|compren\p{L}*|comprens\p{L}*|rendimiento|desempeño|us(o|os|ó|ado|ada|ados|adas|an|aron)|utiliz\p{L}*|destac\p{L}*|compromet\p{L}*|particip\p{L}*)(?![\p{L}])/iu

/** Every string of the copy, with the functions called on sample arguments, keyed by its path. */
function everyString(node: unknown, path = ''): Array<[string, string]> {
  if (typeof node === 'string') return [[path, node]]
  if (typeof node === 'function') {
    return [
      [path, String((node as (...args: unknown[]) => unknown)('01/03/2026', '29/03/2026', 5))],
    ]
  }
  if (node && typeof node === 'object') {
    return Object.entries(node).flatMap(([key, value]) =>
      everyString(value, path ? `${path}.${key}` : key),
    )
  }
  return []
}

function flagOn() {
  vi.stubEnv(FLAG, 'true')
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('TeacherActivityPage - the owner reads the figures', () => {
  it('shows the cards, the weekly table, the shares and the documents', async () => {
    flagOn()
    serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { level: 1, name: text.title })).toBeVisible()
    expect(screen.getByText(text.window('02/03/2026', '29/03/2026'))).toBeVisible()
    expect(screen.getByText(text.cards.enrolled).nextSibling).toHaveTextContent('12')
    expect(screen.getByText(text.cards.active).nextSibling).toHaveTextContent('8')
    const weekly = screen.getByRole('table', { name: text.weekly.caption })
    const rows = within(weekly).getAllByRole('row').slice(1)
    expect(rows.map((row) => within(row).getAllByRole('cell')[0]!.textContent)).toEqual([
      '02/03/2026',
      '09/03/2026',
      '16/03/2026',
      '23/03/2026',
    ])
    expect(within(rows[0]!).getAllByRole('cell')[1]).toHaveTextContent('14')
    expect(screen.getByText(text.shares.noMaterial).nextSibling).toHaveTextContent('20,0 %')
    expect(screen.getByText(text.shares.noCitedSource).nextSibling).toHaveTextContent('45,0 %')
    const documents = screen.getByRole('table', { name: text.documents.caption })
    expect(within(documents).getByText('unidad-vieja.pdf')).toBeVisible()
    expect(screen.getByText(text.note(5))).toBeVisible()
  })

  it('reads «Datos insuficientes» for a withheld figure, with no bar and no zero', async () => {
    flagOn()
    serveActivity()
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    const weekly = await screen.findByRole('table', { name: text.weekly.caption })
    const rows = within(weekly).getAllByRole('row').slice(1)
    const withheld = within(rows[2]!).getAllByRole('cell')[1]!
    expect(withheld).toHaveTextContent(text.insufficient)
    expect(withheld.textContent).not.toMatch(/\d/)
    expect(rows[2]!.querySelector('[data-bar]')).toBeNull()
    expect(rows[0]!.querySelector('[data-bar]')).not.toBeNull()
    const documents = screen.getByRole('table', { name: text.documents.caption })
    const last = within(documents).getAllByRole('row').at(-1)!
    expect(within(last).getAllByRole('cell')[1]).toHaveTextContent(text.insufficient)
    expect(container.querySelectorAll('[data-bar]')).toHaveLength(3 + 2 + 0) // 3 weeks, 2 shares
  })

  it('shows a rate of 0% as a real figure with its bar', async () => {
    flagOn()
    serveActivity(activity({ no_material_rate: 0 }))
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    const value = (await screen.findByText(text.shares.noMaterial)).nextSibling
    expect(value).toHaveTextContent('0,0 %')
    expect(value).not.toHaveTextContent(text.insufficient)
  })

  it('shows only the enrolled count and an explanation when everything is withheld', async () => {
    flagOn()
    serveActivity(allSuppressed())
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(text.allSuppressed)).toBeVisible()
    expect(screen.getByText(text.cards.enrolled).nextSibling).toHaveTextContent('12')
    expect(screen.getByText(text.cards.active).nextSibling).toHaveTextContent(text.insufficient)
    expect(container.querySelector('[data-bar]')).toBeNull()
    expect(screen.getByText(text.note(5))).toBeVisible()
  })
})

describe('TeacherActivityPage - one request and no comparison', () => {
  it('sends one request without query parameters', async () => {
    flagOn()
    const state = serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    await screen.findByRole('heading', { level: 1, name: text.title })
    expect(state.calls).toBe(1)
    expect(state.searches).toEqual([''])
  })

  it('does not ask again when the window regains focus or the connection returns', async () => {
    flagOn()
    const state = serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { level: 1, name: text.title })

    focusManager.setFocused(false)
    focusManager.setFocused(true)
    window.dispatchEvent(new Event('online'))
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(state.calls).toBe(1)
  })

  it('offers no date selector, export, comparison or change between weeks', async () => {
    flagOn()
    serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { level: 1, name: text.title })

    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.queryByLabelText(/fecha|desde|hasta|período/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /exportar|descargar|comparar/i })).toBeNull()
    expect(screen.queryByText(/%\s*(más|menos)|respecto|anterior|variación/i)).toBeNull()
  })

  it('asks again and shows the new answer, not the old one, after leaving and returning', async () => {
    flagOn()
    const user = userEvent.setup()
    serveSubject()
    let call = 0
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}/activity`, () => {
        call += 1
        return HttpResponse.json(activity({ enrolled_students: call === 1 ? 12 : 13 }))
      }),
    )
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    expect((await screen.findByText(text.cards.enrolled)).nextSibling).toHaveTextContent('12')

    await user.click(screen.getByRole('link', { name: text.back }))
    await screen.findByRole('heading', { level: 1 })
    await user.click(await screen.findByRole('link', { name: text.link }))

    await waitFor(() =>
      expect(screen.getByText(text.cards.enrolled).nextSibling).toHaveTextContent('13'),
    )
    expect(call).toBe(2)
  })
})

describe('TeacherActivityPage - switches and authorisation', () => {
  it('with the frontend switch off there is no route and no request', async () => {
    const state = serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: strings.notFound.title })).toBeVisible()
    expect(state.calls).toBe(0)
  })

  it('with the switch off the subject page has no link to the activity', async () => {
    serveSubject()
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('link', { name: text.link })).toBeNull()
  })

  it('a student gets the forbidden page without any request', async () => {
    flagOn()
    const state = serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: studentUser } })

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
    expect(state.calls).toBe(0)
  })

  it('a caller without a session is sent to the login page without any request', async () => {
    flagOn()
    const state = serveActivity()
    const { currentLocation } = renderApp({ route: ACTIVITY_PAGE })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(state.calls).toBe(0)
  })

  it.each([404, 422])('a %i from the API shows the same not-found view', async (status) => {
    flagOn()
    failActivity(status, status === 404 ? 'NOT_FOUND' : 'VALIDATION_ERROR')
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(strings.materials.notFound.title)).toBeVisible()
    expect(screen.queryByText('server side text')).toBeNull()
  })

  it('a 403 shows the forbidden page', async () => {
    flagOn()
    failActivity(403, 'FORBIDDEN')
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByRole('heading', { name: strings.forbidden.title })).toBeVisible()
  })

  it('a 401 ends the session without flashing an error', async () => {
    flagOn()
    failActivity(401, 'UNAUTHORIZED')
    const { currentLocation } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.errors.byStatus.unauthorized)).not.toBeInTheDocument()
  })
})

describe('TeacherActivityPage - states', () => {
  it('shows the loading state first', async () => {
    flagOn()
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}/activity`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 100))
        return HttpResponse.json(activity())
      }),
    )
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(screen.getByText(text.loading)).toBeVisible()
    expect(await screen.findByRole('heading', { level: 1, name: text.title })).toBeVisible()
  })

  it('shows an error with a retry control, once per attempt, and recovers', async () => {
    flagOn()
    const user = userEvent.setup()
    let call = 0
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}/activity`, () => {
        call += 1
        return call === 1
          ? HttpResponse.json(
              { code: 'SERVICE_UNAVAILABLE', message: 'x', details: null },
              { status: 503 },
            )
          : HttpResponse.json(activity())
      }),
    )
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    const alert = await screen.findByRole('alert')
    expect(call).toBe(1)
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }))

    expect(await screen.findByRole('heading', { level: 1, name: text.title })).toBeVisible()
    expect(call).toBe(2)
  })
})

describe('TeacherActivityPage - placement and wording', () => {
  it('links from the header of the subject page, outside the enrolments, and sends no activity request', async () => {
    flagOn()
    const user = userEvent.setup()
    const state = serveSubject()
    const activityState = serveActivity()
    renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })

    const link = await screen.findByRole('link', { name: text.link })
    expect(link).toHaveAttribute('href', `${SUBJECT_PAGE}/activity`)
    const enrolments = screen
      .getByRole('heading', { name: strings.enrollments.heading })
      .closest('section')!
    expect(enrolments.contains(link)).toBe(false)
    expect(link.closest('header')).not.toBeNull()
    expect(state.enrollmentCalls).toBeGreaterThan(0)
    await user.click(link)
    await screen.findByRole('heading', { level: 1, name: text.title })

    expect(activityState.calls).toBe(1)
    expect(screen.queryByRole('heading', { name: strings.enrollments.heading })).toBeNull()
    expect(screen.queryByRole('button', { name: /inscribir|quitar|dar de baja/i })).toBeNull()
  })

  it('uses no judgement word in any string of the page', () => {
    const strings = everyString(text)
    expect(strings.length).toBeGreaterThan(20)
    for (const [path, value] of strings) {
      if (ALLOWED_NEGATIONS.has(path)) continue
      expect(value, path).not.toMatch(JUDGEMENT)
    }
    expect(text.documents.note).toMatch(/no mide/)
    expect(text.shares.noCitedSourceNote).toMatch(/sin material/)
  })

  it.each([
    'correctas',
    'erróneas',
    'acertadas',
    'fallidas',
    'comprensión',
    'aprenden',
    'entienden',
    'más usados',
    'usado',
    'destacados',
    'buen desempeño',
    'mal citados',
    'participación baja',
  ])('the judgement scan catches «%s»', (word) => {
    expect(word).toMatch(JUDGEMENT)
  })

  it.each(['material', 'Respuestas sin fuente citada', 'Estudiantes activos', 'estudiantes'])(
    'the judgement scan lets «%s» through',
    (word) => {
      expect(word).not.toMatch(JUDGEMENT)
    },
  )

  it('draws each bar as wide as its figure relative to the largest week', async () => {
    flagOn()
    serveActivity()
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { level: 1, name: text.title })

    const widths = [...container.querySelectorAll<HTMLElement>('[data-bar]')].map(
      (bar) => bar.style.width,
    )

    expect(widths).toEqual(['100%', '43%', '64%', '20%', '45%']) // weeks of 14, 6 and 9 questions, then the 20 % and 45 % shares
  })

  it('puts the focus on the heading when the figures appear', async () => {
    flagOn()
    serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    const heading = await screen.findByRole('heading', { level: 1, name: text.title })

    await waitFor(() => expect(heading).toHaveFocus())
  })

  it('shows hostile, duplicated and deleted file names as plain text, one row each', async () => {
    flagOn()
    const hostile = '<img src=x onerror=alert(1)>\u202Egpj.pdf'
    serveActivity(
      activity({
        documents: [
          { document_id: null, filename: 'repetido.pdf', cited_appearances: 7 },
          { document_id: null, filename: 'repetido.pdf', cited_appearances: 5 },
          {
            document_id: '99999999-9999-4999-8999-999999999999',
            filename: hostile,
            cited_appearances: 9,
          },
          { document_id: null, filename: `${'x'.repeat(300)}.pdf`, cited_appearances: null },
        ],
      }),
    )
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    const table = await screen.findByRole('table', { name: text.documents.caption })

    expect(within(table).getAllByRole('row')).toHaveLength(5)
    expect(within(table).getByText(hostile)).toBeVisible()
    expect(container.querySelector('img')).toBeNull()
  })

  it('defines the active students and states what the privacy note covers', async () => {
    flagOn()
    serveActivity()
    renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })

    expect(await screen.findByText(text.cards.activeNote)).toBeVisible()
    expect(text.note(5)).toMatch(/cifras de actividad/)
  })
})

describe('TeacherActivityPage - accessibility', () => {
  it.each([
    ['loaded', () => activity()],
    ['all withheld', () => allSuppressed()],
    ['no documents', () => activity({ documents: [] })],
  ])('has no serious violation when %s', async (_name, build) => {
    flagOn()
    serveActivity(build())
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { level: 1, name: text.title })

    await expectNoSeriousA11yViolations(container)
  })

  it('has no serious violation in the error state', async () => {
    flagOn()
    failActivity(503, 'SERVICE_UNAVAILABLE')
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('alert')

    await expectNoSeriousA11yViolations(container)
  })

  it('hides every bar from assistive technology and keeps each figure as text', async () => {
    flagOn()
    serveActivity()
    const { container } = renderApp({ route: ACTIVITY_PAGE, session: { user: teacherUser } })
    await screen.findByRole('heading', { level: 1, name: text.title })

    const bars = container.querySelectorAll('[data-bar]')
    expect(bars.length).toBeGreaterThan(0)
    bars.forEach((bar) => expect(bar).toHaveAttribute('aria-hidden', 'true'))
    expect(screen.getByRole('table', { name: text.weekly.caption })).toBeVisible()
    expect(screen.getByRole('table', { name: text.documents.caption })).toBeVisible()
  })
})
