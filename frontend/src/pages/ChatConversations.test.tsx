import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { API, errorResponse, handlers, studentUser, subject, teacherUser } from '../tests/api'
import {
  CHAT_PAGE,
  CHAT_SUBJECT,
  conversationItem,
  messageItem,
  serveChat,
  sourceItem,
} from '../tests/chat'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'
import type { Conversation, Message } from '../types/api'

const text = strings.chat

const first = () =>
  conversationItem({
    id: 'c1',
    last_message_preview: 'Primera conversacion',
    created_at: '2026-11-20T11:00:00Z',
  })
const second = () =>
  conversationItem({
    id: 'c2',
    last_message_preview: 'Segunda conversacion',
    created_at: '2026-11-20T10:00:00Z',
  })
const thread1 = () => [
  messageItem({ id: 'u1', content: 'Pregunta uno' }),
  messageItem({
    id: 'a1',
    role: 'assistant',
    content: 'Respuesta uno',
    sources: [sourceItem()],
    attribution: 'cited',
  }),
]
const thread2 = () => [
  messageItem({ id: 'u2', content: 'Pregunta dos' }),
  messageItem({ id: 'a2', role: 'assistant', content: 'Respuesta dos' }),
]

async function openChat(
  initial: { conversations: Conversation[]; messages: Record<string, Message[]> } = {
    conversations: [first(), second()],
    messages: { c1: thread1(), c2: thread2() },
  },
) {
  const state = serveChat(initial)
  const view = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
  await screen.findByRole('textbox', { name: text.box.label })
  return { state, ...view }
}

describe('Conversations of the subject', () => {
  it('lists the conversations of this subject in the order received, by preview', async () => {
    await openChat()

    const list = await screen.findByRole('list', { name: text.conversations.listLabel })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Primera conversacion')
    expect(rows[1]).toHaveTextContent('Segunda conversacion')
  })

  it('asks the API only for the conversations of this subject', async () => {
    const { state } = await openChat()
    state.conversations.push(
      conversationItem({
        id: 'other',
        subject_id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
        last_message_preview: 'De otra materia',
      }),
    )
    await userEvent.setup().click(screen.getByRole('button', { name: text.conversations.new }))

    expect(screen.queryByText('De otra materia')).not.toBeInTheDocument()
  })

  it('opens a conversation, shows its messages with their sources in order and marks it as current', async () => {
    await openChat()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Segunda conversacion' }))

    const log = await screen.findByRole('log', { name: text.thread.label })
    expect(await within(log).findByText('Pregunta dos')).toBeVisible()
    const texts = within(log)
      .getAllByText(/Pregunta dos|Respuesta dos/)
      .map((node) => node.textContent)
    expect(texts).toEqual(['Pregunta dos', 'Respuesta dos'])
    expect(screen.getByRole('button', { name: 'Segunda conversacion' })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('shows the sources of the messages of an opened conversation', async () => {
    await openChat()
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: 'Primera conversacion' }))

    expect(await screen.findByText(text.sources.cited)).toBeVisible()
    expect(screen.getByText('fotosintesis.txt')).toBeVisible()
  })

  it('continues the opened conversation with the next question', async () => {
    const { state } = await openChat()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Segunda conversacion' }))
    await screen.findByText('Pregunta dos')

    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Y la siguiente')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    await waitFor(() => expect(state.asked).toHaveLength(1))
    expect(state.asked[0]?.conversation_id).toBe('c2')
    expect(await screen.findByText('Y la siguiente', { selector: 'p' })).toBeVisible()
  })

  it('starts a new conversation that sends no conversation id', async () => {
    const { state } = await openChat()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Segunda conversacion' }))
    await screen.findByText('Pregunta dos')

    await user.click(screen.getByRole('button', { name: text.conversations.new }))
    expect(screen.queryByText('Pregunta dos')).not.toBeInTheDocument()
    expect(screen.getByText(text.thread.empty)).toBeVisible()
    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Tema nuevo')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    await waitFor(() => expect(state.asked).toHaveLength(1))
    expect(state.asked[0]).not.toHaveProperty('conversation_id')
  })

  it('shows an empty state when the subject has no conversations', async () => {
    await openChat({ conversations: [], messages: {} })

    expect(await screen.findByText(text.conversations.empty)).toBeVisible()
  })

  it('says the conversation is not available when its messages answer 404, and refreshes the list', async () => {
    const { state } = await openChat({ conversations: [first()], messages: {} })
    const before = state.listCalls

    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: 'Primera conversacion' }))

    expect(await screen.findByText(text.conversations.messagesUnavailable)).toBeVisible()
    await waitFor(() => expect(state.listCalls).toBeGreaterThan(before))
  })

  it('labels a conversation without a preview by its date, so several stay distinguishable', async () => {
    const older = conversationItem({
      id: 'c1',
      last_message_preview: null,
      created_at: '2026-11-20T10:00:00Z',
    })
    const newer = conversationItem({
      id: 'c2',
      last_message_preview: null,
      created_at: '2026-11-21T09:30:00Z',
    })
    await openChat({ conversations: [newer, older], messages: { c1: [], c2: [] } })

    const labels = (await screen.findAllByRole('button', { name: /^Conversación del / })).map(
      (button) => button.textContent,
    )

    expect(labels).toEqual([
      text.conversations.untitled(newer.created_at),
      text.conversations.untitled(older.created_at),
    ])
    expect(new Set(labels).size).toBe(2)
  })

  it('shows a preview with markup as text', async () => {
    await openChat({
      conversations: [conversationItem({ id: 'c1', last_message_preview: '<b>x</b> larga' })],
      messages: { c1: [] },
    })

    expect(await screen.findByRole('button', { name: '<b>x</b> larga' })).toBeVisible()
    expect(document.querySelector('main b')).toBeNull()
  })

  it('has no serious accessibility violation with conversations and an open thread', async () => {
    const { container } = await openChat()
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')

    await expectNoSeriousA11yViolations(container)
  })
})

