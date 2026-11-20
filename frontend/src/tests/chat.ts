import { HttpResponse, http } from 'msw'
import type { ChatResponse, Conversation, Message, Source } from '../types/api'
import { API, errorResponse, subject } from './api'
import { server } from './server'

export const CHAT_SUBJECT = subject({
  id: '33333333-3333-4333-8333-333333333333',
  name: 'Biologia',
})
export const CHAT_PAGE = `/subjects/${CHAT_SUBJECT.id}/chat`

export function sourceItem(overrides: Partial<Source> = {}): Source {
  return {
    chunk_id: 'c0000000-0000-4000-8000-000000000001',
    document_id: 'd0000000-0000-4000-8000-000000000001',
    filename: 'fotosintesis.txt',
    page_number: null,
    rank: 1,
    snippet: 'La fotosintesis convierte la luz en energia quimica.',
    ...overrides,
  }
}

export function conversationItem(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'a0000000-0000-4000-8000-000000000001',
    subject_id: CHAT_SUBJECT.id,
    created_at: '2026-11-20T10:00:00Z',
    last_message_preview: 'Que es la fotosintesis?',
    ...overrides,
  }
}

export function messageItem(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm0000000-0000-4000-8000-000000000001',
    role: 'user',
    content: 'Que es la fotosintesis?',
    created_at: '2026-11-20T10:00:00Z',
    sources: [],
    ...overrides,
  }
}

export interface AskBody {
  subject_id: string
  conversation_id?: string | null
  message: string
}

export interface ChatState {
  conversations: Conversation[]
  messages: Record<string, Message[]>
  asked: AskBody[]
  subjectCalls: number
  listCalls: number
  messageCalls: number
  /** Decides the answer of POST /chat; the default behaves like the backend on success. */
  ask: (body: AskBody, state: ChatState) => Response | Promise<Response>
}

/** Answers like the backend: creates the conversation when needed and stores both messages. */
export function defaultAsk(body: AskBody, state: ChatState): Response {
  const id = body.conversation_id ?? `new-${state.conversations.length + 1}`
  if (!body.conversation_id) {
    state.conversations.unshift(conversationItem({ id, last_message_preview: body.message }))
  }
  return storeTurn(body, state, id, {
    answer: 'La fotosintesis ocurre en los cloroplastos [1].',
    sources: [sourceItem()],
    noMaterial: false,
  })
}

interface Answer {
  answer: string
  sources: Source[]
  noMaterial: boolean
}

function storeTurn(body: AskBody, state: ChatState, id: string, given: Answer): Response {
  const thread = state.messages[id] ?? []
  const base = thread.length
  thread.push(
    messageItem({ id: `u-${base}`, role: 'user', content: body.message }),
    messageItem({
      id: `a-${base + 1}`,
      role: 'assistant',
      content: given.answer,
      sources: given.sources,
    }),
  )
  state.messages[id] = thread
  const response: ChatResponse = {
    conversation_id: id,
    message_id: `a-${base + 1}`,
    answer: given.answer,
    no_material: given.noMaterial,
    sources: given.sources,
  }
  return HttpResponse.json(response)
}

/** An answer given by the test, stored like the backend stores it. */
export function answerWith(given: Partial<Answer> & { answer: string }) {
  return (body: AskBody, state: ChatState): Response => {
    const id = body.conversation_id ?? `new-${state.conversations.length + 1}`
    if (!body.conversation_id) {
      state.conversations.unshift(conversationItem({ id, last_message_preview: body.message }))
    }
    return storeTurn(body, state, id, { sources: [], noMaterial: false, ...given })
  }
}

/** Serves the endpoints of the chat page for the enrolled subject; the state can be changed. */
export function serveChat(
  initial: { conversations?: Conversation[]; messages?: Record<string, Message[]> } = {},
): ChatState {
  const state: ChatState = {
    conversations: [...(initial.conversations ?? [])],
    messages: { ...(initial.messages ?? {}) },
    asked: [],
    subjectCalls: 0,
    listCalls: 0,
    messageCalls: 0,
    ask: defaultAsk,
  }
  server.use(
    http.get(`${API}/subjects/${CHAT_SUBJECT.id}`, () => {
      state.subjectCalls += 1
      return HttpResponse.json(CHAT_SUBJECT)
    }),
    http.get(`${API}/conversations`, ({ request }) => {
      state.listCalls += 1
      const subjectId = new URL(request.url).searchParams.get('subject_id')
      return HttpResponse.json(
        state.conversations.filter((item) => !subjectId || item.subject_id === subjectId),
      )
    }),
    http.get(`${API}/conversations/:id/messages`, ({ params }) => {
      state.messageCalls += 1
      const thread = state.messages[String(params.id)]
      return thread ? HttpResponse.json(thread) : errorResponse(404, 'NOT_FOUND')
    }),
    http.post(`${API}/chat`, async ({ request }) => {
      const body = (await request.json()) as AskBody
      state.asked.push(body)
      return state.ask(body, state)
    }),
    http.delete(`${API}/conversations/:id`, ({ params }) => {
      const id = String(params.id)
      if (!state.conversations.some((item) => item.id === id)) {
        return errorResponse(404, 'NOT_FOUND')
      }
      state.conversations = state.conversations.filter((item) => item.id !== id)
      delete state.messages[id]
      return new HttpResponse(null, { status: 204 })
    }),
    http.delete(`${API}/users/me/conversations`, () => {
      state.conversations = []
      state.messages = {}
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return state
}
