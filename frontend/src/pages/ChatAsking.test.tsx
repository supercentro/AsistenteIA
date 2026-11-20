import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import { chatService } from '../services/chatService'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, errorResponse, studentUser } from '../tests/api'
import {
  CHAT_PAGE,
  conversationItem,
  answerWith,
  defaultAsk,
  messageItem,
  serveChat,
  sourceItem,
  type ChatState,
} from '../tests/chat'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.chat

afterEach(() => {
  vi.restoreAllMocks()
})

async function openChat(state: ChatState = serveChat()) {
  const view = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
  const box = await screen.findByRole('textbox', { name: text.box.label })
  return { state, box, ...view }
}

async function ask(box: HTMLElement, question: string) {
  const user = userEvent.setup()
  await user.click(box)
  await user.paste(question)
  await user.click(screen.getByRole('button', { name: text.box.send }))
  return user
}

describe('Asking a question', () => {
  it('shows the question at once, then the answer as plain text, clears the box and keeps the focus', async () => {
    const { state, box } = await openChat()

    await ask(box, 'Que es la fotosintesis?')

    expect(await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')).toBeVisible()
    expect(screen.getByText('Que es la fotosintesis?', { selector: 'p' })).toBeVisible()
    expect(state.asked).toEqual([
      { subject_id: expect.any(String), message: 'Que es la fotosintesis?' },
    ])
    await waitFor(() => expect(box).toHaveValue(''))
    await waitFor(() => expect(box).toHaveFocus())
  })

  it('continues the conversation with the next question', async () => {
    const { state, box } = await openChat()
    const user = await ask(box, 'Primera pregunta')
    await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')

    await user.click(box)
    await user.paste('Segunda pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    await waitFor(() => expect(state.asked).toHaveLength(2))
    expect(state.asked[0]).not.toHaveProperty('conversation_id')
    expect(state.asked[1]?.conversation_id).toBe('new-1')
  })

  it('shows a polite status and disables the send control while the answer is pending', async () => {
    const state = serveChat()
    state.ask = async (body, current) => {
      await delay(200)
      return defaultAsk(body, current)
    }
    const { box } = await openChat(state)

    const user = await ask(box, 'Una pregunta')

    const send = screen.getByRole('button', {
      name: new RegExp(`${text.box.sending}|${text.box.send}`),
    })
    await waitFor(() => expect(send).toBeDisabled())
    expect(screen.getByRole('status')).toHaveTextContent(text.answering)
    await user.click(send)
    await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')
    expect(state.asked).toHaveLength(1)
    expect(screen.queryByText(text.answering)).not.toBeInTheDocument()
  })

  it.each([
    ['empty', '', text.box.required],
    ['only blanks', '   ', text.box.required],
    ['too long', 'a'.repeat(2001), text.box.tooLong],
  ])(
    'sends nothing for a question that is %s and focuses the box',
    async (_name, value, message) => {
      const { state, box } = await openChat()
      const user = userEvent.setup()
      if (value) {
        await user.click(box)
        await user.paste(value)
      }

      await user.click(screen.getByRole('button', { name: text.box.send }))

      const error = await screen.findByText(message)
      expect(state.asked).toEqual([])
      await waitFor(() => expect(box).toHaveFocus())
      expect(box.getAttribute('aria-describedby')).toContain(error.id)
    },
  )

  it('shows an answer without material as a normal message and without a sources list', async () => {
    const state = serveChat()
    state.ask = answerWith({ answer: 'No encontre material relevante.', noMaterial: true })
    const { box } = await openChat(state)

    await ask(box, 'Pregunta fuera de tema')

    expect(await screen.findByText('No encontre material relevante.')).toBeVisible()
    expect(screen.queryByText(text.sources.label)).not.toBeInTheDocument()
  })

  it('shows questions and answers literally: markup, Markdown, long text and line breaks', async () => {
    const state = serveChat()
    const markup = '<b>negrita</b> **no es negrita** ' + 'x'.repeat(200)
    state.ask = answerWith({
      answer: `Linea uno\nLinea dos <img src=x onerror=alert(1)> ${'y'.repeat(200)}`,
    })
    const { box } = await openChat(state)

    await ask(box, markup)

    const answer = await screen.findByText(/Linea uno/)
    expect(answer.className).toContain('whitespace-pre-wrap')
    expect(answer.className).toContain('break-words')
    expect(answer.textContent).toContain('<img src=x onerror=alert(1)>')
    expect(document.querySelector('main b')).toBeNull()
    expect(document.querySelector('main img')).toBeNull()
    expect(screen.getByText(markup)).toBeVisible()
  })

  it('announces the messages in a polite log', async () => {
    await openChat()

    const log = screen.getByRole('log', { name: text.thread.label })

    expect(log.getAttribute('aria-live') ?? 'polite').toBe('polite')
  })
})

describe('Sources: shown as provided, without guarantees', () => {
  async function answered(
    sources = [
      sourceItem(),
      sourceItem({ filename: 'otro.pdf', page_number: 4, rank: 3, snippet: 'Segundo fragmento.' }),
    ],
  ) {
    const state = serveChat()
    state.ask = answerWith({ answer: 'Respuesta con fuentes.', sources })
    const { box } = await openChat(state)
    await ask(box, 'Pregunta')
    return screen.findByText('Respuesta con fuentes.')
  }

  it('lists file name and page (when there is one) and the snippet in an expandable detail, in the order given', async () => {
    await answered()

    const block = screen.getByRole('group', { name: text.sources.label })
    const items = within(block).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('fotosintesis.txt')
    expect(items[0]).not.toHaveTextContent(/página/)
    expect(items[1]).toHaveTextContent('otro.pdf')
    expect(items[1]).toHaveTextContent(text.sources.page(4))
    const detail = items[1]?.querySelector('details') as HTMLDetailsElement
    expect(detail).not.toBeNull()
    expect(within(detail).getByText('Segundo fragmento.')).toBeInTheDocument()
    expect(detail.open).toBe(false)
  })

  it('shows a source of a deleted document like any other', async () => {
    await answered([sourceItem({ chunk_id: null, document_id: null, filename: 'borrado.pdf' })])

    expect(screen.getByText('borrado.pdf')).toBeVisible()
  })

  it('says material consulted, adds the neutral note and never claims support', async () => {
    await answered()

    expect(screen.getByText(text.sources.note)).toBeVisible()
    const page = document.body.textContent ?? ''
    expect(page).not.toMatch(/respald|demuestr|garantiz|comprueba que|confirma|verificad[ao]s?\b/i)
    expect(text.sources.label).toMatch(/consultado/i)
  })

  it('shows file names and snippets as text, with direction characters isolated', async () => {
    await answered([
      sourceItem({ filename: '<i>x</i>‮fdp.txt', snippet: '<script>alert(1)</script>' }),
    ])

    expect(document.querySelector('main i')).toBeNull()
    expect(document.querySelector('main script')).toBeNull()
    expect(document.querySelector('bdi')?.textContent).toContain('fdp.txt')
  })
})

describe('Failures never lose the question', () => {
  async function failWith(
    respond: () => Response | Promise<Response> | never,
    question = 'Mi pregunta',
  ) {
    const state = serveChat()
    server.use(http.post(`${API}/chat`, () => respond()))
    const { box } = await openChat(state)
    await ask(box, question)
    return { state, box }
  }

  it.each([
    [
      '429 with Retry-After',
      () => errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '7' }),
      strings.errors.rateLimitedIn(7),
    ],
    [
      '429 without Retry-After',
      () => errorResponse(429, 'RATE_LIMITED'),
      strings.errors.byCode.RATE_LIMITED,
    ],
    [
      '502 LLM_UNAVAILABLE',
      () => errorResponse(502, 'LLM_UNAVAILABLE'),
      strings.errors.byCode.LLM_UNAVAILABLE,
    ],
    ['502 LLM_BLOCKED', () => errorResponse(502, 'LLM_BLOCKED'), strings.errors.byCode.LLM_BLOCKED],
    ['422', () => errorResponse(422, 'VALIDATION_ERROR'), strings.errors.byCode.VALIDATION_ERROR],
    ['500', () => errorResponse(500, 'INTERNAL_ERROR'), strings.errors.byStatus.server],
    [
      '503',
      () => errorResponse(503, 'SERVICE_UNAVAILABLE'),
      strings.errors.byCode.SERVICE_UNAVAILABLE,
    ],
    ['a network failure', () => HttpResponse.error(), strings.errors.network],
  ])(
    '%s: shows its message, keeps the question in the box and adds nothing to the thread',
    async (_name, respond, message) => {
      const { box } = await failWith(respond, 'Pregunta que debe quedar')

      expect(
        await screen.findByText(new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))),
      ).toBeVisible()
      expect(box).toHaveValue('Pregunta que debe quedar')
      expect(
        screen.queryByText('Pregunta que debe quedar', { selector: 'p' }),
      ).not.toBeInTheDocument()
      expect(screen.queryByText(text.answering)).not.toBeInTheDocument()
    },
  )

  it('explains that the rate limit can be shared by users of the same connection', async () => {
    await failWith(() => errorResponse(429, 'RATE_LIMITED', { 'Retry-After': '5' }))

    expect(await screen.findByText(text.errors.sharedLimit, { exact: false })).toBeVisible()
  })

  it('tells the unavailable and the blocked cases apart', () => {
    expect(strings.errors.byCode.LLM_UNAVAILABLE).not.toBe(strings.errors.byCode.LLM_BLOCKED)
  })

  it('after a timeout says the answer may have been saved, requests the data again and keeps the question', async () => {
    const state = serveChat({
      conversations: [conversationItem({ id: 'c1' })],
      messages: { c1: [messageItem()] },
    })
    vi.spyOn(chatService, 'ask').mockRejectedValue(new ApiError({ kind: 'timeout' }))
    const { box } = await openChat(state)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Que es la fotosintesis?' }))
    await screen.findAllByText('Que es la fotosintesis?')
    const listCalls = state.listCalls
    const messageCalls = state.messageCalls

    await user.click(box)
    await user.paste('Otra pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    expect(await screen.findByText(text.errors.timeout)).toBeVisible()
    await waitFor(() => expect(state.listCalls).toBeGreaterThan(listCalls))
    await waitFor(() => expect(state.messageCalls).toBeGreaterThan(messageCalls))
    expect(box).toHaveValue('Otra pregunta')
  })

  it.each([
    [403, 'FORBIDDEN'],
    [404, 'NOT_FOUND'],
  ])('says the subject is not available when the question answers %s', async (status, code) => {
    await failWith(() => errorResponse(status, code))

    expect(await screen.findByRole('heading', { name: text.unavailable.title })).toBeVisible()
  })

  it('sends the student to the consent gate on CONSENT_REQUIRED and does not send the question again', async () => {
    let calls = 0
    const state = serveChat()
    server.use(
      http.post(`${API}/chat`, () => {
        calls += 1
        return errorResponse(403, 'CONSENT_REQUIRED')
      }),
    )
    const { box, currentLocation } = await openChat(state)

    await ask(box, 'Pregunta')

    await waitFor(() => expect(currentLocation()).toBe('/consent'))
    expect(calls).toBe(1)
  })

  it('ends the session on 401 without flashing an error', async () => {
    const state = serveChat()
    server.use(http.post(`${API}/chat`, () => errorResponse(401, 'UNAUTHORIZED')))
    const { box, currentLocation } = await openChat(state)

    await ask(box, 'Pregunta')

    await waitFor(() => expect(currentLocation()).toBe('/login'))
    expect(screen.queryByText(strings.errors.byStatus.unauthorized)).not.toBeInTheDocument()
  })

  it('never logs the question, the answer or the server message', async () => {
    const logged: string[] = []
    const originals = { warn: console.warn, error: console.error, log: console.log }
    console.warn = (...args: unknown[]) => logged.push(args.join(' '))
    console.error = (...args: unknown[]) => logged.push(args.join(' '))
    console.log = (...args: unknown[]) => logged.push(args.join(' '))
    try {
      await failWith(() => errorResponse(500, 'INTERNAL_ERROR'), 'pregunta-secreta')
      await screen.findByText(strings.errors.byStatus.server)
    } finally {
      Object.assign(console, originals)
    }

    expect(logged.join('\n')).not.toContain('pregunta-secreta')
    expect(logged.join('\n')).not.toContain('server side text')
  })

  it('has no serious accessibility violation after an answer with sources and after an error', async () => {
    const state = serveChat()
    const { box, container } = await openChat(state)
    await ask(box, 'Pregunta')
    await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')
    await expectNoSeriousA11yViolations(container)

    server.use(http.post(`${API}/chat`, () => errorResponse(502, 'LLM_UNAVAILABLE')))
    const user = userEvent.setup()
    await user.click(box)
    await user.paste('Otra')
    await user.click(screen.getByRole('button', { name: text.box.send }))
    await screen.findByText(strings.errors.byCode.LLM_UNAVAILABLE, { exact: false })
    await expectNoSeriousA11yViolations(container)
  })
})
