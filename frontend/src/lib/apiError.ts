import { isAxiosError } from 'axios'
import { strings } from './strings.es'

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'unknown'

/** The reasons the API documents for an upload answered with 422; anything else is dropped. */
export const UPLOAD_REASONS = [
  'MALFORMED_MULTIPART',
  'FILE_PART_MISSING',
  'UNEXPECTED_FIELDS',
  'EMPTY_FILE',
  'INVALID_FILENAME',
] as const
export type UploadReason = (typeof UPLOAD_REASONS)[number]

/** The reasons the API documents for a refused write of topics (409 and 422). */
export const TOPIC_REASONS = ['stale', 'not_ready', 'no_pages', 'overlap', 'page_range'] as const
export type TopicReason = (typeof TOPIC_REASONS)[number]

interface ApiErrorInit {
  kind: ApiErrorKind
  status?: number | null
  code?: string | null
  retryAfterSeconds?: number | null
  reason?: UploadReason | null
  topicReason?: TopicReason | null
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
  /** Documented reason of a 422 upload answer, chosen from a closed list; never server text. */
  readonly reason: UploadReason | null
  readonly topicReason: TopicReason | null

  constructor({
    kind,
    status = null,
    code = null,
    retryAfterSeconds = null,
    reason = null,
    topicReason = null,
  }: ApiErrorInit) {
    super('API request failed')
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
    this.reason = reason
    this.topicReason = topicReason
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

function readReason(status: number, body: unknown): UploadReason | null {
  if (status !== 422 || typeof body !== 'object' || body === null || Array.isArray(body)) {
    return null
  }
  const details = (body as Record<string, unknown>).details
  if (typeof details !== 'object' || details === null || Array.isArray(details)) {
    return null
  }
  const reason = (details as Record<string, unknown>).reason
  return UPLOAD_REASONS.find((known) => known === reason) ?? null
}

function readTopicReason(status: number, body: unknown): TopicReason | null {
  if ((status !== 409 && status !== 422) || typeof body !== 'object' || body === null) {
    return null
  }
  const details = (body as Record<string, unknown>).details
  if (typeof details !== 'object' || details === null) {
    return null
  }
  const reason = (details as Record<string, unknown>).reason
  return TOPIC_REASONS.find((known) => known === reason) ?? null
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
        retryAfterSeconds:
          status === 429 || status === 503 ? parseRetryAfter(headers?.['retry-after']) : null,
        reason: readReason(status, data),
        topicReason: readTopicReason(status, data),
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
  const base = (error.code && byCode[error.code]) || byStatus(error.status)
  if (error.status === 503 && error.retryAfterSeconds !== null) {
    return `${base} ${strings.errors.waitSeconds(error.retryAfterSeconds)}`
  }
  return base
}
