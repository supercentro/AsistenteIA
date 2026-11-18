import type { Page, Request } from '@playwright/test'
import type { components } from '../../src/types/api.generated.ts'

type Schemas = components['schemas']
type ApiErrorBody = Schemas['Error']
type Subject = Schemas['Subject']
type TokenResponse = Schemas['TokenResponse']
type User = Schemas['User']

/**
 * Stubs the API for the mocked browser suite (no backend, no database). Payloads are typed with
 * the types generated from docs/api-spec.yml, so a contract change breaks compilation here too.
 */
export const API = 'http://localhost:8000/api/v1'
const APP_ORIGIN = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

/** Must equal PRIVACY_POLICY_VERSION in src/lib/privacyPolicy.ts (a unit test keeps that one in sync). */
export const POLICY_VERSION = '2026-10-v1'

/** A student whose consent is current: the consent gate lets every student route through. */
export const student: User = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Ana Estudiante',
  email: 'ana@example.com',
  role: 'student',
  consent_version: POLICY_VERSION,
  consent_accepted_at: '2026-11-17T10:00:00Z',
}

/** A student who never accepted the privacy policy. */
export const unconsentedStudent: User = {
  ...student,
  consent_version: null,
  consent_accepted_at: null,
}

export const teacher: User = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Tomas Docente',
  email: 'tomas@example.com',
  role: 'teacher',
  consent_version: null,
  consent_accepted_at: null,
}

export function subject(overrides: Partial<Subject> = {}): Subject {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    name: 'Algebra',
    description: null,
    teacher_id: teacher.id,
    created_at: '2026-10-28T10:00:00Z',
    ...overrides,
  }
}

export function token(expiresIn = 3600): TokenResponse {
  return { access_token: 'e2e.fake.token', token_type: 'bearer', expires_in: expiresIn }
}

export function errorBody(code: string): ApiErrorBody {
  return { code, message: 'server side text that must never be shown', details: null }
}

export interface Reply {
  status: number
  body?: unknown
  headers?: Record<string, string>
}

export type Handlers = Record<string, (request: Request) => Reply>

const CORS = {
  'access-control-allow-origin': APP_ORIGIN,
  'access-control-allow-headers': 'authorization,content-type',
  'access-control-allow-methods': 'GET,POST,DELETE,OPTIONS',
  // Mirrors the backend CORS configuration (TD-021 resolved): browsers may read Retry-After.
  'access-control-expose-headers': 'Retry-After',
}

/** Handlers are keyed by `METHOD /path` (without the API prefix), e.g. `POST /auth/login`. */
export async function mockApi(page: Page, handlers: Handlers) {
  const seen: Array<{ key: string; authorization: string | null }> = []
  await page.route(`${API}/**`, async (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS })
      return
    }
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const key = `${request.method()} ${path}`
    const handler = handlers[key]
    seen.push({ key, authorization: request.headers()['authorization'] ?? null })
    if (!handler) {
      await route.fulfill({ status: 404, headers: CORS, json: errorBody('NOT_FOUND') })
      return
    }
    const reply = handler(request)
    await route.fulfill({
      status: reply.status,
      headers: { ...CORS, ...reply.headers },
      ...(reply.body === undefined ? {} : { json: reply.body }),
    })
  })
  return { seen }
}

export const signInHandlers = (user: User, subjects: Subject[] = []): Handlers => ({
  'POST /auth/login': () => ({ status: 200, body: token() }),
  'GET /users/me': () => ({ status: 200, body: user }),
  'GET /subjects': () => ({ status: 200, body: subjects }),
})
