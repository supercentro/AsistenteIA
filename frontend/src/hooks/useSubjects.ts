import { useQuery } from '@tanstack/react-query'
import { subjectService } from '../services/subjectService'
import type { Subject } from '../types/api'

/** The cache key includes the user id so a different user never reads another user's data. */
export function useSubjects(userId: string) {
  return useQuery<Subject[]>({
    queryKey: ['subjects', userId],
    queryFn: () => subjectService.list(),
  })
}
