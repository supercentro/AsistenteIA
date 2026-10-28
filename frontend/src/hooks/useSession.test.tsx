import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { endSession, setUser, startSession } from '../lib/session'
import { useSession } from './useSession'

afterEach(() => {
  endSession('signed-out')
})

describe('useSession', () => {
  it('is anonymous until a session starts and follows the store', () => {
    const { result } = renderHook(() => useSession())
    expect(result.current.status).toBe('anonymous')
    expect(result.current.user).toBeNull()

    act(() => startSession('token', 60))
    expect(result.current.status).toBe('loading-profile')

    act(() =>
      setUser({
        id: '1',
        name: 'Ana',
        email: 'ana@example.com',
        role: 'teacher',
        consent_version: null,
        consent_accepted_at: null,
      }),
    )
    expect(result.current.status).toBe('authenticated')
    expect(result.current.user?.role).toBe('teacher')

    act(() => endSession('signed-out'))
    expect(result.current.status).toBe('anonymous')
  })

  it('exposes no token to components', () => {
    const { result } = renderHook(() => useSession())
    act(() => startSession('secret-token', 60))
    expect(JSON.stringify(result.current)).not.toContain('secret-token')
  })
})
