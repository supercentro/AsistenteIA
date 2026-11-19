import { apiClient } from '../lib/apiClient'
import type { Enrollment } from '../types/api'

function enrollmentsPath(subjectId: string): string {
  return `/subjects/${encodeURIComponent(subjectId)}/enrollments`
}

export const enrollmentService = {
  async list(subjectId: string): Promise<Enrollment[]> {
    const { data } = await apiClient.get<Enrollment[]>(enrollmentsPath(subjectId))
    return data
  },

  /** The e-mail goes exactly as typed; the API matches it in lowercase. */
  async create(subjectId: string, studentEmail: string): Promise<Enrollment> {
    const { data } = await apiClient.post<Enrollment>(enrollmentsPath(subjectId), {
      student_email: studentEmail,
    })
    return data
  },

  async remove(subjectId: string, studentId: string): Promise<void> {
    await apiClient.delete(`${enrollmentsPath(subjectId)}/${encodeURIComponent(studentId)}`)
  },
}
