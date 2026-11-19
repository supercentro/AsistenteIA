import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, delay, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { strings } from '../lib/strings.es'
import { API, documentItem, errorBody, errorResponse, teacherUser } from '../tests/api'
import { SUBJECT, SUBJECT_PAGE, readMultipart, serveSubject } from '../tests/materials'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

const text = strings.materials

function uploadUrl() {
  return `${API}/subjects/${SUBJECT.id}/documents`
}

async function openPage() {
  // The type filter of the file input is a hint, so the tests may also choose unsupported files.
  const user = userEvent.setup({ applyAccept: false })
  renderApp({ route: SUBJECT_PAGE, session: { user: teacherUser } })
  const input = (await screen.findByLabelText(text.upload.fileLabel)) as HTMLInputElement
  const submit = screen.getByRole('button', { name: text.upload.submit })
  return { user, input, submit }
}

function file(name = 'notas.txt', type = 'text/plain', content = 'contenido') {
  return new File([content], name, { type })
}

describe('Upload - accepted', () => {
  it('sends the single field "file", shows the pending document at once and clears the input', async () => {
    const state = serveSubject()
    const seen: { fields: string[]; name: string } = { fields: [], name: '' }
    server.use(
      http.post(uploadUrl(), async ({ request }) => {
        const body = await readMultipart(request)
        seen.fields = body.fields
        seen.name = body.filename ?? ''
        const created = documentItem({
          id: 'new',
          filename: seen.name,
          content_type: 'text/plain',
          size_bytes: 9,
          status: 'pending',
          chunks_count: 0,
        })
        state.documents.push(created)
        return HttpResponse.json(created, { status: 202 })
      }),
    )
    const { user, input, submit } = await openPage()

    await user.upload(input, file())
    await user.click(submit)

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('notas.txt')).toBeVisible()
    expect(within(row).getByText(text.status.pending)).toBeVisible()
    expect(within(row).getByText(text.documents.types['text/plain']!)).toBeVisible()
    expect(seen).toEqual({ fields: ['file'], name: 'notas.txt' })
    await waitFor(() => expect(input.files).toHaveLength(0))
  })

  it('keeps the row shown from the 202 even if the list does not include it yet', async () => {
    serveSubject([])
    server.use(
      http.post(uploadUrl(), () =>
        HttpResponse.json(documentItem({ id: 'new', filename: 'nuevo.txt', status: 'pending' }), {
          status: 202,
        }),
      ),
    )
    const { user, input, submit } = await openPage()

    await user.upload(input, file('nuevo.txt'))
    await user.click(submit)

    expect(await screen.findByText('nuevo.txt')).toBeVisible()
  })

  it('shows the formats, and that this MVP is for tests with fictitious documents only', async () => {
    serveSubject()
    await openPage()

    const notice = screen.getByText(/documentos ficticios/)
    expect(notice).toHaveTextContent(/PDF/)
    expect(notice).toHaveTextContent(/\.txt/)
    expect(notice).toHaveTextContent(/\.md/)
    expect(notice).toHaveTextContent(/datos personales/)
    expect(notice).toHaveTextContent(/MVP/)
  })
})

describe('Upload - nothing to send', () => {
  it('sends no request and asks for a file when none was chosen', async () => {
    serveSubject()
    let calls = 0
    server.use(
      http.post(uploadUrl(), () => {
        calls += 1
        return HttpResponse.json(documentItem(), { status: 202 })
      }),
    )
    const { user, submit } = await openPage()

    await user.click(submit)

    expect(await screen.findByText(text.upload.noFile)).toBeVisible()
    expect(calls).toBe(0)
  })
})

