import { afterEach, describe, expect, it } from 'vitest'
import {
  studentUser,
  teacherUser,
  TOKEN_VALUE,
  outdatedStudent,
  unconsentedStudent,
} from '../tests/api'
import { isHeldForConsent } from './consent'
import { PRIVACY_POLICY_VERSION } from './privacyPolicy'
import { endSession, getSnapshot, markConsentStale, setUser, startSession } from './session'

afterEach(() => {
  endSession('signed-out')
})

describe('isHeldForConsent', () => {
  it('holds a student who never accepted', () => {
    expect(isHeldForConsent(unconsentedStudent)).toBe(true)
  })

  it('holds a student whose accepted version is not the current one', () => {
    expect(isHeldForConsent(outdatedStudent)).toBe(true)
  })

  it('does not hold a student with the current version', () => {
    expect(isHeldForConsent(studentUser)).toBe(false)
  })

  it('never holds a teacher, whatever the stored version', () => {
    expect(isHeldForConsent({ ...teacherUser, consent_version: null })).toBe(false)
    expect(isHeldForConsent({ ...teacherUser, consent_version: '2025-01-v0' })).toBe(false)
  })

  it('does not hold when there is no profile yet', () => {
    expect(isHeldForConsent(null)).toBe(false)
  })

  it('compares with the current policy version exactly', () => {
    expect(
      isHeldForConsent({ ...studentUser, consent_version: PRIVACY_POLICY_VERSION + ' ' }),
    ).toBe(true)
  })
})

describe('markConsentStale', () => {
  it('forgets the accepted version but keeps the acceptance time and the rest', () => {
    startSession(TOKEN_VALUE, 3600)
    setUser(studentUser)

    markConsentStale()

    const user = getSnapshot().user
    expect(user?.consent_version).toBeNull()
    expect(user?.consent_accepted_at).toBe(studentUser.consent_accepted_at)
    expect(user?.id).toBe(studentUser.id)
    expect(user?.role).toBe('student')
  })

  it('does nothing without a signed-in user', () => {
    markConsentStale()
    expect(getSnapshot().user).toBeNull()

    startSession(TOKEN_VALUE, 3600)
    markConsentStale()
    expect(getSnapshot().user).toBeNull()
  })
})
