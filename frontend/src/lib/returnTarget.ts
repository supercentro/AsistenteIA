const MAX_LENGTH = 2048
const AUTH_ROUTES = /^\/(login|register)\/*$/
const PLACEHOLDER_ORIGIN = 'http://placeholder.invalid'
// Control characters and backslash: browsers normalise them in ways that can turn a path into a host.
const UNSAFE_CHARACTERS = new RegExp(String.raw`[\u0000-\u001f\u007f\\]`)

/** True when the path, once dot segments, percent-encoding and case are resolved, is login/register. */
function resolvesToAuthenticationScreen(value: string): boolean {
  try {
    const url = new URL(value, PLACEHOLDER_ORIGIN)
    if (url.origin !== PLACEHOLDER_ORIGIN) {
      return true
    }
    return AUTH_ROUTES.test(decodeURIComponent(url.pathname).toLowerCase())
  } catch {
    return true
  }
}

/**
 * Where to go after signing in. Only a plain internal path is accepted: an absolute or
 * protocol-relative URL, a scheme, a backslash, control characters or the authentication screens
 * themselves are ignored (open-redirect and loop protection).
 */
export function safeReturnTarget(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0 || value.length > MAX_LENGTH) {
    return null
  }
  if (UNSAFE_CHARACTERS.test(value)) {
    return null
  }
  if (!value.startsWith('/') || value.startsWith('//')) {
    return null
  }
  return resolvesToAuthenticationScreen(value) ? null : value
}