describe('Deleting one conversation', () => {
  async function askToDelete(preview = 'Primera conversacion') {
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: text.conversations.remove.action(preview) }),
    )
    return user
  }

  it('says it is permanent, sends nothing yet, and deletes after confirming', async () => {
    const { state } = await openChat()
    const user = await askToDelete()

    const panel = screen.getByRole('group', {
      name: text.conversations.remove.question('Primera conversacion'),
    })
    expect(panel).toHaveTextContent(/No se puede deshacer/)
    expect(panel).toHaveTextContent(/mensajes/)
    expect(state.conversations).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: text.conversations.remove.confirm }))

    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Primera conversacion' }),
      ).not.toBeInTheDocument(),
    )
    expect(state.conversations.map((item) => item.id)).toEqual(['c2'])
    expect(screen.getByRole('button', { name: 'Segunda conversacion' })).toBeVisible()
  })

  it('resets the thread when the open conversation is deleted', async () => {
    await openChat()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')

    await user.click(
      screen.getByRole('button', {
        name: text.conversations.remove.action('Primera conversacion'),
      }),
    )
    await user.click(screen.getByRole('button', { name: text.conversations.remove.confirm }))

    await waitFor(() => expect(screen.queryByText('Respuesta uno')).not.toBeInTheDocument())
    expect(screen.getByText(text.thread.empty)).toBeVisible()
  })

  it('cancelling sends nothing and returns the focus to the delete action', async () => {
    const { state } = await openChat()
    const user = await askToDelete()

    await user.click(screen.getByRole('button', { name: text.conversations.remove.cancel }))

    expect(state.conversations).toHaveLength(2)
    const trigger = screen.getByRole('button', {
      name: text.conversations.remove.action('Primera conversacion'),
    })
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('removes the row with a notice when the conversation no longer existed (404)', async () => {
    const { state } = await openChat()
    const user = await askToDelete()
    state.conversations = state.conversations.filter((item) => item.id !== 'c1')

    await user.click(screen.getByRole('button', { name: text.conversations.remove.confirm }))

    expect(await screen.findByText(text.conversations.gone)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Primera conversacion' })).not.toBeInTheDocument()
  })

  it('keeps the conversation and shows an error when the deletion fails, and allows trying again', async () => {
    await openChat()
    server.use(http.delete(`${API}/conversations/:id`, () => errorResponse(500, 'INTERNAL_ERROR')))
    const user = await askToDelete()

    await user.click(screen.getByRole('button', { name: text.conversations.remove.confirm }))

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Primera conversacion' })).toBeVisible()
    expect(screen.getByRole('button', { name: text.conversations.remove.confirm })).toBeEnabled()
  })

  it('disables every confirm control while one deletion is in flight', async () => {
    await openChat()
    server.use(
      http.delete(`${API}/conversations/:id`, async () => {
        await delay(300)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', {
        name: text.conversations.remove.action('Primera conversacion'),
      }),
    )
    await user.click(
      screen.getByRole('button', {
        name: text.conversations.remove.action('Segunda conversacion'),
      }),
    )
    const confirms = screen.getAllByRole('button', { name: text.conversations.remove.confirm })

    await user.click(confirms[0] as HTMLElement)

    await waitFor(() => expect(confirms[1]).toBeDisabled())
  })
})

describe('An answer that was already on its way does not undo a change', () => {
  it('keeps the new messages when an older messages request answers afterwards', async () => {
    const state = serveChat({ conversations: [first()], messages: { c1: thread1() } })
    let calls = 0
    server.use(
      http.get(`${API}/conversations/c1/messages`, async () => {
        calls += 1
        // The answer is a snapshot taken when the request started: the second call is the old one.
        const snapshot = structuredClone(state.messages.c1 ?? [])
        if (calls === 2) {
          await delay(900)
        }
        return HttpResponse.json(snapshot)
      }),
    )
    const { client } = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')

    void client.invalidateQueries({ queryKey: ['messages'] })
    await waitFor(() => expect(calls).toBe(2))
    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Pregunta nueva')
    await user.click(screen.getByRole('button', { name: text.box.send }))
    await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')
    await act(() => new Promise((resolve) => setTimeout(resolve, 1300)))

    expect(screen.getByText('La fotosintesis ocurre en los cloroplastos [1].')).toBeVisible()
    expect(state.asked).toHaveLength(1)
  })

  it('does not bring back a deleted conversation when an older list answers afterwards', async () => {
    const state = serveChat({
      conversations: [first(), second()],
      messages: { c1: thread1(), c2: thread2() },
    })
    let calls = 0
    server.use(
      http.get(`${API}/conversations`, async () => {
        calls += 1
        if (calls > 1) {
          await delay(900)
        }
        return HttpResponse.json([first(), second()])
      }),
    )
    const { client } = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
    const user = userEvent.setup()
    await screen.findByRole('button', { name: 'Primera conversacion' })

    void client.invalidateQueries({ queryKey: ['conversations'] })
    await waitFor(() => expect(calls).toBe(2))
    await user.click(
      screen.getByRole('button', {
        name: text.conversations.remove.action('Primera conversacion'),
      }),
    )
    await user.click(screen.getByRole('button', { name: text.conversations.remove.confirm }))
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Primera conversacion' }),
      ).not.toBeInTheDocument(),
    )
    await act(() => new Promise((resolve) => setTimeout(resolve, 1300)))

    expect(screen.queryByRole('button', { name: 'Primera conversacion' })).not.toBeInTheDocument()
    expect(state.conversations.map((item) => item.id)).toEqual(['c2'])
  })
})

