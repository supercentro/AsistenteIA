import { describe, expect, it } from 'vitest'
import { safeReturnTarget } from './returnTarget'

const BACKSLASH = String.fromCharCode(92)
const NEWLINE = String.fromCharCode(10)
const TAB = String.fromCharCode(9)
const NUL = String.fromCharCode(0)

describe('safeReturnTarget', () => {
  it.each(['/subjects', '/subjects/abc-123', '/a/b?x=1#top'])(
    'accepts the internal path %s',
    (target) => {
      expect(safeReturnTarget(target)).toBe(target)
    },
  )

  it.each([
    ['absolute URL', 'https://evil.example/x'],
    ['http URL', 'http://evil.example'],
    ['protocol-relative', '//evil.example'],
    ['backslash trick', `/${BACKSLASH}evil.example`],
    ['backslash after a slash pair', `/${BACKSLASH}/evil.example`],
    ['scheme without slashes', 'javascript:alert(1)'],
    ['data URL', 'data:text/html,<script>alert(1)</script>'],
    ['relative path', 'subjects'],
    ['login route', '/login'],
    ['login with query', '/login?next=/subjects'],
    ['register route', '/register'],
    ['register nested', '/register/'],
    ['empty string', ''],
    ['newline', `/subjects${NEWLINE}/evil`],
    ['tab inside', `/${TAB}evil`],
    ['NUL', `/a${NUL}b`],
    ['very long', '/' + 'a'.repeat(3000)],
  ])('rejects %s', (_name, target) => {
    expect(safeReturnTarget(target)).toBeNull()
  })

  it.each([undefined, null, 42, {}, ['/subjects']])('rejects the non-string %j', (value) => {
    expect(safeReturnTarget(value)).toBeNull()
  })
})
