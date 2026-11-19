import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { endSession, startSession } from '../lib/session'
import { API, TOKEN_VALUE, documentItem, subject } from '../tests/api'
import { readMultipart } from '../tests/materials'
import { server } from '../tests/server'
import { documentService } from './documentService'
import { subjectService } from './subjectService'

afterEach(() => {
  endSession('signed-out')
})

const SUBJECT_ID = subject().id

describe('subjectService - create and get', () => {
  it('create posts the name and the description as JSON with the token', async () => {
    let body: unknown
    let authorization: string | null = null
    server.use(
      http.post(`${API}/subjects`, async ({ request }) => {
        body = await request.json()
        authorization = request.headers.get('authorization')
        return HttpResponse.json(subject({ name: 'Fisica' }), { status: 201 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    const created = await subjectService.create({ name: 'Fisica', description: 'Mecanica' })

    expect(body).toEqual({ name: 'Fisica', description: 'Mecanica' })
    expect(authorization).toBe(`Bearer ${TOKEN_VALUE}`)
    expect(created.name).toBe('Fisica')
  })

  it('create sends no description key when there is none', async () => {
    let body: unknown
    server.use(
      http.post(`${API}/subjects`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(subject(), { status: 201 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    await subjectService.create({ name: 'Fisica' })

    expect(body).toEqual({ name: 'Fisica' })
  })

  it('get reads one subject', async () => {
    server.use(http.get(`${API}/subjects/${SUBJECT_ID}`, () => HttpResponse.json(subject())))
    startSession(TOKEN_VALUE, 3600)

    expect((await subjectService.get(SUBJECT_ID)).id).toBe(SUBJECT_ID)
  })
})

describe('documentService', () => {
  it('list reads the documents of the subject', async () => {
    server.use(
      http.get(`${API}/subjects/${SUBJECT_ID}/documents`, () =>
        HttpResponse.json([documentItem()]),
      ),
    )
    startSession(TOKEN_VALUE, 3600)

    expect(await documentService.list(SUBJECT_ID)).toEqual([documentItem()])
  })

  it('upload sends a multipart body with the single field "file" and the token', async () => {
    let sent: Awaited<ReturnType<typeof readMultipart>> | null = null
    let contentType: string | null = null
    let authorization: string | null = null
    server.use(
      http.post(`${API}/subjects/${SUBJECT_ID}/documents`, async ({ request }) => {
        contentType = request.headers.get('content-type')
        authorization = request.headers.get('authorization')
        sent = await readMultipart(request)
        return HttpResponse.json(documentItem({ status: 'pending', chunks_count: 0 }), {
          status: 202,
        })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    const created = await documentService.upload(
      SUBJECT_ID,
      new File(['contenido'], 'notas.txt', { type: 'text/plain' }),
    )

    expect(sent).toEqual({ fields: ['file'], filename: 'notas.txt', content: 'contenido' })
    expect(contentType).toMatch(/^multipart\/form-data; boundary=/)
    expect(authorization).toBe(`Bearer ${TOKEN_VALUE}`)
    expect(created.status).toBe('pending')
  })

  it('remove deletes one document', async () => {
    let path = ''
    server.use(
      http.delete(`${API}/subjects/${SUBJECT_ID}/documents/:id`, ({ request }) => {
        path = new URL(request.url).pathname
        return new HttpResponse(null, { status: 204 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    await documentService.remove(SUBJECT_ID, documentItem().id)

    expect(path).toBe(`/api/v1/subjects/${SUBJECT_ID}/documents/${documentItem().id}`)
  })
})
