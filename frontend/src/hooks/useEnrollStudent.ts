import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiError'
import { enrollmentService } from '../services/enrollmentService'
import type { Enrollment } from '../types/api'

/**
 * The 404 of an enrollment is ambiguous by design (no account, or the subject itself is gone), so
 * after one the subject is requested again and the page shows its own not-found view if needed.
 */
export function useEnrollStudent(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  return useMutation<Enrollment, Error, string>({
    mutationFn: (studentEmail) => enrollmentService.create(subjectId, studentEmail),
    onSuccess: async (created) => {
      // An older refresh still on its way must not undo this change when it answers.
      await queryClient.cancelQueries({ queryKey: ['enrollments', userId, subjectId] })
      const key = ['enrollments', userId, subjectId]
      const current = queryClient.getQueryData<Enrollment[]>(key)
      if (current) {
        queryClient.setQueryData<Enrollment[]>(key, [
          ...current.filter((item) => item.id !== created.id),
          created,
        ])
      } else {
        // The list is not loaded (still loading, or failed): a one-row list would be a lie.
        void queryClient.invalidateQueries({ queryKey: key })
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 404) {
        void queryClient.invalidateQueries({ queryKey: ['subject', userId, subjectId] })
      }
    },
  })
}
