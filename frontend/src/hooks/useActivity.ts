import { useQuery } from '@tanstack/react-query'
import { activityService } from '../services/activityService'
import type { ActivityResponse } from '../types/api'

/**
 * The aggregate activity of a subject, read once per visit.
 *
 * The key holds the user and the subject, never a window. No automatic retry, refetch or interval,
 * and nothing is kept once the page is left (`gcTime: 0`), so no earlier response can be compared
 * with a later one: the page offers no comparison between periods (docs/frontend-standards.md).
 */
export function useActivity(userId: string, subjectId: string) {
  return useQuery<ActivityResponse>({
    queryKey: ['activity', userId, subjectId],
    queryFn: () => activityService.get(subjectId),
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    refetchInterval: false,
  })
}
