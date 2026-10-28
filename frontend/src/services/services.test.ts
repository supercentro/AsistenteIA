import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { endSession, startSession } from '../lib/session'
import { API, TOKEN_VALUE, errorResponse, studentUser, subject, tokenResponse } from '../tests/api'
import { server } from '../tests/server'
import { authService } from './authService'
import { subjectService } from './subjectService'

afterEach(() => {
  endSession('signed-out')
})

describe('authService', () => {
  it('login posts only email and password and returns the token response', async () => {
    let body: unknown
    let authorization: string | null = 'unset'
    server.use(
      http.post(`${API}/auth/login`, async ({ request }) => {
        body = await request.json()
        authorization = request.headers.get('authorization')
        return HttpResponse.json(tokenResponse(120))
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    const result = await authService.login({
      email: 'ana@example.com',
      password: 'a-long-password',
    })

    expect(body).toEqual({ email: 'ana@example.com', password: 'a-long-password' })
    expect(authorization).toBeNull()
    expect(result).toEqual(tokenResponse(120))
  })

  it('register posts only name, email and password', async () => {
    let body: unknown
    server.use(
      http.post(`${API}/auth/register`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(studentUser, { status: 201 })
      }),
    )

    const user = await authService.register({
      name: 'Ana',
      email: 'ana@example.com',
      password: 'a-long-password',
    })

    expect(Object.keys(body as object).sort()).toEqual(['email', 'name', 'password'])
    expect(user).toEqual(studentUser)
  })

  it('me sends the bearer token and returns the profile', async () => {
    let authorization: string | null = null
    server.use(
      http.get(`${API}/users/me`, ({ request }) => {
        authorization = request.headers.get('authorization')
        return HttpResponse.json(studentUser)
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    expect(await authService.me()).toEqual(studentUser)
    expect(authorization).toBe(`Bearer ${TOKEN_VALUE}`)
  })

  it('propagates API errors as ApiError', async () => {
    server.use(http.post(`${API}/auth/login`, () => errorResponse(401, 'INVALID_CREDENTIALS')))

    await expect(authService.login({ email: 'a@b.co', password: 'x' })).rejects.toMatchObject({
      status: 401,
      code: 'INVALID_CREDENTIALS',
    })
  })
})

describe('subjectService', () => {
  it('lists the subjects in the order received', async () => {
    const list = [subject({ name: 'Zoo' }), subject({ id: '4', name: 'Algebra' })]
    server.use(http.get(`${API}/subjects`, () => HttpResponse.json(list)))
    startSession(TOKEN_VALUE, 3600)

    expect(await subjectService.list()).toEqual(list)
  })
})
