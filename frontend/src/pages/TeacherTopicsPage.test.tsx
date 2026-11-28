import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { ACTIVITY_PAGE, serveActivity } from '../tests/activity'
import { studentUser, teacherUser, documentItem } from '../tests/api'
import { SUBJECT_PAGE, serveSubject } from '../tests/materials'
import {
  DOCUMENT_ID,
  EDITOR_PAGE,
  RANKING_PAGE,
  failRanking,
  ranked,
  ranking,
  serveRanking,
} from '../tests/topics'
import { renderApp } from '../tests/utils'

const text = strings.topics.ranking
const owner = { user: teacherUser }

function flagsOn() {
  vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', 'true')
  vi.stubEnv('VITE_TEACHER_TOPICS_ENABLED', 'true')
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('TeacherTopicsPage - the owner reads the ranking', () => {
  it('shows a bar and a table row per topic with its document, pages and start', async () => {
    flagsOn()
    serveRanking()
    const { container } = renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByRole('heading', { level: 1, name: text.title })).toBeVisible()
    const table = screen.getByRole('table', { name: text.caption })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Modelo relacional')
    expect(rows[0]).toHaveTextContent('unidad-1.pdf')
    expect(rows[0]).toHaveTextContent(text.pages(1, 4))
    expect(rows[0]).toHaveTextContent('05/01/2026')
    expect(rows[0]).toHaveTextContent('20')
    expect(rows[1]).toHaveTextContent(text.alsoIn)
    expect(rows[1]).toHaveTextContent('repaso.pdf')
    const bars = container.querySelectorAll('[data-bar]')
    expect(bars).toHaveLength(2)
    for (const bar of bars) {
      expect(bar.closest('[aria-hidden="true"]')).not.toBeNull()
    }
    expect(screen.getByText(text.note(5))).toBeVisible()
    await expectNoSeriousA11yViolations(container)
  })

  it('sends one request without any parameter', async () => {
    flagsOn()
    const state = serveRanking()
    renderApp({ route: RANKING_PAGE, session: owner })

    await screen.findByRole('table', { name: text.caption })

    expect(state.calls).toBe(1)
    expect(new URL(state.urls[0]!).search).toBe('')
  })

  it('shows hostile titles as text', async () => {
    flagsOn()
    serveRanking(ranking({ topics: [ranked({ title: '<img src=x onerror=alert(1)>' })] }))
    const { container } = renderApp({ route: RANKING_PAGE, session: owner })

    await screen.findByRole('table', { name: text.caption })

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getAllByText('<img src=x onerror=alert(1)>').length).toBeGreaterThan(0)
  })
})

