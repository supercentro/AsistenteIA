import axios, { type InternalAxiosRequestConfig, isAxiosError } from 'axios'
import { ApiError, toApiError } from './apiError'
import { endSession, getSnapshot, getValidToken, markConsentStale } from './session'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Login and registration: never carries the token and a 401 is a plain form error. */
    public?: boolean
  }
}

const REQUEST_TIMEOUT_MS = 15_000

/**
 * Shared Axios instance. Only `services/` modules may use it. The token comes from `lib/session`
 * (memory only) and is attached to API requests that are not marked `public`.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: REQUEST_TIMEOUT_MS,
})

function resolveUrl(config: InternalAxiosRequestConfig): URL | null {
  try {
    return new URL(apiClient.getUri(config), window.location.href)
  } catch {
    return null
  }
}

function targetsApiOrigin(config: InternalAxiosRequestConfig): boolean {
  const target = resolveUrl(config)
  const base = new URL(apiClient.defaults.baseURL ?? '/', window.location.href)
  return target !== null && target.origin === base.origin
}

apiClient.interceptors.request.use((config) => {
  if (config.public || !targetsApiOrigin(config)) {
    return config
  }
  const token = getValidToken()
  if (token === null) {
    // No session (or it just expired): do not send the request at all.
    throw new ApiError({ kind: 'http', status: 401, code: 'UNAUTHORIZED' })
  }
  config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

/** Method, path without query string and status or kind: nothing else may be logged. */
function logFailure(error: unknown, apiError: ApiError): void {
  if (!isAxiosError(error) || !error.config) {
    return
  }
  const url = resolveUrl(error.config as InternalAxiosRequestConfig)
  const method = (error.config.method ?? 'get').toUpperCase()
  console.warn(`[api] ${method} ${url?.pathname ?? '?'} -> ${apiError.status ?? apiError.kind}`)
}

/** True when the failed request was sent with the token of the session that is open now. */
function carriedCurrentToken(error: unknown): boolean {
  return (
    isAxiosError(error) &&
    !error.config?.public &&
    error.config?.headers?.get('Authorization') === `Bearer ${getSnapshot().token}`
  )
}

apiClient.interceptors.response.use(undefined, (error: unknown) => {
  const apiError = toApiError(error)
  if (apiError.status === 401 && carriedCurrentToken(error)) {
    // Only the token of the current session may end it: a late answer to a request sent by a
    // previous session (another user) must not sign the next user out.
    endSession('unauthorized')
  }
  if (
    apiError.status === 403 &&
    apiError.code === 'CONSENT_REQUIRED' &&
    getSnapshot().user?.role === 'student' &&
    carriedCurrentToken(error)
  ) {
    // The policy changed during the session: the consent gate holds the student again. The
    // request is not retried; accepting is the student's own action.
    markConsentStale()
  }
  logFailure(error, apiError)
  return Promise.reject(apiError)
})
