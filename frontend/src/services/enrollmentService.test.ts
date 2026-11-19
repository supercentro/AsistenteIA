import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { endSession, startSession } from '../lib/session'
import { API, TOKEN_VALUE, enrollmentItem, subject } from '../tests/api'
import { server } from '../tests/server'
import { enrollmentService } from './enrollmentService'

afterEach(() => {
  endSession('signed-out')
})

const SUBJECT_ID = subject().id

describe('enrollmentService', () => {
  it('list reads the enrollments of the subject with the token', async () => {
    let authorization: string | null = null
    server.use(
      http.get(`${API}/subjects/${SUBJECT_ID}/enrollments`, ({ request }) => {
        authorization = request.headers.get('authorization')
        return HttpResponse.json([enrollmentItem()])
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    expect(await enrollmentService.list(SUBJECT_ID)).toEqual([enrollmentItem()])
    expect(authorization).toBe(`Bearer ${TOKEN_VALUE}`)
  })

  it('create posts only the e-mail, exactly as typed', async () => {
    let body: unknown
    server.use(
      http.post(`${API}/subjects/${SUBJECT_ID}/enrollments`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(enrollmentItem(), { status: 201 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    const created = await enrollmentService.create(SUBJECT_ID, 'Ana@Example.com')

    expect(body).toEqual({ student_email: 'Ana@Example.com' })
    expect(created.student_email).toBe('ana@example.com')
  })

  it('remove deletes the enrollment of one student', async () => {
    let path = ''
    server.use(
      http.delete(`${API}/subjects/${SUBJECT_ID}/enrollments/:studentId`, ({ request }) => {
        path = new URL(request.url).pathname
        return new HttpResponse(null, { status: 204 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    await enrollmentService.remove(SUBJECT_ID, enrollmentItem().student_id)

    expect(path).toBe(`/api/v1/subjects/${SUBJECT_ID}/enrollments/${enrollmentItem().student_id}`)
  })
})
