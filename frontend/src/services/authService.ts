import { apiClient } from '../lib/apiClient'
import type { LoginRequest, RegisterRequest, TokenResponse, User } from '../types/api'

export const authService = {
  async login(credentials: LoginRequest): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>('/auth/login', credentials, {
      public: true,
    })
    return data
  },

  async register(payload: RegisterRequest): Promise<User> {
    const { data } = await apiClient.post<User>('/auth/register', payload, { public: true })
    return data
  },

  async me(): Promise<User> {
    const { data } = await apiClient.get<User>('/users/me')
    return data
  },
}
