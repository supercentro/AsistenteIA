import { HttpResponse, http } from 'msw'
import { API, documentItem, subject } from './api'
import { server } from './server'
import type { Document, Enrollment } from '../types/api'

export const SUBJECT = subject()
export const SUBJECT_PAGE = `/subjects/${SUBJECT.id}`

/** Every `error_code` of the closed list in docs/api-spec.yml. */
export const ERROR_CODES = [
  'NO_EXTRACTABLE_TEXT',
  'ENCRYPTED_PDF',
  'CORRUPT_FILE',
  'TOO_MANY_PAGES',
  'TEXT_TOO_LARGE',
  'TOO_MANY_CHUNKS',
  'PROCESSING_TIMEOUT',
  'RESOURCE_LIMIT_EXCEEDED',
  'EMBEDDING_FAILED',
  'PROCESSING_INTERRUPTED',
  'JOB_EXPIRED',
  'PROCESSING_FAILED',
] as const

/**
 * Serves the subject and a document list the test can change, and counts the list requests.
 * `uploads` receives the document the upload endpoint would store.
 */
export function serveSubject(initial: Document[] = [], initialEnrollments: Enrollment[] = []) {
  const state = {
    documents: [...initial],
    enrollments: [...initialEnrollments],
    listCalls: 0,
    subjectCalls: 0,
    enrollmentCalls: 0,
  }
  server.use(
    http.get(`${API}/subjects/${SUBJECT.id}/enrollments`, () => {
      state.enrollmentCalls += 1
      return HttpResponse.json(state.enrollments)
    }),
    http.get(`${API}/subjects/${SUBJECT.id}`, () => {
      state.subjectCalls += 1
      return HttpResponse.json(SUBJECT)
    }),
    http.get(`${API}/subjects/${SUBJECT.id}/documents`, () => {
      state.listCalls += 1
      return HttpResponse.json(state.documents)
    }),
  )
  return state
}

/** An empty enrollment list for any subject, for tests that only care about other parts of the page. */
export const noEnrollments = () =>
  http.get(`${API}/subjects/:id/enrollments`, () => HttpResponse.json([]))

export function pdf(overrides: Partial<Document> = {}): Document {
  return documentItem(overrides)
}

/**
 * Reads a multipart body as text. `request.formData()` cannot be used: jsdom's `File` is not the
 * one undici's parser expects, so the fields are read from the raw body instead.
 */
export async function readMultipart(request: Request): Promise<{
  fields: string[]
  filename: string | null
  content: string
}> {
  const raw = await request.text()
  const fields = Array.from(raw.matchAll(/Content-Disposition: form-data; name="([^"]+)"/gi)).map(
    (match) => match[1] as string,
  )
  const filename = /filename="([^"]*)"/i.exec(raw)?.[1] ?? null
  const content = raw.split(/\r?\n\r?\n/)[1]?.split(/\r?\n--/)[0] ?? ''
  return { fields, filename, content }
}
