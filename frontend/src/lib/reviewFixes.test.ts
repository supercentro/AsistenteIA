import { HttpResponse, http } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { API, errorResponse } from '../tests/api'
import { server } from '../tests/server'
import { apiClient } from './apiClient'
import { ApiError, messageFor } from './apiError'
import { safeReturnTarget } from './returnTarget'
import { endSession, getSnapshot, startSession, takeNotice } from './session'
import { strings } from './strings.es'

beforeEach(() => {
  endSession('signed-out')
  takeNotice()
})

afterEach(() => {
  endSession('signed-out')
  takeNotice()
})

describe('a late 401 for an earlier session', () => {
  it('does not end the session of the user who signed in afterwards', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let reached: () => void = () => undefined
    const arrived = new Promise<void>((resolve) => {
      reached = resolve
    })
    server.use(
      http.get(`${API}/subjects`, async () => {
        reached()
        await gate
        return errorResponse(401, 'UNAUTHORIZED')
      }),
    )
    startSession('token-of-user-a', 3600)
    const pending = apiClient.get('/subjects').catch((error: ApiError) => error)
    await arrived // the request is on the wire carrying user A's token

    endSession('signed-out')
    startSession('token-of-user-b', 3600)
    release()
    const error = await pending

    expect(error).toMatchObject({ status: 401 })
    expect(getSnapshot().token).toBe('token-of-user-b')
    expect(takeNotice()).toBe('signed-out')
  })

  it('still ends the session when the rejected token is the current one', async () => {
    server.use(http.get(`${API}/subjects`, () => errorResponse(401, 'UNAUTHORIZED')))
    startSession('current-token', 3600)

    await apiClient.get('/subjects').catch(() => undefined)

    expect(getSnapshot().token).toBeNull()
  })

  it('ignores a 200 for an earlier session in the same way', async () => {
    server.use(http.get(`${API}/subjects`, () => HttpResponse.json([])))
    startSession('token', 3600)

    await apiClient.get('/subjects')

    expect(getSnapshot().token).toBe('token')
  })
})

describe('return targets that resolve to the authentication screens', () => {
  const PERCENT_L = '%6c'
  it.each([
    '/LOGIN',
    '/Register',
    '/subjects/../login',
    `/${PERCENT_L}ogin`,
    '/./login',
    '/subjects/%2e%2e/register',
    '/login/',
  ])('rejects %s', (target) => {
    expect(safeReturnTarget(target)).toBeNull()
  })

  it.each(['/subjects', '/subjects/login-help', '/loginx'])('still accepts %s', (target) => {
    expect(safeReturnTarget(target)).toBe(target)
  })
})

describe('Spanish messages by status class when the code is unknown', () => {
  it.each([
    [401, strings.errors.byStatus.unauthorized],
    [403, strings.errors.byStatus.forbidden],
    [404, strings.errors.byStatus.notFound],
    [409, strings.errors.byStatus.conflict],
    [422, strings.errors.byStatus.validation],
    [429, strings.errors.byStatus.rateLimited],
    [502, strings.errors.byStatus.server],
  ])('maps %s', (status, text) => {
    expect(messageFor(new ApiError({ kind: 'http', status, code: 'SOMETHING_NEW' }))).toBe(text)
    expect(messageFor(new ApiError({ kind: 'http', status, code: null }))).toBe(text)
  })
})
