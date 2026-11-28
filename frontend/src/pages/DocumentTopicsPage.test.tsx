import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { studentUser, teacherUser } from '../tests/api'
import { EDITOR_PAGE, documentTopics, savedTopics, serveDocumentTopics } from '../tests/topics'
import { renderApp } from '../tests/utils'

const text = strings.topics.editor
const owner = { user: teacherUser }

function open(session = owner) {
  vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', 'true')
  vi.stubEnv('VITE_TEACHER_TOPICS_ENABLED', 'true')
  return renderApp({ route: EDITOR_PAGE, session })
}

afterEach(() => {
  vi.unstubAllEnvs()
})

const field = (label: string, row: number) => screen.getByLabelText(`${label} ${row}`)
const save = () => screen.getByRole('button', { name: text.save })

describe('DocumentTopicsPage - defining topics', () => {
  it('adds a row, saves it and shows the confirmation', async () => {
    const state = serveDocumentTopics()
    const user = userEvent.setup()
    const { container } = open()

    expect(await screen.findByText(text.pagesHelp(10))).toBeVisible()
    await user.click(screen.getByRole('button', { name: text.add }))
    expect(field(text.fieldTitle, 1)).toHaveFocus()
    await user.type(field(text.fieldTitle, 1), '  Modelo relacional ')
    await user.type(field(text.from, 1), '1')
    await user.type(field(text.to, 1), '4')
    await user.click(save())

    expect(await screen.findByText(text.saved)).toBeVisible()
    expect(state.writes).toEqual([
      { revision: 0, topics: [{ title: 'Modelo relacional', start_page: 1, end_page: 4 }] },
    ])
    await expectNoSeriousA11yViolations(container)
  })

  it('works with the keyboard only', async () => {
    const state = serveDocumentTopics()
    const user = userEvent.setup()
    open()

    const add = await screen.findByRole('button', { name: text.add })
    add.focus()
    await user.keyboard('{Enter}')
    await user.keyboard('Claves')
    await user.tab()
    await user.keyboard('2')
    await user.tab()
    await user.keyboard('3{Enter}')

    await waitFor(() => expect(state.writes).toHaveLength(1))
  })

  it.each([
    ['', '1', '2', text.errors.title],
    ['A', '0', '2', text.errors.pages(10)],
    ['A', '3', '2', text.errors.pages(10)],
    ['A', '1', '11', text.errors.pages(10)],
    ['A', '1.5', '2', text.errors.pages(10)],
  ])('refuses «%s» %s-%s before sending it', async (title, from, to, message) => {
    const state = serveDocumentTopics()
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('button', { name: text.add }))
    if (title) await user.type(field(text.fieldTitle, 1), title)
    await user.type(field(text.from, 1), from)
    await user.type(field(text.to, 1), to)
    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(state.writes).toEqual([])
  })

  it('refuses overlapping ranges', async () => {
    const state = serveDocumentTopics()
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('button', { name: text.add }))
    await user.type(field(text.fieldTitle, 1), 'A')
    await user.type(field(text.from, 1), '1')
    await user.type(field(text.to, 1), '5')
    await user.click(screen.getByRole('button', { name: text.add }))
    await user.type(field(text.fieldTitle, 2), 'B')
    await user.type(field(text.from, 2), '5')
    await user.type(field(text.to, 2), '6')
    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(text.errors.overlap)
    expect(state.writes).toEqual([])
  })
})

describe('DocumentTopicsPage - changing saved topics', () => {
  it('saves a rename without any warning', async () => {
    const state = serveDocumentTopics(savedTopics())
    const user = userEvent.setup()
    open()

    await user.type(await screen.findByLabelText(`${text.fieldTitle} 1`), ' relacional')
    await user.click(save())

    expect(await screen.findByText(text.saved)).toBeVisible()
    expect(screen.queryByRole('button', { name: text.warning.confirm })).toBeNull()
    expect(state.writes[0]!.revision).toBe(2)
  })

  it('warns before saving changed pages and sends nothing until confirmed', async () => {
    const state = serveDocumentTopics(savedTopics())
    const user = userEvent.setup()
    open()

    const end = await screen.findByLabelText(`${text.to} 1`)
    await user.clear(end)
    await user.type(end, '3')
    await user.click(save())

    const warning = screen.getByRole('group', { name: text.warning.question })
    expect(warning).toHaveTextContent(
      /volverán a contar desde la semana del \d{2}\/\d{2}\/\d{4} y se mostrarán cuando esa semana termine\./,
    )
    expect(warning).toHaveFocus()
    expect(state.writes).toEqual([])

    await user.click(screen.getByRole('button', { name: text.warning.confirm }))

    await waitFor(() => expect(state.writes).toHaveLength(1))
  })

  it('warns again when the set was cleared before', async () => {
    const state = serveDocumentTopics(savedTopics({ topics: [] }))
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('button', { name: text.add }))
    await user.type(field(text.fieldTitle, 1), 'A')
    await user.type(field(text.from, 1), '1')
    await user.type(field(text.to, 1), '2')
    await user.click(save())

    expect(screen.getByRole('group', { name: text.warning.question })).toBeVisible()
    expect(state.writes).toEqual([])
  })

  it('keeps the typed rows when the save is refused as stale, and can reload', async () => {
    const state = serveDocumentTopics(savedTopics())
    state.fail = { status: 409, reason: 'stale' }
    const user = userEvent.setup()
    open()

    await user.type(await screen.findByLabelText(`${text.fieldTitle} 1`), ' nuevo')
    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(text.errors.stale)
    expect(field(text.fieldTitle, 1)).toHaveValue('Modelo nuevo')
    expect(screen.queryByText('server text')).toBeNull()

    state.fail = null
    await user.click(screen.getByRole('button', { name: text.reload }))

    await waitFor(() => expect(field(text.fieldTitle, 1)).toHaveValue('Modelo'))
    expect(state.reads).toBe(2)
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus()
  })

  it('removes a row', async () => {
    const state = serveDocumentTopics(savedTopics())
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('button', { name: text.remove(2) }))
    await user.click(save())
    await user.click(screen.getByRole('button', { name: text.warning.confirm }))

    await waitFor(() => expect(state.writes[0]?.topics).toHaveLength(1))
  })
})

