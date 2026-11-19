import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiError'
import { enrollmentService } from '../services/enrollmentService'
import type { Enrollment } from '../types/api'

export type RemoveResult = 'removed' | 'gone'

/**
 * A 404 means the enrollment no longer existed: the row goes away and the caller says so. The
 * same status also comes from a subject that is gone, so the subject and the list are requested
 * again and the page shows its own not-found view if needed.
 */
export function useRemoveEnrollment(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  return useMutation<RemoveResult, Error, string>({
    mutationFn: async (studentId) => {
      try {
        await enrollmentService.remove(subjectId, studentId)
        return 'removed'
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return 'gone'
        }
        throw error
      }
    },
    onSuccess: async (result, studentId) => {
      await queryClient.cancelQueries({ queryKey: ['enrollments', userId, subjectId] })
      queryClient.setQueryData<Enrollment[]>(['enrollments', userId, subjectId], (current) =>
        current?.filter((item) => item.student_id !== studentId),
      )
      if (result === 'gone') {
        void queryClient.invalidateQueries({ queryKey: ['subject', userId, subjectId] })
        void queryClient.invalidateQueries({ queryKey: ['enrollments', userId, subjectId] })
      }
    },
  })
}
