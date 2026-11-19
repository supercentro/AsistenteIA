import { apiClient } from '../lib/apiClient'
import type { Subject, SubjectCreate } from '../types/api'

export const subjectService = {
  async list(): Promise<Subject[]> {
    const { data } = await apiClient.get<Subject[]>('/subjects')
    return data
  },

  async create(payload: SubjectCreate): Promise<Subject> {
    const { data } = await apiClient.post<Subject>('/subjects', payload)
    return data
  },

  async get(subjectId: string): Promise<Subject> {
    const { data } = await apiClient.get<Subject>(`/subjects/${encodeURIComponent(subjectId)}`)
    return data
  },
}
