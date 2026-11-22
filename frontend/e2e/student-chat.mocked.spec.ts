import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/types/api.generated.ts'
import { API, errorBody, mockApi, signInHandlers, student, subject } from './support/mockApi.ts'

type Conversation = components['schemas']['Conversation']
type Message = components['schemas']['Message']

// Spanish copy lives in src/lib/strings.es.ts; the texts used here are the visible labels.
const SUBJECT = subject({ name: 'Biologia General' })
const BASE = `/subjects/${SUBJECT.id}`

const source = {
  chunk_id: 'c1',
  document_id: 'd1',
  filename: 'mitocondrias.txt',
  page_number: null,
  rank: 1,
  snippet: 'Las mitocondrias producen la energia de la celula.',
}

async function openChat(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('ana@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.getByRole('link', { name: 'Preguntar sobre Biologia General' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Biologia General' })).toBeVisible()
}

function chatHandlers(state: {
  conversations: Conversation[]
  messages: Record<string, Message[]>
}) {
  return {
    ...signInHandlers(student, [SUBJECT]),
    [`GET ${BASE}`]: () => ({ status: 200, body: SUBJECT }),
    'GET /conversations': () => ({ status: 200, body: state.conversations }),
    'GET /conversations/c1/messages': () => ({ status: 200, body: state.messages['c1'] ?? [] }),
  }
}

test('a student asks, reads the sources, continues and deletes a conversation with the keyboard', async ({
  page,
}) => {
  const state = {
    conversations: [] as Conversation[],
    messages: {} as Record<string, Message[]>,
  }
  const asked: unknown[] = []
  await mockApi(page, {
    ...chatHandlers(state),
    'POST /chat': (request) => {
      const body = request.postDataJSON() as { message: string; conversation_id?: string }
      asked.push(body)
      const thread = state.messages['c1'] ?? []
      thread.push(
        {
          id: `u${thread.length}`,
          role: 'user',
          content: body.message,
          created_at: '2026-11-20T10:00:00Z',
          sources: [],
        },
        {
          id: `a${thread.length}`,
          role: 'assistant',
          content: 'Respuesta de prueba.',
          created_at: '2026-11-20T10:00:01Z',
          sources: [source],
        },
      )
      state.messages['c1'] = thread
      state.conversations = [
        {
          id: 'c1',
          subject_id: SUBJECT.id,
          created_at: '2026-11-20T10:00:00Z',
          last_message_preview: thread[0]?.content ?? null,
        },
      ]
      return {
        status: 200,
        body: {
          conversation_id: 'c1',
          message_id: `a${thread.length - 1}`,
          answer: 'Respuesta de prueba.',
          no_material: false,
          sources: [source],
        },
      }
    },
    'DELETE /conversations/c1': () => {
      state.conversations = []
      state.messages = {}
      return { status: 204 }
    },
  })

  await openChat(page)
  await expect(page.getByText(/Gemini \(Google\)/)).toBeVisible()
  const box = page.getByRole('textbox', { name: 'Pregunta' })
  await box.fill('Que son las mitocondrias?')
  await page.getByRole('button', { name: 'Enviar' }).click()

  await expect(page.getByText('Respuesta de prueba.')).toBeVisible()
  await expect(page.getByText('Material consultado')).toBeVisible()
  await expect(box).toBeFocused()
  await expect(page.getByText('mitocondrias.txt')).toBeVisible()
  await page.getByText('Ver fragmento').click()
  await expect(page.getByText('Las mitocondrias producen la energia de la celula.')).toBeVisible()
  expect(asked).toEqual([{ subject_id: SUBJECT.id, message: 'Que son las mitocondrias?' }])

  await box.fill('Y donde estan?')
  await page.getByRole('button', { name: 'Enviar' }).click()
  await expect.poll(() => asked.length).toBe(2)
  expect(asked[1]).toEqual({
    subject_id: SUBJECT.id,
    conversation_id: 'c1',
    message: 'Y donde estan?',
  })

  // Keyboard only: open the confirmation of the conversation, move to the confirm control, press Enter.
  await page
    .getByRole('button', { name: /Eliminar la conversación «Que son las mitocondrias\?»/ })
    .focus()
  await page.keyboard.press('Enter')
  const group = page.getByRole('group', { name: /¿Eliminar la conversación/ })
  await expect(group).toBeFocused()
  await expect(group.getByText('No se puede deshacer', { exact: false })).toBeVisible()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await expect(page.getByText('Todavía no hay conversaciones en esta asignatura.')).toBeVisible()
})

test('the failures of a question are explained and the question stays in the box', async ({
  page,
}) => {
  const replies = [
    { status: 429, body: errorBody('RATE_LIMITED'), headers: { 'Retry-After': '7' } },
    { status: 502, body: errorBody('LLM_UNAVAILABLE') },
    { status: 502, body: errorBody('LLM_BLOCKED') },
  ]
  let call = 0
  await mockApi(page, {
    ...chatHandlers({ conversations: [], messages: {} }),
    'POST /chat': () => replies[call++] ?? { status: 500, body: errorBody('INTERNAL_ERROR') },
  })

  await openChat(page)
  const box = page.getByRole('textbox', { name: 'Pregunta' })
  await box.fill('Mi pregunta')
  const send = page.getByRole('button', { name: 'Enviar' })

  await send.click()
  await expect(page.getByText('Espere 7 segundos', { exact: false })).toBeVisible()
  await expect(page.getByText('misma conexión', { exact: false })).toBeVisible()
  await send.click()
  await expect(page.getByText('El asistente no está disponible', { exact: false })).toBeVisible()
  await send.click()
  await expect(page.getByText('Reformúlela', { exact: false })).toBeVisible()
  await expect(box).toHaveValue('Mi pregunta')
  await expect(page.getByText('server side text')).toHaveCount(0)
})

