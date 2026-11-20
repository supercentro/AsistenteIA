import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { API, errorResponse, studentUser } from '../tests/api'
import { CHAT_PAGE, conversationItem, defaultAsk, messageItem, serveChat } from '../tests/chat'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

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
const thread = (label: string) => [
  messageItem({ id: `u-${label}`, content: `Pregunta ${label}` }),
  messageItem({ id: `a-${label}`, role: 'assistant', content: `Respuesta ${label}` }),
]

async function openChat() {
  const state = serveChat({
    conversations: [first(), second()],
    messages: { c1: thread('uno'), c2: thread('dos') },
  })
  const view = renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
  await screen.findByRole('textbox', { name: text.box.label })
  return { state, ...view }
}

describe('Review: nothing changes the open conversation while a question is pending', () => {
  it('locks the conversation list, the new-conversation action and the deletions until the answer arrives', async () => {
    const { state } = await openChat()
    state.ask = async (body, current) => {
      await delay(500)
      return defaultAsk(body, current)
    }
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')

    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Una pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Segunda conversacion' })).toBeDisabled(),
    )
    expect(screen.getByRole('button', { name: text.conversations.new })).toBeDisabled()
    await user.click(
      screen.getByRole('button', {
        name: text.conversations.remove.action('Segunda conversacion'),
      }),
    )
    expect(screen.getByRole('button', { name: text.conversations.remove.confirm })).toBeDisabled()
  })

  it('shows the answer in the conversation the question was asked in, and keeps it selected', async () => {
    const { state } = await openChat()
    state.ask = async (body, current) => {
      await delay(400)
      return defaultAsk(body, current)
    }
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')

    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Pregunta nueva')
    await user.click(screen.getByRole('button', { name: text.box.send }))
    await screen.findByText('La fotosintesis ocurre en los cloroplastos [1].')

    expect(state.asked[0]?.conversation_id).toBe('c1')
    expect(screen.getByRole('button', { name: 'Primera conversacion' })).toHaveAttribute(
      'aria-current',
      'true',
    )
    expect(screen.getByText('Respuesta uno')).toBeVisible()
    expect(screen.queryByText('Respuesta dos')).not.toBeInTheDocument()
  })
})

describe('Review: a 404 on a question of an open conversation is the conversation, not the subject', () => {
  it('says the conversation is not available, keeps the page and the question, and refreshes the list', async () => {
    const { state } = await openChat()
    server.use(http.post(`${API}/chat`, () => errorResponse(404, 'NOT_FOUND')))
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')
    const listCalls = state.listCalls

    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Mi pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    expect(await screen.findByText(text.conversations.messagesUnavailable)).toBeVisible()
    expect(screen.queryByRole('heading', { name: text.unavailable.title })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: text.box.label })).toHaveValue('Mi pregunta')
    await waitFor(() => expect(state.listCalls).toBeGreaterThan(listCalls))
  })

  it('sends the kept question as a new conversation the next time', async () => {
    const { state } = await openChat()
    server.use(http.post(`${API}/chat`, () => errorResponse(404, 'NOT_FOUND')))
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText('Respuesta uno')
    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Mi pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))
    await screen.findByText(text.conversations.messagesUnavailable)
    server.use(
      http.post(`${API}/chat`, async ({ request }) => {
        state.asked.push((await request.json()) as never)
        return HttpResponse.json({
          conversation_id: 'fresh',
          message_id: 'a-fresh',
          answer: 'Respuesta nueva',
          no_material: false,
          sources: [],
        })
      }),
    )

    await user.click(screen.getByRole('button', { name: text.box.send }))

    expect(await screen.findByText('Respuesta nueva')).toBeVisible()
    expect(state.asked[0]).not.toHaveProperty('conversation_id')
  })

  it('still says the subject is not available for a 404 on a new conversation', async () => {
    await openChat()
    server.use(http.post(`${API}/chat`, () => errorResponse(404, 'NOT_FOUND')))
    const user = userEvent.setup()
    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Mi pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    expect(await screen.findByRole('heading', { name: text.unavailable.title })).toBeVisible()
  })
})

describe('Review: a thread that turned out to be gone is not continued', () => {
  it('sends the next question as a new conversation when the opened conversation had no messages (404)', async () => {
    const state = serveChat({ conversations: [first()], messages: {} })
    renderApp({ route: CHAT_PAGE, session: { user: studentUser } })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Primera conversacion' }))
    await screen.findByText(text.conversations.messagesUnavailable)

    await user.click(screen.getByRole('textbox', { name: text.box.label }))
    await user.paste('Otra pregunta')
    await user.click(screen.getByRole('button', { name: text.box.send }))

    await waitFor(() => expect(state.asked).toHaveLength(1))
    expect(state.asked[0]).not.toHaveProperty('conversation_id')
  })
})
