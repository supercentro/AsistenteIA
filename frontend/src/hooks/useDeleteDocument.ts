import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiError'
import { documentService } from '../services/documentService'
import type { Document } from '../types/api'

export type DeleteResult = 'deleted' | 'gone'

/** A 404 means the document no longer existed: the row goes away and the caller says so. */
export function useDeleteDocument(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  return useMutation<DeleteResult, Error, string>({
    mutationFn: async (documentId) => {
      try {
        await documentService.remove(subjectId, documentId)
        return 'deleted'
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return 'gone'
        }
        throw error
      }
    },
    onSuccess: async (_result, documentId) => {
      await queryClient.cancelQueries({ queryKey: ['documents', userId, subjectId] })
      queryClient.setQueryData<Document[]>(['documents', userId, subjectId], (current) =>
        current?.filter((item) => item.id !== documentId),
      )
    },
  })
}
