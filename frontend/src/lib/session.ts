import type { User } from '../types/api'

/**
 * The only holder of the access token and the profile. Module-level memory: nothing is written to
 * localStorage, sessionStorage, cookies or the URL, and nothing here logs. Reloading the page
 * loses it by construction. Everything that needs the token reads it from this module.
 */

export type EndReason = 'expired' | 'unauthorized' | 'signed-out' | 'login-failed'

export interface SessionSnapshot {
  readonly token: string | null
  readonly expiresAt: number | null
  readonly user: User | null
}

const ANONYMOUS: SessionSnapshot = { token: null, expiresAt: null, user: null }
// setTimeout stores its delay in a signed 32-bit integer; longer lifetimes re-arm the timer.
const MAX_TIMER_DELAY_MS = 2 ** 31 - 1

let snapshot: SessionSnapshot = ANONYMOUS
let timer: ReturnType<typeof setTimeout> | null = null
let notice: EndReason | null = null
const listeners = new Set<() => void>()
const endListeners = new Set<(reason: EndReason) => void>()

function publish(next: SessionSnapshot): void {
  snapshot = next
  listeners.forEach((listener) => listener())
}

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

function armTimer(expiresAt: number): void {
  clearTimer()
  const remaining = expiresAt - Date.now()
  timer = setTimeout(
    () => {
      timer = null
      if (Date.now() >= expiresAt) {
        endSession('expired')
      } else {
        armTimer(expiresAt)
      }
    },
    Math.min(Math.max(remaining, 0), MAX_TIMER_DELAY_MS),
  )
}

export function getSnapshot(): SessionSnapshot {
  return snapshot
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Runs after every real session end (not after a no-op), e.g. to clear cached server data. */
export function onSessionEnd(listener: (reason: EndReason) => void): () => void {
  endListeners.add(listener)
  return () => {
    endListeners.delete(listener)
  }
}

export function startSession(token: string, expiresInSeconds: number): void {
  if (!Number.isFinite(expiresInSeconds) || expiresInSeconds <= 0) {
    throw new RangeError('Invalid session lifetime')
  }
  const expiresAt = Date.now() + expiresInSeconds * 1000
  armTimer(expiresAt)
  publish({ token, expiresAt, user: null })
}

export function setUser(user: User): void {
  if (snapshot.token === null) {
    return
  }
  publish({ ...snapshot, user })
}

/**
 * The API said the consent is not current (the policy changed during the session): keep the
 * session but forget the accepted version, so the consent gate holds the student again. The
 * acceptance time stays, which tells "the policy changed" apart from "never accepted".
 */
export function markConsentStale(): void {
  if (snapshot.token === null || snapshot.user === null) {
    return
  }
  publish({
    ...snapshot,
    user: { ...snapshot.user, consent_version: null },
  })
}

export function endSession(reason: EndReason): void {
  if (snapshot.token === null && snapshot.user === null) {
    return
  }
  clearTimer()
  notice = reason
  publish(ANONYMOUS)
  endListeners.forEach((listener) => listener(reason))
}

/** The token if it is still valid; an elapsed lifetime ends the session instead of returning it. */
export function getValidToken(): string | null {
  const { token, expiresAt } = snapshot
  if (token === null || expiresAt === null) {
    return null
  }
  if (Date.now() >= expiresAt) {
    endSession('expired')
    return null
  }
  return token
}

/** Reason why the last session ended; stays readable until it is cleared (safe to read twice). */
export function peekNotice(): EndReason | null {
  return notice
}

export function clearNotice(): void {
  notice = null
}

/** Reads and clears the notice in one step. */
export function takeNotice(): EndReason | null {
  const current = notice
  notice = null
  return current
}
