import { useQuery } from '@tanstack/react-query'
import { enrollmentService } from '../services/enrollmentService'
import type { Enrollment } from '../types/api'

/** The cache key includes the user id and the subject id. No polling: enrolling is synchronous. */
export function useEnrollments(userId: string, subjectId: string) {
  return useQuery<Enrollment[]>({
    queryKey: ['enrollments', userId, subjectId],
    queryFn: () => enrollmentService.list(subjectId),
  })
}
