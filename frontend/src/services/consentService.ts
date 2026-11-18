import { apiClient } from '../lib/apiClient'
import type { User } from '../types/api'

export const consentService = {
  /** Records the acceptance of one policy version; the API answers with the updated profile. */
  async accept(consentVersion: string): Promise<User> {
    const { data } = await apiClient.post<User>('/users/me/consent', {
      consent_version: consentVersion,
    })
    return data
  },
}
