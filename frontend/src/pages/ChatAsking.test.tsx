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
    expect(screen.queryByText(text.sources.cited)).not.toBeInTheDocument()
    expect(screen.queryByText(text.sources.retrieved)).not.toBeInTheDocument()
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
    // The conversation list can show the same text as its label, so look inside the thread.
    expect(within(screen.getByRole('log')).getByText(markup)).toBeVisible()
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
    attribution: 'cited' | 'retrieved' | null | 'absent' = 'cited',
  ) {
    const state = serveChat()
    state.ask = answerWith({
      answer: 'Respuesta con fuentes [1][3].',
      sources,
      attribution: attribution === 'absent' ? undefined : attribution,
    })
    const { box } = await openChat(state)
    await ask(box, 'Pregunta')
    return screen.findByText('Respuesta con fuentes [1][3].')
  }

  it('lists the cited sources with their marker, file name, page (when there is one) and the snippet in an expandable detail, in the order given', async () => {
    await answered()

    const block = screen.getByRole('group', { name: text.sources.cited })
    const items = within(block).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent(text.sources.marker(1))
    expect(items[0]).toHaveTextContent('fotosintesis.txt')
    expect(items[0]).not.toHaveTextContent(/página/)
    expect(items[1]).toHaveTextContent(text.sources.marker(3))
    expect(items[1]).toHaveTextContent('otro.pdf')
    expect(items[1]).toHaveTextContent(text.sources.page(4))
    const detail = items[1]?.querySelector('details') as HTMLDetailsElement
    expect(detail).not.toBeNull()
    expect(within(detail).getByText('Segundo fragmento.')).toBeInTheDocument()
    expect(detail.open).toBe(false)
  })

  it('shows the sources that were only retrieved apart, collapsed, with no marker numbers', async () => {
    await answered(undefined, 'retrieved')

    const label = screen.getByText(text.sources.retrieved)
    const outer = label.closest('details') as HTMLDetailsElement
    expect(outer).not.toBeNull()
    expect(outer.open).toBe(false)
    expect(screen.queryByText(text.sources.cited)).not.toBeInTheDocument()
    const items = within(outer).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    for (const item of items) {
      expect(item).not.toHaveTextContent(/\[\d+\]/)
    }
    expect(items[1]).toHaveTextContent('otro.pdf')
  })

  it('keeps the retrieved fragments reachable with the keyboard (Tab reaches the summary)', async () => {
    await answered(undefined, 'retrieved')
    const user = userEvent.setup()
    const summary = screen.getByText(text.sources.retrieved)

    for (let step = 0; step < 40 && document.activeElement !== summary; step += 1) {
      await user.tab()
    }

    expect(summary).toHaveFocus()
    await user.click(summary)
    expect((summary.closest('details') as HTMLDetailsElement).open).toBe(true)
    expect(screen.getByText('fotosintesis.txt')).toBeVisible()
  })

  it.each(['absent', null] as const)(
    'shows the sources as retrieved material when the attribution is %s',
    async (attribution) => {
      await answered(undefined, attribution)

      expect(screen.getByText(text.sources.retrieved)).toBeInTheDocument()
      expect(screen.queryByText(text.sources.cited)).not.toBeInTheDocument()
    },
  )

  it('shows a source of a deleted document like any other', async () => {
    await answered([sourceItem({ chunk_id: null, document_id: null, filename: 'borrado.pdf' })])

    expect(screen.getByText('borrado.pdf')).toBeVisible()
  })

  it('adds the neutral note and never claims support, in either state', async () => {
    await answered()

    expect(screen.getByText(text.sources.note)).toBeVisible()
    const page = document.body.textContent ?? ''
    expect(page).not.toMatch(/respald|demuestr|garantiz|comprueba que|confirma|verificad[ao]s?\b/i)
    for (const label of [text.sources.cited, text.sources.retrieved]) {
      expect(label).not.toMatch(/respald|demuestr|garantiz|prueba|confirma|verific/i)
    }
    expect(text.sources.cited).toBe('Material citado en la respuesta')
    expect(text.sources.retrieved).toBe(
      'Material recuperado (la respuesta no indica cuáles fragmentos usó)',
    )
  })

  it('shows file names and snippets as text, with direction characters isolated', async () => {
    await answered([
      sourceItem({ filename: '<i>x</i>\u202efdp.txt', snippet: '<script>alert(1)</script>' }),
    ])

    expect(document.querySelector('main i')).toBeNull()
    expect(document.querySelector('main script')).toBeNull()
    expect(document.querySelector('bdi')?.textContent).toContain('fdp.txt')
  })

  it('has no serious accessibility violation in either state', async () => {
    await answered()
    await expectNoSeriousA11yViolations(document.body)
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

describe('The focus when an answer arrives', () => {
  function heldAnswer() {
    const state = serveChat({
      conversations: [
        conversationItem({ id: 'old-1', last_message_preview: 'Vieja conversacion' }),
      ],
    })
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    state.ask = async (body, current) => {
      await gate
      return defaultAsk(body, current)
    }
    return { state, release }
  }

  it('leaves the focus in an open delete confirmation', async () => {
    const { state, release } = heldAnswer()
    const { box } = await openChat(state)
    const user = await ask(box, 'Una pregunta')
    await waitFor(() => expect(state.asked).toHaveLength(1))

    await user.click(
      screen.getByRole('button', {
        name: text.conversations.remove.action('Vieja conversacion'),
      }),
    )
    const group = screen.getByRole('group', {
      name: text.conversations.remove.question('Vieja conversacion'),
    })
    await waitFor(() => expect(group).toHaveFocus())

    release()

    expect(await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')).toBeVisible()
    await waitFor(() => expect(box).toHaveValue(''))
    expect(group).toHaveFocus()
    expect(box).not.toHaveFocus()
  })

  it('leaves the focus on a control the student moved to', async () => {
    const { state, release } = heldAnswer()
    const { box } = await openChat(state)
    await ask(box, 'Una pregunta')
    await waitFor(() => expect(state.asked).toHaveLength(1))
    const link = screen.getByRole('link', { name: text.policyLink })
    link.focus()

    release()

    expect(await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')).toBeVisible()
    await waitFor(() => expect(box).toHaveValue(''))
    expect(link).toHaveFocus()
  })

  it('still gives the focus to the box when it fell to the page body', async () => {
    const { state, release } = heldAnswer()
    const { box } = await openChat(state)
    await ask(box, 'Una pregunta')
    await waitFor(() => expect(state.asked).toHaveLength(1))
    // A disabled button cannot be blurred in jsdom: move the focus to a link and drop it.
    const link = screen.getByRole('link', { name: text.policyLink })
    link.focus()
    link.blur()
    expect(document.body).toHaveFocus()

    release()

    await waitFor(() => expect(box).toHaveFocus())
  })

  it('never moves the focus to the box while the student has it on another control, even through a deferred focus', async () => {
    const { state, release } = heldAnswer()
    const { box } = await openChat(state)
    await ask(box, 'Una pregunta')
    await waitFor(() => expect(state.asked).toHaveLength(1))
    const trigger = screen.getByRole('button', {
      name: text.conversations.remove.action('Vieja conversacion'),
    })
    // Any timer scheduled by the box or by react-hook-form (its setFocus defers the focus) opens a
    // window between the decision and the move: the student chooses the delete trigger in it.
    const nativeSetTimeout = window.setTimeout.bind(window)
    vi.spyOn(window, 'setTimeout').mockImplementation(((
      handler: TimerHandler,
      ...rest: unknown[]
    ) => {
      if (/react-hook-form|QuestionBox/.test(new Error().stack ?? '')) {
        nativeSetTimeout(() => trigger.focus(), 0)
      }
      return nativeSetTimeout(handler, ...(rest as [number?]))
    }) as typeof window.setTimeout)
    // What had the focus each time the box was focused by code.
    const activeWhenTheBoxWasFocused: (Element | null)[] = []
    const nativeFocus = HTMLTextAreaElement.prototype.focus
    vi.spyOn(HTMLTextAreaElement.prototype, 'focus').mockImplementation(function (
      this: HTMLTextAreaElement,
      options?: FocusOptions,
    ) {
      activeWhenTheBoxWasFocused.push(document.activeElement)
      nativeFocus.call(this, options)
    })

    release()
    expect(await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')).toBeVisible()
    await waitFor(() => expect(box).toHaveValue(''))
    // Let the timers that were already queued run: two turns of the task queue.
    await new Promise((resolve) => nativeSetTimeout(resolve, 0))
    await new Promise((resolve) => nativeSetTimeout(resolve, 0))

    for (const active of activeWhenTheBoxWasFocused) {
      expect(
        active === null ||
          active === document.body ||
          (box as HTMLTextAreaElement).form?.contains(active),
      ).toBe(true)
    }
  })
})
