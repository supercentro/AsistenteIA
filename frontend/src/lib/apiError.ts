import { isAxiosError } from 'axios'
import { strings } from './strings.es'

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'unknown'

interface ApiErrorInit {
  kind: ApiErrorKind
  status?: number | null
  code?: string | null
  retryAfterSeconds?: number | null
}

const CODE_PATTERN = /^[A-Z][A-Z0-9_]{0,39}$/
const MAX_RETRY_AFTER_SECONDS = 3600

/**
 * The only error type that leaves the HTTP layer. It deliberately keeps no server text: the
 * server `message` and `details` can echo user input and are never shown or stored.
 */
export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly code: string | null
  readonly retryAfterSeconds: number | null

  constructor({ kind, status = null, code = null, retryAfterSeconds = null }: ApiErrorInit) {
    super('API request failed')
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }

  get isClientError(): boolean {
    return this.status !== null && this.status >= 400 && this.status < 500
  }
}

/** `Retry-After` in whole seconds, accepted only between 1 and 3600; anything else is ignored. */
export function parseRetryAfter(value: unknown): number | null {
  if (typeof value !== 'string' || !/^\d{1,5}$/.test(value)) {
    return null
  }
  const seconds = Number(value)
  return seconds >= 1 && seconds <= MAX_RETRY_AFTER_SECONDS ? seconds : null
}

function readCode(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return null
  }
  const code = (body as Record<string, unknown>).code
  return typeof code === 'string' && CODE_PATTERN.test(code) ? code : null
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }
  if (isAxiosError(error)) {
    if (error.response) {
      const { status, data, headers } = error.response
      return new ApiError({
        kind: 'http',
        status,
        code: readCode(data),
        retryAfterSeconds: status === 429 ? parseRetryAfter(headers?.['retry-after']) : null,
      })
    }
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return new ApiError({ kind: 'timeout' })
    }
    return new ApiError({ kind: 'network' })
  }
  return new ApiError({ kind: 'unknown' })
}

function byStatus(status: number | null): string {
  switch (true) {
    case status === 401:
      return strings.errors.byStatus.unauthorized
    case status === 403:
      return strings.errors.byStatus.forbidden
    case status === 404:
      return strings.errors.byStatus.notFound
    case status === 409:
      return strings.errors.byStatus.conflict
    case status === 422:
      return strings.errors.byStatus.validation
    case status === 429:
      return strings.errors.byStatus.rateLimited
    case status !== null && status >= 500:
      return strings.errors.byStatus.server
    default:
      return strings.errors.byStatus.client
  }
}

/**
 * Spanish text for an error, chosen by code and then by status class. `overrides` lets a form give
 * a code a more specific text. The server message is never used.
 */
export function messageFor(error: ApiError, overrides: Record<string, string> = {}): string {
  if (error.kind === 'network') return strings.errors.network
  if (error.kind === 'timeout') return strings.errors.timeout
  if (error.kind === 'unknown') return strings.errors.unknown

  if (error.code && overrides[error.code]) {
    return overrides[error.code] as string
  }
  if (error.status === 429 && error.retryAfterSeconds !== null) {
    return strings.errors.rateLimitedIn(error.retryAfterSeconds)
  }
  const byCode = strings.errors.byCode as Record<string, string>
  if (error.code && byCode[error.code]) {
    return byCode[error.code] as string
  }
  return byStatus(error.status)
}
