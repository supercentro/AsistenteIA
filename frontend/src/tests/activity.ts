import { HttpResponse, http } from 'msw'
import type { ActivityResponse } from '../types/api'
import { API } from './api'
import { SUBJECT } from './materials'
import { server } from './server'

export const ACTIVITY_PAGE = `/subjects/${SUBJECT.id}/activity`
const ACTIVITY_URL = `${API}/subjects/${SUBJECT.id}/activity`

/** Fictitious figures: one withheld week, one withheld document and one deleted document. */
export function activity(overrides: Partial<ActivityResponse> = {}): ActivityResponse {
  return {
    window: { start: '2026-03-02', end: '2026-03-29', granularity: 'week', weeks: 4 },
    minimum_group: 5,
    enrolled_students: 12,
    active_students: 8,
    questions: [
      { period_start: '2026-03-02', count: 14 },
      { period_start: '2026-03-09', count: 6 },
      { period_start: '2026-03-16', count: null },
      { period_start: '2026-03-23', count: 9 },
    ],
    no_material_rate: 0.2,
    no_cited_source_rate: 0.45,
    documents: [
      {
        document_id: '66666666-6666-4666-8666-666666666666',
        filename: 'unidad-1.pdf',
        cited_appearances: 11,
      },
      { document_id: null, filename: 'unidad-vieja.pdf', cited_appearances: 6 },
      {
        document_id: '88888888-8888-4888-8888-888888888888',
        filename: 'unidad-2.pdf',
        cited_appearances: null,
      },
    ],
    suppressed: true,
    ...overrides,
  }
}

/** A normal answer: the 12 weeks that have ended (the weekly rows are the fictitious ones). */
export function fullWindow(): ActivityResponse {
  return activity({
    window: { start: '2025-12-15', end: '2026-03-08', granularity: 'week', weeks: 12 },
  })
}

/** Every week starts before the last unenrolment: no week, nothing but the enrolled count. */
export function noWeeks(): ActivityResponse {
  return activity({
    window: { start: '2026-04-06', end: '2026-04-05', granularity: 'week', weeks: 0 },
    active_students: null,
    questions: [],
    no_material_rate: null,
    no_cited_source_rate: null,
    documents: activity().documents.map((document) => ({ ...document, cited_appearances: null })),
  })
}

/** What the endpoint returns for a class with fewer than the minimum group of active students. */
export function allSuppressed(): ActivityResponse {
  return activity({
    active_students: null,
    questions: activity().questions.map((week) => ({ ...week, count: null })),
    no_material_rate: null,
    no_cited_source_rate: null,
    documents: activity().documents.map((document) => ({ ...document, cited_appearances: null })),
  })
}

/** Serves the activity of the test subject and records every request, with its query string. */
export function serveActivity(body: ActivityResponse = activity()) {
  const state = { calls: 0, searches: [] as string[] }
  server.use(
    http.get(ACTIVITY_URL, ({ request }) => {
      state.calls += 1
      state.searches.push(new URL(request.url).search)
      return HttpResponse.json(body)
    }),
  )
  return state
}

/** Counts the requests to the activity endpoint and answers with the given response. */
export function failActivity(status: number, code: string) {
  const state = { calls: 0 }
  server.use(
    http.get(ACTIVITY_URL, () => {
      state.calls += 1
      return HttpResponse.json({ code, message: 'server side text', details: null }, { status })
    }),
  )
  return state
}
