import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  endSession,
  getSnapshot,
  getValidToken,
  onSessionEnd,
  setUser,
  startSession,
  subscribe,
  takeNotice,
} from './session'
import type { User } from '../types/api'

const TOKEN = 'header.payload-secret-value.signature'

const user: User = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Ana',
  email: 'ana@example.com',
  role: 'student',
  consent_version: null,
  consent_accepted_at: null,
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-28T12:00:00Z'))
  endSession('signed-out')
  takeNotice()
})

afterEach(() => {
  endSession('signed-out')
  takeNotice()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('session store', () => {
  it('starts anonymous', () => {
    expect(getSnapshot()).toMatchObject({ token: null, user: null, expiresAt: null })
    expect(getValidToken()).toBeNull()
  })

  it('keeps the token and the profile after start and setUser', () => {
    startSession(TOKEN, 3600)
    setUser(user)

    expect(getValidToken()).toBe(TOKEN)
    expect(getSnapshot().user).toEqual(user)
  })

  it('notifies subscribers on every change and stops after unsubscribe', () => {
    const listener = vi.fn()
    const unsubscribe = subscribe(listener)

    startSession(TOKEN, 3600)
    setUser(user)
    endSession('signed-out')
    expect(listener).toHaveBeenCalledTimes(3)

    unsubscribe()
    startSession(TOKEN, 3600)
    expect(listener).toHaveBeenCalledTimes(3)
  })

  it('returns a new snapshot object only when something changed', () => {
    const first = getSnapshot()
    expect(getSnapshot()).toBe(first)
    startSession(TOKEN, 3600)
    expect(getSnapshot()).not.toBe(first)
  })

  it('ends the session once: a second end is a no-op with no notice and no callbacks', () => {
    const ended = vi.fn()
    onSessionEnd(ended)
    startSession(TOKEN, 3600)

    endSession('unauthorized')
    endSession('unauthorized')

    expect(ended).toHaveBeenCalledTimes(1)
    expect(takeNotice()).toBe('unauthorized')
    expect(takeNotice()).toBeNull()
  })
})

describe('expiry', () => {
  it('ends the session by itself when the announced lifetime elapses', () => {
    startSession(TOKEN, 60)
    setUser(user)

    vi.advanceTimersByTime(59_000)
    expect(getValidToken()).toBe(TOKEN)

    vi.advanceTimersByTime(1_000)
    expect(getSnapshot()).toMatchObject({ token: null, user: null })
    expect(takeNotice()).toBe('expired')
  })

  it('never hands out a token whose lifetime elapsed even if the timer did not fire', () => {
    startSession(TOKEN, 60)
    // A sleeping computer moves the clock without running timers.
    vi.setSystemTime(new Date('2026-10-28T12:01:01Z'))

    expect(getValidToken()).toBeNull()
    expect(getSnapshot().token).toBeNull()
    expect(takeNotice()).toBe('expired')
  })

  it('clamps very large lifetimes to a timer delay the platform accepts', () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    startSession(TOKEN, 10 * 365 * 24 * 3600)

    const delays = setTimeoutSpy.mock.calls.map((call) => call[1] as number)
    expect(Math.max(...delays)).toBeLessThanOrEqual(2 ** 31 - 1)
    vi.advanceTimersByTime(2 ** 31 - 1)
    expect(getValidToken()).toBe(TOKEN)
  })

  it.each([0, -5, Number.NaN, Number.POSITIVE_INFINITY])(
    'refuses a session with the invalid lifetime %s',
    (lifetime) => {
      expect(() => startSession(TOKEN, lifetime)).toThrow(RangeError)
      expect(getSnapshot().token).toBeNull()
    },
  )

  it('replaces the timer when a new session starts', () => {
    startSession(TOKEN, 60)
    startSession('second-token', 3600)

    vi.advanceTimersByTime(120_000)
    expect(getValidToken()).toBe('second-token')
  })
})

describe('ending a session leaves no residue', () => {
  it.each(['expired', 'unauthorized', 'signed-out', 'login-failed'] as const)(
    'clears token, profile and timer and runs end callbacks for %s',
    (reason) => {
      const ended = vi.fn()
      const off = onSessionEnd(ended)
      startSession(TOKEN, 60)
      setUser(user)
      const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')

      endSession(reason)

      expect(getSnapshot()).toMatchObject({ token: null, user: null, expiresAt: null })
      expect(clearTimeoutSpy).toHaveBeenCalled()
      expect(vi.getTimerCount()).toBe(0)
      expect(ended).toHaveBeenCalledWith(reason)
      expect(takeNotice()).toBe(reason)
      off()
    },
  )

  it('starts the next session from an empty state', () => {
    startSession(TOKEN, 60)
    setUser(user)
    endSession('signed-out')

    startSession('next-token', 60)

    expect(getSnapshot().user).toBeNull()
  })
})

describe('where the session is stored', () => {
  it('writes nothing to local storage, session storage, cookies or the URL', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    const cookieSetter = vi.spyOn(document, 'cookie', 'set')

    startSession(TOKEN, 3600)
    setUser(user)
    endSession('signed-out')

    expect(setItem).not.toHaveBeenCalled()
    expect(cookieSetter).not.toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(window.location.href).not.toContain(TOKEN)
  })
})

describe('logging', () => {
  it('never prints the token or the profile across start, use, expiry and end', () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    )

    startSession(TOKEN, 60)
    setUser(user)
    getValidToken()
    vi.advanceTimersByTime(61_000)
    startSession(TOKEN, 60)
    endSession('unauthorized')

    const printed = JSON.stringify(spies.flatMap((spy) => spy.mock.calls))
    expect(printed).not.toContain('secret-value')
    expect(printed).not.toContain(user.email)
  })
})
