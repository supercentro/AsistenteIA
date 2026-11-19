import { useMutation, useQueryClient } from '@tanstack/react-query'
import { documentService } from '../services/documentService'
import type { Document } from '../types/api'

/** On 202 the pending document is added to the cache at once; the polling reconciles it later. */
export function useUploadDocument(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  return useMutation<Document, Error, File>({
    mutationFn: (file) => documentService.upload(subjectId, file),
    onSuccess: async (created) => {
      // An older refresh still on its way must not undo this change when it answers.
      await queryClient.cancelQueries({ queryKey: ['documents', userId, subjectId] })
      queryClient.setQueryData<Document[]>(['documents', userId, subjectId], (current) =>
        current ? [...current.filter((item) => item.id !== created.id), created] : [created],
      )
    },
  })
}
