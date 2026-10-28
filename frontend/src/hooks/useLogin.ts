import { useMutation } from '@tanstack/react-query'
import { clearNotice, endSession, setUser, startSession } from '../lib/session'
import { authService } from '../services/authService'
import type { LoginRequest, User } from '../types/api'

/** The credentials were accepted but the session could not be completed (profile or lifetime). */
export class LoginIncompleteError extends Error {
  constructor() {
    super('Login could not be completed')
    this.name = 'LoginIncompleteError'
  }
}

/** Login, then the profile; the session counts as established only when both succeed. */
export function useLogin() {
  return useMutation<User, Error, LoginRequest>({
    mutationFn: async (credentials) => {
      const token = await authService.login(credentials)
      try {
        startSession(token.access_token, token.expires_in)
      } catch {
        throw new LoginIncompleteError()
      }
      try {
        const user = await authService.me()
        setUser(user)
        return user
      } catch {
        endSession('login-failed')
        clearNotice()
        throw new LoginIncompleteError()
      }
    },
  })
}