describe('DocumentTopicsPage - not available', () => {
  it.each(['no_pages', 'not_ready'] as const)('explains a %s document', async (reason) => {
    serveDocumentTopics(documentTopics({ editable: false, reason, last_page: null }))
    open()

    expect(await screen.findByText(text.unavailable[reason])).toBeVisible()
    expect(screen.queryByRole('button', { name: text.save })).toBeNull()
  })

  it('shows the forbidden page to a student without any request', async () => {
    const state = serveDocumentTopics()
    open({ user: studentUser })

    expect(await screen.findByText(strings.forbidden.title)).toBeVisible()
    expect(state.reads).toBe(0)
  })

  it('is not found while the switch is off', async () => {
    const state = serveDocumentTopics()
    renderApp({ route: EDITOR_PAGE, session: owner })

    expect(await screen.findByText(strings.notFound.title)).toBeVisible()
    expect(state.reads).toBe(0)
  })
})

describe('DocumentTopicsPage - while saving, reloading and moving focus', () => {
  it('keeps the typed rows when the reload fails, and says so', async () => {
    const state = serveDocumentTopics(savedTopics())
    state.fail = { status: 409, reason: 'stale' }
    const user = userEvent.setup()
    open()

    await user.type(await screen.findByLabelText(`${text.fieldTitle} 1`), ' nuevo')
    await user.click(save())
    state.failRead = 503
    await user.click(await screen.findByRole('button', { name: text.reload }))

    await waitFor(() => expect(state.reads).toBe(2))
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2))
    expect(field(text.fieldTitle, 1)).toHaveValue('Modelo nuevo')
    expect(screen.getByText(text.errors.stale)).toBeVisible()
    expect(screen.queryByText('server text')).toBeNull()
  })

  it('does not let the rows change while a save is in flight', async () => {
    const state = serveDocumentTopics(savedTopics())
    let answer = () => {}
    state.hold = new Promise<void>((resolve) => {
      answer = resolve
    })
    const user = userEvent.setup()
    open()

    const title = await screen.findByLabelText(`${text.fieldTitle} 1`)
    await user.type(title, ' relacional')
    await user.click(save())
    await waitFor(() => expect(state.writes).toHaveLength(1))

    await user.type(title, ' perdido')
    await user.type(field(text.from, 1), '9')
    await user.type(field(text.to, 1), '9')
    expect(title).toHaveValue('Modelo relacional')
    expect(field(text.from, 1)).toHaveValue('1')
    expect(field(text.to, 1)).toHaveValue('4')
    expect(screen.getByRole('button', { name: text.add })).toBeDisabled()
    expect(screen.getByRole('button', { name: text.remove(1) })).toBeDisabled()

    answer()
    expect(await screen.findByText(text.saved)).toBeVisible()
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus()
  })

  it('returns the focus to the save button when the warning is cancelled', async () => {
    serveDocumentTopics(savedTopics())
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('button', { name: text.remove(2) }))
    await user.click(save())
    await user.click(screen.getByRole('button', { name: text.warning.cancel }))

    expect(save()).toHaveFocus()
  })

  it('counts the length of a title in characters, as the server does', async () => {
    const long = '\u{1D400}'.repeat(150)
    const state = serveDocumentTopics(
      savedTopics({ topics: [{ title: long, start_page: 1, end_page: 4 }] }),
    )
    const user = userEvent.setup()
    open()

    await screen.findByLabelText(`${text.fieldTitle} 1`)
    await user.click(save())

    await waitFor(() => expect(state.writes[0]?.topics[0]?.title).toBe(long))
  })
})