test('the whole history is deleted from the subject list after a confirmation', async ({
  page,
}) => {
  let deleted = 0
  await mockApi(page, {
    ...signInHandlers(student, [SUBJECT]),
    'DELETE /users/me/conversations': () => {
      deleted += 1
      return { status: 204 }
    },
  })
  await page.goto('/login')
  await page.getByLabel('Correo electrónico').fill('ana@example.com')
  await page.getByLabel('Contraseña').fill('a-very-long-password')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await page.getByRole('button', { name: 'Borrar todo mi historial' }).click()
  const group = page.getByRole('group', { name: '¿Borrar todo el historial de conversaciones?' })
  await expect(
    group.getByText('también las de asignaturas que ya no ve', { exact: false }),
  ).toBeVisible()
  expect(deleted).toBe(0)
  await page.getByRole('button', { name: 'Borrar todo el historial' }).click()

  await expect(page.getByText('Se borró todo el historial de conversaciones.')).toBeVisible()
  expect(deleted).toBe(1)
})

test('the chat has no horizontal scrolling at 320 px with a long answer and a long file name', async ({
  page,
}) => {
  const long = 'x'.repeat(300)
  const state = {
    conversations: [
      {
        id: 'c1',
        subject_id: SUBJECT.id,
        created_at: '2026-11-20T10:00:00Z',
        last_message_preview: long,
      },
    ] as Conversation[],
    messages: {
      c1: [
        { id: 'u', role: 'user', content: long, created_at: '2026-11-20T10:00:00Z', sources: [] },
        {
          id: 'a',
          role: 'assistant',
          content: long,
          created_at: '2026-11-20T10:00:01Z',
          sources: [{ ...source, filename: `${long}.txt` }],
        },
      ],
    } as Record<string, Message[]>,
  }
  await mockApi(page, chatHandlers(state))
  await page.setViewportSize({ width: 320, height: 700 })

  await openChat(page)
  await page.getByRole('button', { name: long, exact: true }).click()
  await expect(page.getByText('Material consultado')).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)
})

test('an answer that arrives after the delete confirmation was opened does not take its focus', async ({
  page,
}) => {
  const state = {
    conversations: [
      {
        id: 'c1',
        subject_id: SUBJECT.id,
        created_at: '2026-11-20T10:00:00Z',
        last_message_preview: 'Que son las mitocondrias?',
      },
    ] as Conversation[],
    messages: {
      c1: [
        {
          id: 'u0',
          role: 'user',
          content: 'Que son las mitocondrias?',
          created_at: '2026-11-20T10:00:00Z',
          sources: [],
        },
        {
          id: 'a0',
          role: 'assistant',
          content: 'Respuesta anterior.',
          created_at: '2026-11-20T10:00:01Z',
          sources: [source],
        },
      ],
    } as Record<string, Message[]>,
  }
  // The answer is held back by an explicit gate that the test releases: no fixed wait.
  let release: () => void = () => undefined
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await mockApi(page, {
    ...chatHandlers(state),
    'POST /chat': (request) => {
      const asked = request.postDataJSON() as { message: string }
      // The thread of the server holds the answer too: the page refetches it after the answer.
      state.messages['c1']?.push(
        {
          id: 'u1',
          role: 'user',
          content: asked.message,
          created_at: '2026-11-20T10:01:00Z',
          sources: [],
        },
        {
          id: 'a1',
          role: 'assistant',
          content: 'Respuesta tardia.',
          created_at: '2026-11-20T10:01:01Z',
          sources: [source],
        },
      )
      return {
        status: 200,
        body: {
          conversation_id: 'c1',
          message_id: 'a1',
          answer: 'Respuesta tardia.',
          no_material: false,
          sources: [source],
        },
      }
    },
    'DELETE /conversations/c1': () => {
      state.conversations = []
      return { status: 204 }
    },
  })
  await page.route(`${API}/chat`, async (route) => {
    await gate
    await route.fallback()
  })

  await openChat(page)
  await page.getByRole('button', { name: 'Que son las mitocondrias?', exact: true }).click()
  await expect(page.getByText('Respuesta anterior.')).toBeVisible()
  await page.getByRole('textbox', { name: 'Pregunta' }).fill('Y la membrana?')
  await page.getByRole('button', { name: 'Enviar' }).click()
  await expect(page.getByRole('button', { name: 'Enviando…' })).toBeDisabled()

  await page
    .getByRole('button', { name: /Eliminar la conversación «Que son las mitocondrias\?»/ })
    .focus()
  await page.keyboard.press('Enter')
  const group = page.getByRole('group', { name: /¿Eliminar la conversación/ })
  await expect(group).toBeFocused()
  // The confirm control cannot be used while the answer is on its way.
  await expect(group.getByRole('button', { name: 'Eliminar conversación' })).toBeDisabled()

  release()

  await expect(page.getByText('Respuesta tardia.')).toBeVisible()
  await expect(group).toBeFocused()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await expect(page.getByText('Todavía no hay conversaciones en esta asignatura.')).toBeVisible()
})
