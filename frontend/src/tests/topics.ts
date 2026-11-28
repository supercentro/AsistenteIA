import { HttpResponse, http } from 'msw'
import type {
  DocumentTopicsResponse,
  DocumentTopicsUpdate,
  TopicRankingResponse,
} from '../types/api'
import { API } from './api'
import { SUBJECT } from './materials'
import { server } from './server'

export const DOCUMENT_ID = '00000000-0000-4000-8000-00000000d0c1'
export const RANKING_PAGE = `/subjects/${SUBJECT.id}/activity/topics`
export const EDITOR_PAGE = `/subjects/${SUBJECT.id}/documents/${DOCUMENT_ID}/topics`
const RANKING_API = `${API}/subjects/${SUBJECT.id}/activity/topics`
const EDITOR_API = `${API}/subjects/${SUBJECT.id}/documents/${DOCUMENT_ID}/topics`

type Ranked = TopicRankingResponse['topics'][number]

export function ranked(overrides: Partial<Ranked> = {}): Ranked {
  return {
    topic_id: '00000000-0000-4000-8000-000000000001',
    title: 'Modelo relacional',
    document_id: DOCUMENT_ID,
    filename: 'unidad-1.pdf',
    start_page: 1,
    end_page: 4,
    counted_since: '2026-01-05',
    answers: 20,
    also_in: [],
    ...overrides,
  }
}

export function ranking(overrides: Partial<TopicRankingResponse> = {}): TopicRankingResponse {
  return {
    window: { start: '2026-01-05', end: '2026-03-29', granularity: 'week', weeks: 12 },
    minimum_group: 5,
    topics_defined: 3,
    topics: [
      ranked(),
      ranked({
        topic_id: '00000000-0000-4000-8000-000000000002',
        title: 'Formas normales',
        filename: 'unidad-2.pdf',
        start_page: 5,
        end_page: 9,
        answers: 10,
        also_in: ['repaso.pdf'],
      }),
    ],
    documents_without_topics: [],
    restarted_documents: [],
    ...overrides,
  }
}

export function serveRanking(body: TopicRankingResponse = ranking()) {
  const state = { calls: 0, urls: [] as string[] }
  server.use(
    http.get(RANKING_API, ({ request }) => {
      state.calls += 1
      state.urls.push(request.url)
      return HttpResponse.json(body)
    }),
  )
  return state
}

export function failRanking(status: number) {
  server.use(
    http.get(RANKING_API, () =>
      HttpResponse.json({ code: 'SOMETHING', message: 'server text' }, { status }),
    ),
  )
}

export function documentTopics(
  overrides: Partial<DocumentTopicsResponse> = {},
): DocumentTopicsResponse {
  return {
    document_id: DOCUMENT_ID,
    filename: 'unidad-1.pdf',
    editable: true,
    reason: null,
    last_page: 10,
    revision: 0,
    source: null,
    counting_from: null,
    topics: [],
    ...overrides,
  }
}

export const savedTopics = (overrides: Partial<DocumentTopicsResponse> = {}) =>
  documentTopics({
    revision: 2,
    source: 'teacher',
    topics: [
      { title: 'Modelo', start_page: 1, end_page: 4 },
      { title: 'Formas', start_page: 5, end_page: 8 },
    ],
    ...overrides,
  })

/** Serves one document; `fail` makes the next writes answer with that status and reason. */
export function serveDocumentTopics(initial: DocumentTopicsResponse = documentTopics()) {
  const state = {
    current: initial,
    reads: 0,
    writes: [] as DocumentTopicsUpdate[],
    fail: null as { status: number; reason: string } | null,
    /** Status of the next reads, and a promise the next write waits for. */
    failRead: null as number | null,
    hold: null as Promise<void> | null,
  }
  server.use(
    http.get(EDITOR_API, () => {
      state.reads += 1
      if (state.failRead) {
        return HttpResponse.json(
          { code: 'SERVICE_UNAVAILABLE', message: 'server text' },
          { status: state.failRead },
        )
      }
      return HttpResponse.json(state.current)
    }),
    http.put(EDITOR_API, async ({ request }) => {
      const body = (await request.json()) as DocumentTopicsUpdate
      state.writes.push(body)
      if (state.hold) await state.hold
      if (state.fail) {
        return HttpResponse.json(
          { code: 'CONFLICT', message: 'server text', details: { reason: state.fail.reason } },
          { status: state.fail.status },
        )
      }
      state.current = {
        ...state.current,
        revision: body.revision + 1,
        source: 'teacher',
        topics: body.topics,
      }
      return HttpResponse.json(state.current)
    }),
  )
  return state
}
