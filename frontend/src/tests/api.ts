import { HttpResponse, http } from 'msw'
import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import type { ApiErrorBody, Document, Subject, TokenResponse, User } from '../types/api'

/** Base URL used by every test (set through `test.env` in vite.config.ts). */
export const API = 'http://localhost:8000/api/v1'

/** A student whose consent is current: the gate lets every student route through. */
export const studentUser: User = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Ana Estudiante',
  email: 'ana@example.com',
  role: 'student',
  consent_version: PRIVACY_POLICY_VERSION,
  consent_accepted_at: '2026-11-17T10:00:00Z',
}

/** A student who never accepted the privacy policy. */
export const unconsentedStudent: User = {
  ...studentUser,
  consent_version: null,
  consent_accepted_at: null,
}

/** A student whose accepted version is not the current one. */
export const outdatedStudent: User = {
  ...studentUser,
  consent_version: '2025-01-v0',
  consent_accepted_at: '2025-01-10T10:00:00Z',
}

export const teacherUser: User = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Tomas Docente',
  email: 'tomas@example.com',
  role: 'teacher',
  consent_version: '2026-10-v1',
  consent_accepted_at: '2026-10-28T10:00:00Z',
}

export const TOKEN_VALUE = 'eyJhbGciOiJIUzI1NiJ9.test-secret-payload.test-secret-signature'

export function tokenResponse(expiresIn = 3600): TokenResponse {
  return { access_token: TOKEN_VALUE, token_type: 'bearer', expires_in: expiresIn }
}

export function subject(overrides: Partial<Subject> = {}): Subject {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    name: 'Algebra',
    description: null,
    teacher_id: teacherUser.id,
    created_at: '2026-10-28T10:00:00Z',
    ...overrides,
  }
}

export function documentItem(overrides: Partial<Document> = {}): Document {
  return {
    id: '44444444-4444-4444-8444-444444444444',
    subject_id: subject().id,
    filename: 'apuntes.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    status: 'ready',
    error_code: null,
    error_message: null,
    chunks_count: 12,
    created_at: '2026-11-18T10:00:00Z',
    ...overrides,
  }
}

/** Error body exactly as the backend sends it, so tests also check that its text is never shown. */
export function errorBody(
  code: string,
  message = 'server side text',
  details?: Record<string, unknown>,
): ApiErrorBody {
  return { code, message, details: details ?? null }
}

export function errorResponse(
  status: number,
  code: string,
  headers: Record<string, string> = {},
  message?: string,
) {
  return HttpResponse.json(errorBody(code, message), { status, headers })
}

/** Handlers for the happy path of the endpoints this change uses. */
export const handlers = {
  login: (expiresIn = 3600) =>
    http.post(`${API}/auth/login`, () => HttpResponse.json(tokenResponse(expiresIn))),
  me: (user: User = studentUser) => http.get(`${API}/users/me`, () => HttpResponse.json(user)),
  subjects: (list: Subject[] = []) => http.get(`${API}/subjects`, () => HttpResponse.json(list)),
  subject: (item: Subject = subject()) =>
    http.get(`${API}/subjects/${item.id}`, () => HttpResponse.json(item)),
  documents: (list: Document[] = [], subjectId: string = subject().id) =>
    http.get(`${API}/subjects/${subjectId}/documents`, () => HttpResponse.json(list)),
  register: (user: User = studentUser) =>
    http.post(`${API}/auth/register`, () => HttpResponse.json(user, { status: 201 })),
}
