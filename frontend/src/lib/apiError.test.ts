import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios'
import { describe, expect, it } from 'vitest'
import { ApiError, messageFor, parseRetryAfter, toApiError } from './apiError'
import { strings } from './strings.es'

function httpError(status: number, data: unknown, headers: Record<string, string> = {}) {
  const config = { headers: new AxiosHeaders() }
  const response = { status, data, headers, config, statusText: '' } as AxiosResponse
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, {}, response)
}

describe('toApiError', () => {
  it('keeps status and the stable code but never the server message or details', () => {
    const error = toApiError(
      httpError(409, { code: 'CONFLICT', message: 'ana@example.com exists', details: { a: 1 } }),
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, code: 'CONFLICT', kind: 'http' })
    expect(JSON.stringify(error)).not.toContain('ana@example.com')
    expect(error.message).not.toContain('ana@example.com')
    expect(JSON.stringify(error)).not.toContain('"a"')
  })

  it.each([
    ['unknown code', { code: 'WEIRD_CODE', message: 'x' }, 'WEIRD_CODE'],
    ['non-string code', { code: 42 }, null],
    ['array body', ['a'], null],
    ['text body', '<html>boom</html>', null],
    ['empty body', '', null],
    ['null body', null, null],
    ['markup in code', { code: '<script>alert(1)</script>' }, null],
    ['oversized code', { code: 'A'.repeat(500) }, null],
  ])('handles %s', (_name, body, expectedCode) => {
    expect(toApiError(httpError(400, body)).code).toBe(expectedCode)
  })

  it('classifies a failure without a response as a network error', () => {
    const error = toApiError(new AxiosError('Network Error', 'ERR_NETWORK'))
    expect(error).toMatchObject({ kind: 'network', status: null, code: null })
  })

  it('classifies an aborted-by-timeout request as a timeout', () => {
    const error = toApiError(new AxiosError('timeout of 15000ms exceeded', 'ECONNABORTED'))
    expect(error.kind).toBe('timeout')
  })

  it('wraps anything else as an unknown error without keeping its text', () => {
    const error = toApiError(new Error('password=hunter2'))
    expect(error.kind).toBe('unknown')
    expect(error.message).not.toContain('hunter2')
  })

  it('returns an ApiError unchanged', () => {
    const original = new ApiError({ kind: 'http', status: 404, code: 'NOT_FOUND' })
    expect(toApiError(original)).toBe(original)
  })
})

describe('parseRetryAfter', () => {
  it.each([
    ['30', 30],
    ['1', 1],
    ['3600', 3600],
  ])('accepts %s', (value, expected) => {
    expect(parseRetryAfter(value)).toBe(expected)
  })

  it.each(['', 'abc', '-5', '0', '3601', '1e9', '12.5', ' ', '99999999999', 'Wed, 21 Oct 2026'])(
    'rejects %j',
    (value) => {
      expect(parseRetryAfter(value)).toBeNull()
    },
  )

  it('rejects an absent header', () => {
    expect(parseRetryAfter(undefined)).toBeNull()
  })

  it('is read from the response headers of a 429', () => {
    const error = toApiError(httpError(429, { code: 'RATE_LIMITED' }, { 'retry-after': '42' }))
    expect(error.retryAfterSeconds).toBe(42)
  })
})

