import { HttpResponse, http } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { API, TOKEN_VALUE, errorBody, studentUser, teacherUser } from '../tests/api'
import { server } from '../tests/server'
import { apiClient } from './apiClient'
import { endSession, getSnapshot, setUser, startSession } from './session'
import type { User } from '../types/api'

function signIn(user: User, token = TOKEN_VALUE) {
  startSession(token, 3600)
  setUser(user)
}

function answer(status: number, code: string) {
  let calls = 0
  server.use(
    http.get(`${API}/anything`, () => {
      calls += 1
      return HttpResponse.json(errorBody(code), { status })
    }),
  )
  return () => calls
}

beforeEach(() => {
  endSession('signed-out')
})

afterEach(() => {
  endSession('signed-out')
})

describe('403 CONSENT_REQUIRED re-opens the consent gate', () => {
  it('marks the consent of a signed-in student as stale and does not retry', async () => {
    signIn(studentUser)
    const calls = answer(403, 'CONSENT_REQUIRED')

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 403 })

    expect(getSnapshot().user?.consent_version).toBeNull()
    expect(getSnapshot().token).not.toBeNull()
    expect(calls()).toBe(1)
  })

  it('leaves the profile alone for any other 403 code', async () => {
    signIn(studentUser)
    answer(403, 'FORBIDDEN')

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 403 })

    expect(getSnapshot().user?.consent_version).toBe(studentUser.consent_version)
  })

  it('leaves a teacher alone even if the code shows up', async () => {
    signIn(teacherUser)
    answer(403, 'CONSENT_REQUIRED')

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 403 })

    expect(getSnapshot().user?.consent_version).toBe(teacherUser.consent_version)
  })

  it('ignores the same code on a 401 or a 500', async () => {
    signIn(studentUser)
    answer(500, 'CONSENT_REQUIRED')

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 500 })

    expect(getSnapshot().user?.consent_version).toBe(studentUser.consent_version)
  })

  it('does not touch a later session with an answer that belongs to an earlier one', async () => {
    signIn(studentUser)
    server.use(
      http.get(`${API}/anything`, async () => {
        endSession('signed-out')
        signIn(
          { ...studentUser, id: '99999999-9999-4999-8999-999999999999' },
          'another-session-token',
        )
        return HttpResponse.json(errorBody('CONSENT_REQUIRED'), { status: 403 })
      }),
    )

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 403 })

    expect(getSnapshot().user?.consent_version).toBe(studentUser.consent_version)
  })
})
