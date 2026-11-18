import type { User } from '../types/api'
import { PRIVACY_POLICY_VERSION } from './privacyPolicy'

/**
 * True when the user must accept the privacy policy before using the student area: a student whose
 * stored version is not the current one. A usability rule only; the backend refuses the chat with
 * 403 CONSENT_REQUIRED independently. Teachers never send conversations to the processor.
 */
export function isHeldForConsent(user: User | null): boolean {
  return user !== null && user.role === 'student' && user.consent_version !== PRIVACY_POLICY_VERSION
}