describe('messageFor', () => {
  it.each(Object.entries(strings.errors.byCode))(
    'maps the code %s to its Spanish text',
    (code, text) => {
      const error = new ApiError({ kind: 'http', status: 400, code })
      expect(messageFor(error)).toBe(text)
    },
  )

  it('falls back to the status class when the code is unknown or absent', () => {
    expect(messageFor(new ApiError({ kind: 'http', status: 503, code: 'WHATEVER' }))).toBe(
      strings.errors.byStatus.server,
    )
    expect(messageFor(new ApiError({ kind: 'http', status: 418, code: null }))).toBe(
      strings.errors.byStatus.client,
    )
    expect(messageFor(new ApiError({ kind: 'http', status: 500, code: null }))).toBe(
      strings.errors.byStatus.server,
    )
  })

  it('states the wait for a rate limit and omits the number when it is not trustworthy', () => {
    const withWait = new ApiError({
      kind: 'http',
      status: 429,
      code: 'RATE_LIMITED',
      retryAfterSeconds: 42,
    })
    const without = new ApiError({
      kind: 'http',
      status: 429,
      code: 'RATE_LIMITED',
      retryAfterSeconds: null,
    })
    expect(messageFor(withWait)).toBe(strings.errors.rateLimitedIn(42))
    expect(messageFor(without)).toBe(strings.errors.byCode.RATE_LIMITED)
  })

  it('has dedicated texts for network failure, timeout and unknown errors', () => {
    expect(messageFor(new ApiError({ kind: 'network' }))).toBe(strings.errors.network)
    expect(messageFor(new ApiError({ kind: 'timeout' }))).toBe(strings.errors.timeout)
    expect(messageFor(new ApiError({ kind: 'unknown' }))).toBe(strings.errors.unknown)
  })

  it('lets a form override the text of a code without exposing server text', () => {
    const error = new ApiError({ kind: 'http', status: 409, code: 'CONFLICT' })
    expect(messageFor(error, { CONFLICT: 'custom' })).toBe('custom')
  })
})

describe('toApiError - the reason of an upload 422', () => {
  it.each([
    'MALFORMED_MULTIPART',
    'FILE_PART_MISSING',
    'UNEXPECTED_FIELDS',
    'EMPTY_FILE',
    'INVALID_FILENAME',
  ])('keeps the documented reason %s', (reason) => {
    const error = toApiError(
      httpError(422, { code: 'VALIDATION_ERROR', message: 'x', details: { reason } }),
    )
    expect(error.reason).toBe(reason)
  })

  it.each([
    ['an unlisted value', { reason: 'SOMETHING_ELSE' }],
    ['markup', { reason: '<b>EMPTY_FILE</b>' }],
    ['a lowercase value', { reason: 'empty_file' }],
    ['a non-string value', { reason: 42 }],
    ['no reason', { other: 'EMPTY_FILE' }],
  ])('drops %s', (_name, details) => {
    const error = toApiError(httpError(422, { code: 'VALIDATION_ERROR', message: 'x', details }))
    expect(error.reason).toBeNull()
  })

  it('keeps a reason only on a 422', () => {
    const error = toApiError(
      httpError(409, { code: 'CONFLICT', message: 'x', details: { reason: 'EMPTY_FILE' } }),
    )
    expect(error.reason).toBeNull()
  })

  it('still keeps no other detail and no server text', () => {
    const error = toApiError(
      httpError(422, {
        code: 'VALIDATION_ERROR',
        message: 'secret-file.pdf is empty',
        details: { reason: 'EMPTY_FILE', filename: 'secret-file.pdf' },
      }),
    )
    expect(JSON.stringify(error)).not.toContain('secret-file')
  })
})

describe('Retry-After on a 503', () => {
  it('is kept for a 429 and a 503 and ignored for other statuses', () => {
    expect(
      toApiError(httpError(503, { code: 'X' }, { 'retry-after': '9' })).retryAfterSeconds,
    ).toBe(9)
    expect(
      toApiError(httpError(429, { code: 'X' }, { 'retry-after': '9' })).retryAfterSeconds,
    ).toBe(9)
    expect(
      toApiError(httpError(500, { code: 'X' }, { 'retry-after': '9' })).retryAfterSeconds,
    ).toBeNull()
  })

  it('adds the wait to the message of a 503', () => {
    const error = toApiError(
      httpError(503, { code: 'INGESTION_QUEUE_FULL', message: 'x' }, { 'retry-after': '9' }),
    )
    expect(messageFor(error)).toBe(
      `${strings.errors.byCode.INGESTION_QUEUE_FULL} ${strings.errors.waitSeconds(9)}`,
    )
  })

  it('keeps the plain message of a 503 without the header', () => {
    const error = toApiError(httpError(503, { code: 'INGESTION_QUEUE_FULL', message: 'x' }))
    expect(messageFor(error)).toBe(strings.errors.byCode.INGESTION_QUEUE_FULL)
  })
})
