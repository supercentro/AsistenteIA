import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../lib/apiClient'
import { ApiError, messageFor, toApiError } from '../lib/apiError'
import { endSession, startSession } from '../lib/session'
import { strings } from '../lib/strings.es'
import { API, TOKEN_VALUE, errorBody } from '../tests/api'
import { CHAT_SUBJECT, conversationItem, messageItem } from '../tests/chat'
import { server } from '../tests/server'
import { chatService } from './chatService'
import { conversationService } from './conversationService'

afterEach(() => {
  vi.restoreAllMocks()
  endSession('signed-out')
})

describe('chatService', () => {
  it('posts the subject and the message, and the conversation only when there is one', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post(`${API}/chat`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({
          conversation_id: 'c1',
          message_id: 'm1',
          answer: 'ok',
          no_material: false,
          sources: [],
        })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    await chatService.ask({ subjectId: CHAT_SUBJECT.id, conversationId: null, message: 'hola' })
    await chatService.ask({ subjectId: CHAT_SUBJECT.id, conversationId: 'c1', message: 'otra' })

    expect(bodies).toEqual([
      { subject_id: CHAT_SUBJECT.id, message: 'hola' },
      { subject_id: CHAT_SUBJECT.id, conversation_id: 'c1', message: 'otra' },
    ])
  })

  it('uses a 60-second limit, longer than the 15 seconds of an ordinary request', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} })

    await chatService.ask({ subjectId: CHAT_SUBJECT.id, conversationId: null, message: 'hola' })

    expect(post.mock.calls[0]?.[2]).toMatchObject({ timeout: 60_000 })
  })
})

describe('conversationService', () => {
  it('lists the conversations of one subject', async () => {
    let query = ''
    server.use(
      http.get(`${API}/conversations`, ({ request }) => {
        query = new URL(request.url).search
        return HttpResponse.json([conversationItem()])
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    expect(await conversationService.list(CHAT_SUBJECT.id)).toEqual([conversationItem()])
    expect(query).toBe(`?subject_id=${CHAT_SUBJECT.id}`)
  })

  it('reads the messages, deletes one conversation and deletes the whole history', async () => {
    const calls: string[] = []
    server.use(
      http.get(`${API}/conversations/c1/messages`, () => {
        calls.push('messages')
        return HttpResponse.json([messageItem()])
      }),
      http.delete(`${API}/conversations/c1`, () => {
        calls.push('delete-one')
        return new HttpResponse(null, { status: 204 })
      }),
      http.delete(`${API}/users/me/conversations`, () => {
        calls.push('delete-all')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    startSession(TOKEN_VALUE, 3600)

    expect(await conversationService.messages('c1')).toEqual([messageItem()])
    await conversationService.remove('c1')
    await conversationService.removeAll()

    expect(calls).toEqual(['messages', 'delete-one', 'delete-all'])
  })
})

describe('messages of the chat failures', () => {
  function error(status: number, code: string, headers: Record<string, string> = {}) {
    return toApiError(
      Object.assign(new Error('x'), {
        isAxiosError: true,
        response: { status, data: errorBody(code), headers },
        config: { headers: {} },
      }),
    ) as ApiError
  }

  it('gives LLM_UNAVAILABLE and LLM_BLOCKED their own texts', () => {
    const unavailable = messageFor(error(502, 'LLM_UNAVAILABLE'))
    const blocked = messageFor(error(502, 'LLM_BLOCKED'))
    expect(unavailable).toBe(strings.errors.byCode.LLM_UNAVAILABLE)
    expect(blocked).toBe(strings.errors.byCode.LLM_BLOCKED)
    expect(unavailable).not.toBe(blocked)
    expect(blocked).toMatch(/reform/i)
  })
})
