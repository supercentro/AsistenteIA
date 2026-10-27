import axios from 'axios'

/**
 * Shared Axios instance. Only `services/` modules may use it.
 * Token handling (in memory, never localStorage) is added by the auth change.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
})