describe('Upload - every refusal has its own Spanish message', () => {
  const refusals: [string, () => Response, string][] = [
    ['413', () => errorResponse(413, 'PAYLOAD_TOO_LARGE'), strings.errors.byCode.PAYLOAD_TOO_LARGE],
    [
      '415',
      () => errorResponse(415, 'UNSUPPORTED_MEDIA_TYPE'),
      strings.errors.byCode.UNSUPPORTED_MEDIA_TYPE,
    ],
    [
      '409 quota',
      () => errorResponse(409, 'DOCUMENT_QUOTA_EXCEEDED'),
      strings.errors.byCode.DOCUMENT_QUOTA_EXCEEDED,
    ],
    ['408', () => errorResponse(408, 'REQUEST_TIMEOUT'), strings.errors.byCode.REQUEST_TIMEOUT],
    [
      '503 queue full',
      () => errorResponse(503, 'INGESTION_QUEUE_FULL'),
      strings.errors.byCode.INGESTION_QUEUE_FULL,
    ],
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
    ...(
      [
        'MALFORMED_MULTIPART',
        'FILE_PART_MISSING',
        'UNEXPECTED_FIELDS',
        'EMPTY_FILE',
        'INVALID_FILENAME',
      ] as const
    ).map((reason): [string, () => Response, string] => [
      `422 ${reason}`,
      () =>
        HttpResponse.json(errorBody('VALIDATION_ERROR', 'server side text', { reason }), {
          status: 422,
        }),
      text.upload.reasons[reason],
    ]),
    [
      '422 without a reason',
      () => errorResponse(422, 'VALIDATION_ERROR'),
      strings.errors.byCode.VALIDATION_ERROR,
    ],
    ['network failure', () => HttpResponse.error(), strings.errors.network],
  ]

  it.each(refusals)('%s', async (_name, respond, message) => {
    const state = serveSubject([documentItem({ filename: 'existente.pdf' })])
    server.use(http.post(uploadUrl(), () => respond()))
    const { user, input, submit } = await openPage()
    await screen.findByText('existente.pdf')

    await user.upload(input, file('nuevo.txt'))
    await user.click(submit)

    expect(await screen.findByText(message)).toBeVisible()
    expect(screen.queryByText('server side text')).not.toBeInTheDocument()
    expect(screen.queryByText('nuevo.txt')).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(state.documents).toHaveLength(1)
  })

  it('uses a different message for every case', () => {
    // A 422 without a reason and a 429 without Retry-After intentionally reuse generic texts.
    const specific = refusals.filter(([name]) => !name.includes('without'))
    const messages = specific.map(([, , message]) => message)
    expect(new Set(messages).size).toBe(messages.length)
  })

  it('never writes the file name or the server message to the console', async () => {
    const logged: string[] = []
    const originals = { error: console.error, warn: console.warn, log: console.log }
    console.error = (...args: unknown[]) => logged.push(args.join(' '))
    console.warn = (...args: unknown[]) => logged.push(args.join(' '))
    console.log = (...args: unknown[]) => logged.push(args.join(' '))
    try {
      serveSubject()
      server.use(http.post(uploadUrl(), () => errorResponse(415, 'UNSUPPORTED_MEDIA_TYPE')))
      const { user, input, submit } = await openPage()

      await user.upload(input, file('secreto-personal.exe', 'application/octet-stream'))
      await user.click(submit)
      await screen.findByText(strings.errors.byCode.UNSUPPORTED_MEDIA_TYPE)
    } finally {
      Object.assign(console, originals)
    }
    expect(logged.join('\n')).not.toContain('secreto-personal')
    expect(logged.join('\n')).not.toContain('server side text')
  })
})

describe('Upload - in flight and after the subject changed', () => {
  it('disables the upload control while the request is pending so it is not sent twice', async () => {
    serveSubject()
    let calls = 0
    server.use(
      http.post(uploadUrl(), async () => {
        calls += 1
        await delay(150)
        return HttpResponse.json(documentItem({ status: 'pending' }), { status: 202 })
      }),
    )
    const { user, input, submit } = await openPage()

    await user.upload(input, file())
    await user.click(submit)

    await waitFor(() => expect(submit).toBeDisabled())
    expect(input).toBeDisabled()
    await user.click(submit)
    await waitFor(() => expect(submit).toBeEnabled())
    expect(calls).toBe(1)
  })

  it.each([
    [404, 'NOT_FOUND', text.notFound.title],
    [403, 'FORBIDDEN', strings.forbidden.title],
  ])('shows the matching view when the upload answers %s', async (status, code, title) => {
    serveSubject([documentItem({ filename: 'viejo.pdf' })])
    server.use(http.post(uploadUrl(), () => errorResponse(status, code)))
    const { user, input, submit } = await openPage()

    await user.upload(input, file())
    await user.click(submit)

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
    expect(screen.queryByText('viejo.pdf')).not.toBeInTheDocument()
  })

  it('shows a file name with markup and direction characters as text', async () => {
    serveSubject()
    const tricky = `<b>x</b>‮fdp.exe${'a'.repeat(150)}.txt`
    server.use(
      http.post(uploadUrl(), () =>
        HttpResponse.json(documentItem({ filename: tricky, status: 'pending' }), { status: 202 }),
      ),
    )
    const { user, input, submit } = await openPage()

    await user.upload(input, file('x.txt'))
    await user.click(submit)

    const row = await screen.findByRole('listitem')
    expect(row.querySelector('b')).toBeNull()
    expect(within(row).getByText(tricky).closest('p')?.className).toContain('break-words')
  })
})
