import { describe, expect, it } from 'vitest'
import { PRIVACY_POLICY_VERSION } from './privacyPolicy'

describe('PRIVACY_POLICY_VERSION', () => {
  it('is a non-empty version string of at most 20 characters (backend column limit)', () => {
    expect(PRIVACY_POLICY_VERSION.length).toBeGreaterThanOrEqual(1)
    expect(PRIVACY_POLICY_VERSION.length).toBeLessThanOrEqual(20)
    expect(PRIVACY_POLICY_VERSION).toBe(PRIVACY_POLICY_VERSION.trim())
  })
})
