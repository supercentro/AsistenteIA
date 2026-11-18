import { useMutation } from '@tanstack/react-query'
import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import { getSnapshot, setUser } from '../lib/session'
import { consentService } from '../services/consentService'
import type { User } from '../types/api'

/**
 * Accepts the current policy version; on success the stored profile replaces the held one, but
 * only if the session that sent the request is still the open one: a late answer to a student who
 * has left must not write that student's profile into the next user's session.
 */
export function useAcceptConsent() {
  return useMutation<User, Error, void, { token: string | null }>({
    onMutate: () => ({ token: getSnapshot().token }),
    mutationFn: () => consentService.accept(PRIVACY_POLICY_VERSION),
    onSuccess: (user, _variables, context) => {
      if (context?.token != null && context.token === getSnapshot().token) {
        setUser(user)
      }
    },
  })
}
