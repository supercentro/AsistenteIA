import { useMutation, useQueryClient } from '@tanstack/react-query'
import { subjectService } from '../services/subjectService'
import type { Subject, SubjectCreate } from '../types/api'

export function useCreateSubject(userId: string) {
  const queryClient = useQueryClient()
  return useMutation<Subject, Error, SubjectCreate>({
    mutationFn: (payload) => subjectService.create(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subjects', userId] }),
  })
}
