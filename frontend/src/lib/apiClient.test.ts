import { HttpResponse, http } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { API, TOKEN_VALUE, errorResponse } from '../tests/api'
import { server } from '../tests/server'
import { ApiError } from './apiError'
import { apiClient } from './apiClient'
import { endSession, getSnapshot, onSessionEnd, startSession, takeNotice } from './session'

function captureAuthorization(path: string, method: 'get' | 'post' = 'get') {
  const seen: Array<string | null> = []
  server.use(
    http[method](`${API}${path}`, ({ request }) => {
      seen.push(request.headers.get('authorization'))
      return HttpResponse.json({ ok: true })
    }),
  )
  return seen
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    return error as ApiError
  }
  throw new Error('expected the request to be rejected')
}

beforeEach(() => {
  endSession('signed-out')
  takeNotice()
})

afterEach(() => {
  endSession('signed-out')
  takeNotice()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('token injection', () => {
  it('sends the bearer token on protected requests', async () => {
    const seen = captureAuthorization('/users/me')
    startSession(TOKEN_VALUE, 3600)

    await apiClient.get('/users/me')

    expect(seen).toEqual([`Bearer ${TOKEN_VALUE}`])
  })

  it('never sends the token to login or registration, even with a stale session', async () => {
    const login = captureAuthorization('/auth/login', 'post')
    const register = captureAuthorization('/auth/register', 'post')
    startSession(TOKEN_VALUE, 3600)

    await apiClient.post('/auth/login', {}, { public: true })
    await apiClient.post('/auth/register', {}, { public: true })

    expect(login).toEqual([null])
    expect(register).toEqual([null])
  })

  it('never attaches the token to a request for another origin', async () => {
    const seen: Array<string | null> = []
    server.use(
      http.get('http://other.example/data', ({ request }) => {
        seen.push(request.headers.get('authorization'))
        return HttpResponse.json({ ok: true }, { headers: { 'Access-Control-Allow-Origin': '*' } })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    await apiClient.get('http://other.example/data')

    expect(seen).toEqual([null])
  })

  it('does not send a protected request without a session', async () => {
    const seen = captureAuthorization('/users/me')

    const error = await rejection(apiClient.get('/users/me'))

    expect(seen).toEqual([])
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHORIZED' })
  })

  it('ends an expired session before sending and does not send the token', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-28T12:00:00Z'))
    const seen = captureAuthorization('/users/me')
    startSession(TOKEN_VALUE, 60)
    vi.setSystemTime(new Date('2026-10-28T12:02:00Z'))

    const error = await rejection(apiClient.get('/users/me'))

    expect(seen).toEqual([])
    expect(error.status).toBe(401)
    expect(getSnapshot().token).toBeNull()
    expect(takeNotice()).toBe('expired')
  })
})

describe('401 handling', () => {
  it('ends the session once when a protected request is answered with 401', async () => {
    server.use(http.get(`${API}/subjects`, () => errorResponse(401, 'UNAUTHORIZED')))
    const ended = vi.fn()
    onSessionEnd(ended)
    startSession(TOKEN_VALUE, 3600)

    const error = await rejection(apiClient.get('/subjects'))

    expect(error.status).toBe(401)
    expect(ended).toHaveBeenCalledTimes(1)
    expect(takeNotice()).toBe('unauthorized')
    expect(getSnapshot().token).toBeNull()
  })

  it('ends the session once even when several requests are answered with 401 together', async () => {
    server.use(http.get(`${API}/subjects`, () => errorResponse(401, 'UNAUTHORIZED')))
    const ended = vi.fn()
    onSessionEnd(ended)
    startSession(TOKEN_VALUE, 3600)

    await Promise.allSettled([
      apiClient.get('/subjects'),
      apiClient.get('/subjects'),
      apiClient.get('/subjects'),
    ])

    expect(ended).toHaveBeenCalledTimes(1)
  })

  it('treats 401 from login as a plain error and leaves the session alone', async () => {
    server.use(http.post(`${API}/auth/login`, () => errorResponse(401, 'INVALID_CREDENTIALS')))
    const ended = vi.fn()
    onSessionEnd(ended)
    startSession(TOKEN_VALUE, 3600)

    const error = await rejection(apiClient.post('/auth/login', {}, { public: true }))

    expect(error).toMatchObject({ status: 401, code: 'INVALID_CREDENTIALS' })
    expect(ended).not.toHaveBeenCalled()
    expect(getSnapshot().token).toBe(TOKEN_VALUE)
  })

  it('does not touch the session for other failures', async () => {
    server.use(http.get(`${API}/subjects`, () => errorResponse(403, 'FORBIDDEN')))
    startSession(TOKEN_VALUE, 3600)

    await rejection(apiClient.get('/subjects'))

    expect(getSnapshot().token).toBe(TOKEN_VALUE)
  })
})

describe('errors and diagnostics', () => {
  it('rejects with an ApiError that carries no server text', async () => {
    server.use(
      http.post(`${API}/auth/register`, () =>
        errorResponse(409, 'CONFLICT', {}, 'ana@example.com already registered'),
      ),
    )

    const error = await rejection(apiClient.post('/auth/register', {}, { public: true }))

    expect(error).toMatchObject({ kind: 'http', status: 409, code: 'CONFLICT' })
    expect(JSON.stringify(error)).not.toContain('ana@example.com')
  })

  it('reads Retry-After from a 429', async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '17' }),
      ),
    )

    const error = await rejection(apiClient.post('/auth/login', {}, { public: true }))

    expect(error.retryAfterSeconds).toBe(17)
  })

  it('classifies an unreachable server as a network error', async () => {
    server.use(http.get(`${API}/subjects`, () => HttpResponse.error()))
    startSession(TOKEN_VALUE, 3600)

    const error = await rejection(apiClient.get('/subjects'))

    expect(error.kind).toBe('network')
  })

  it('logs at most method, path and status of a failed request', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    server.use(http.get(`${API}/subjects`, () => errorResponse(500, 'INTERNAL_ERROR')))
    startSession(TOKEN_VALUE, 3600)

    await rejection(apiClient.get('/subjects?email=ana@example.com&password=hunter2'))

    const printed = JSON.stringify([...warn.mock.calls, ...error.mock.calls])
    expect(printed).toContain('GET')
    expect(printed).toContain('/subjects')
    expect(printed).toContain('500')
    expect(printed).not.toContain('ana@example.com')
    expect(printed).not.toContain('hunter2')
    expect(printed).not.toContain('secret')
    expect(printed).not.toContain('server side text')
  })

  it('has a bounded request timeout', () => {
    expect(apiClient.defaults.timeout).toBe(15_000)
  })
})
