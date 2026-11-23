import { afterEach, describe, expect, it, vi } from 'vitest'
import { teacherActivityEnabled } from './features'

describe('teacherActivityEnabled', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('is off when the variable is absent', () => {
    expect(teacherActivityEnabled()).toBe(false)
  })

  it.each(['', 'false', 'TRUE', '1', 'yes', ' true'])('is off for %j', (value) => {
    vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', value)

    expect(teacherActivityEnabled()).toBe(false)
  })

  it('is on only for the exact value true', () => {
    vi.stubEnv('VITE_TEACHER_ACTIVITY_ENABLED', 'true')

    expect(teacherActivityEnabled()).toBe(true)
  })
})
