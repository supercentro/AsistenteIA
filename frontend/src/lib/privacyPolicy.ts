/**
 * Current privacy-policy version the UI sends when the user accepts it.
 * Must equal the backend `PRIVACY_POLICY_VERSION` (default in backend/app/core/config.py).
 * A backend test and a Vitest test fail if the two drift or the value is invalid.
 */
export const PRIVACY_POLICY_VERSION = '2026-10-v1'
