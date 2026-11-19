import { useQuery } from '@tanstack/react-query'
import { subjectService } from '../services/subjectService'
import type { Subject } from '../types/api'

/** The cache key includes the user id and the subject id. */
export function useSubject(userId: string, subjectId: string) {
  return useQuery<Subject>({
    queryKey: ['subject', userId, subjectId],
    queryFn: () => subjectService.get(subjectId),
  })
}
