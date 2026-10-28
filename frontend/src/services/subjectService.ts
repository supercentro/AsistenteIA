import { apiClient } from '../lib/apiClient'
import type { Subject } from '../types/api'

export const subjectService = {
  async list(): Promise<Subject[]> {
    const { data } = await apiClient.get<Subject[]>('/subjects')
    return data
  },
}