describe('The student subject list: chat links and the whole history', () => {
  const subjects = () => [
    CHAT_SUBJECT,
    subject({ id: '99999999-9999-4999-8999-999999999999', name: 'Quimica' }),
  ]

  it('links each card to its chat and offers the delete-history action', async () => {
    server.use(handlers.subjects(subjects()))
    renderApp({ route: '/subjects', session: { user: studentUser } })

    const link = await screen.findByRole('link', { name: text.openChat('Biologia') })
    expect(link).toHaveAttribute('href', `/subjects/${CHAT_SUBJECT.id}/chat`)
    expect(screen.getByRole('link', { name: text.openChat('Quimica') })).toBeVisible()
    expect(screen.getByRole('button', { name: text.history.action })).toBeVisible()
  })

  it('does not show the chat links or the history action to a teacher', async () => {
    server.use(handlers.subjects(subjects()))
    renderApp({ route: '/subjects', session: { user: teacherUser } })

    await screen.findByText('Biologia')
    expect(screen.queryByRole('link', { name: text.openChat('Biologia') })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: text.history.action })).not.toBeInTheDocument()
  })

  it('says it covers every subject, is permanent and keeps the account, and sends nothing before confirming', async () => {
    const state = serveChat({ conversations: [first()], messages: { c1: thread1() } })
    server.use(handlers.subjects(subjects()))
    renderApp({ route: '/subjects', session: { user: studentUser } })
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: text.history.action }))

    const panel = screen.getByRole('group', { name: text.history.question })
    expect(panel).toHaveTextContent(/todas las asignaturas/i)
    expect(panel).toHaveTextContent(/ya no ve/i)
    expect(panel).toHaveTextContent(/No se puede deshacer/)
    expect(panel).toHaveTextContent(/cuenta/i)
    expect(state.conversations).toHaveLength(1)
  })

  it('deletes the whole history after confirming and shows a notice', async () => {
    const state = serveChat({ conversations: [first(), second()], messages: { c1: thread1() } })
    server.use(handlers.subjects(subjects()))
    renderApp({ route: '/subjects', session: { user: studentUser } })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: text.history.action }))

    await user.click(screen.getByRole('button', { name: text.history.confirm }))

    expect(await screen.findByText(text.history.done)).toBeVisible()
    expect(state.conversations).toEqual([])
  })

  it('cancelling sends nothing', async () => {
    const state = serveChat({ conversations: [first()], messages: {} })
    server.use(handlers.subjects(subjects()))
    renderApp({ route: '/subjects', session: { user: studentUser } })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: text.history.action }))

    await user.click(screen.getByRole('button', { name: text.history.cancel }))

    expect(state.conversations).toHaveLength(1)
    expect(screen.queryByText(text.history.done)).not.toBeInTheDocument()
  })

  it('keeps the history and shows an error when the deletion fails', async () => {
    const state = serveChat({ conversations: [first()], messages: {} })
    server.use(
      handlers.subjects(subjects()),
      http.delete(`${API}/users/me/conversations`, () => errorResponse(500, 'INTERNAL_ERROR')),
    )
    renderApp({ route: '/subjects', session: { user: studentUser } })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: text.history.action }))

    await user.click(screen.getByRole('button', { name: text.history.confirm }))

    expect(await screen.findByText(strings.errors.byStatus.server)).toBeVisible()
    expect(state.conversations).toHaveLength(1)
    expect(screen.queryByText(text.history.done)).not.toBeInTheDocument()
  })
})