describe('TeacherTopicsPage - states', () => {
  it('explains where topics come from when there is none, and links to define them', async () => {
    flagsOn()
    serveRanking(
      ranking({
        topics_defined: 0,
        topics: [],
        documents_without_topics: [
          { document_id: DOCUMENT_ID, filename: 'apunte.pdf', reason: 'not_defined' },
          {
            document_id: '00000000-0000-4000-8000-00000000d0c2',
            filename: 'notas.md',
            reason: 'no_pages',
          },
        ],
      }),
    )
    renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByText(text.noTopics)).toBeVisible()
    expect(screen.getByRole('link', { name: text.define('apunte.pdf') })).toHaveAttribute(
      'href',
      EDITOR_PAGE,
    )
    expect(screen.getByText(text.reasons.no_pages)).toBeVisible()
    expect(screen.queryByRole('link', { name: text.define('notas.md') })).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('reads «Datos insuficientes» with no chart when nothing can be shown', async () => {
    flagsOn()
    serveRanking(ranking({ topics: [] }))
    const { container } = renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByText(strings.activity.insufficient)).toBeVisible()
    expect(container.querySelector('[data-bar]')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('says that there is no whole week yet', async () => {
    flagsOn()
    serveRanking(
      ranking({
        topics: [],
        window: { start: '2026-03-30', end: '2026-03-29', granularity: 'week', weeks: 0 },
      }),
    )
    renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByText(strings.activity.noWeeks)).toBeVisible()
  })

  it('names the documents that count from a later week', async () => {
    flagsOn()
    serveRanking(
      ranking({
        restarted_documents: [
          { document_id: DOCUMENT_ID, filename: 'cambiado.pdf', counting_from: '2026-03-30' },
        ],
      }),
    )
    renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByText(text.restartedItem('cambiado.pdf', '30/03/2026'))).toBeVisible()
  })

  it.each([404, 500])('handles a %s without showing server text', async (status) => {
    flagsOn()
    failRanking(status)
    renderApp({ route: RANKING_PAGE, session: owner })

    if (status === 404) {
      expect(await screen.findByText(strings.materials.notFound.title)).toBeVisible()
    } else {
      expect(await screen.findByRole('button', { name: strings.states.retry })).toBeVisible()
    }
    expect(screen.queryByText('server text')).toBeNull()
  })
})

describe('Topic pages - switches, roles and links', () => {
  it.each([
    ['true', undefined],
    [undefined, 'true'],
    ['true', '1'],
  ])('is off unless both switches are exactly true (%s, %s)', async (activity, topics) => {
    vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', activity)
    vi.stubEnv('VITE_TEACHER_TOPICS_ENABLED', topics)
    const state = serveRanking()
    renderApp({ route: RANKING_PAGE, session: owner })

    expect(await screen.findByText(strings.notFound.title)).toBeVisible()
    expect(state.calls).toBe(0)
  })

  it('shows the forbidden page to a student without any request', async () => {
    flagsOn()
    const state = serveRanking()
    renderApp({ route: RANKING_PAGE, session: { user: studentUser } })

    expect(await screen.findByText(strings.forbidden.title)).toBeVisible()
    expect(state.calls).toBe(0)
  })

  it('links from the dashboard without asking for topics', async () => {
    flagsOn()
    serveActivity()
    const state = serveRanking()
    renderApp({ route: ACTIVITY_PAGE, session: owner })

    expect(await screen.findByRole('link', { name: strings.topics.link })).toHaveAttribute(
      'href',
      RANKING_PAGE,
    )
    await waitFor(() => expect(state.calls).toBe(0))
  })

  it('links each ready PDF of the document list to its topics, and nothing else', async () => {
    flagsOn()
    serveSubject([
      documentItem({ id: DOCUMENT_ID, filename: 'listo.pdf', status: 'ready' }),
      documentItem({ id: 'd2', filename: 'pendiente.pdf', status: 'pending' }),
      documentItem({
        id: 'd3',
        filename: 'notas.md',
        status: 'ready',
        content_type: 'text/markdown',
      }),
    ])
    renderApp({ route: SUBJECT_PAGE, session: owner })

    expect(
      await screen.findByRole('link', { name: strings.topics.documentLink('listo.pdf') }),
    ).toHaveAttribute('href', EDITOR_PAGE)
    expect(
      screen.queryByRole('link', { name: strings.topics.documentLink('pendiente.pdf') }),
    ).toBeNull()
    expect(screen.queryByRole('link', { name: strings.topics.documentLink('notas.md') })).toBeNull()
  })

  it('shows no topic link while the switch is off', async () => {
    vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', 'true')
    serveSubject([documentItem({ id: DOCUMENT_ID, filename: 'listo.pdf', status: 'ready' })])
    renderApp({ route: SUBJECT_PAGE, session: owner })

    await screen.findByText('listo.pdf')
    expect(
      screen.queryByRole('link', { name: strings.topics.documentLink('listo.pdf') }),
    ).toBeNull()
  })
})

describe('Topic copy', () => {
  /** Labels that present a topic as hard or learned; the note may only deny it. */
  const JUDGEMENT = /(?<![\p{L}])(dific|difíc|compren|entend|entien|aprend|domin)/iu

  it('presents no figure as difficulty or understanding', () => {
    const labels: string[] = []
    const walk = (node: unknown, key: string) => {
      if (key === 'note') return
      if (typeof node === 'string') labels.push(node)
      else if (typeof node === 'function') {
        labels.push(String((node as (...a: unknown[]) => unknown)('a', 'b', 5)))
      } else if (node && typeof node === 'object') {
        Object.entries(node).forEach(([k, v]) => walk(v, k))
      }
    }
    walk(strings.topics, '')

    expect(labels.filter((label) => JUDGEMENT.test(label))).toEqual([])
    expect(text.note(5)).toMatch(/no mide dificultad ni comprensión/i)
    expect(text.note(5)).toMatch(/no garantiza el anonimato/i)
  })
})
