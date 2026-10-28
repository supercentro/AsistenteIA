import { useMutation } from '@tanstack/react-query'
import { authService } from '../services/authService'
import type { RegisterRequest, User } from '../types/api'

export function useRegister() {
  return useMutation<User, Error, RegisterRequest>({
    mutationFn: (payload) => authService.register(payload),
  })
}
