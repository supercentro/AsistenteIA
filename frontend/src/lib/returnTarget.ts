const MAX_LENGTH = 2048
const AUTH_ROUTES = /^\/(login|register)(?:[/?#]|$)/
// Control characters and backslash: browsers normalise them in ways that can turn a path into a host.
const UNSAFE_CHARACTERS = new RegExp(String.raw`[\u0000-\u001f\u007f\\]`)

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
  if (AUTH_ROUTES.test(value)) {
    return null
  }
  return value
}
