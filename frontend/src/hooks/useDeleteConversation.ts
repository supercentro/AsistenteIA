import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiError'
import { conversationService } from '../services/conversationService'
import type { Conversation } from '../types/api'

export type DeleteConversationResult = 'deleted' | 'gone'

/** A 404 means the conversation no longer existed: the row goes away and the caller says so. */
export function useDeleteConversation(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  const listKey = ['conversations', userId, subjectId]
  return useMutation<DeleteConversationResult, Error, string>({
    mutationFn: async (conversationId) => {
      try {
        await conversationService.remove(conversationId)
        return 'deleted'
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return 'gone'
        }
        throw error
      }
    },
    onSuccess: async (_result, conversationId) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      queryClient.setQueryData<Conversation[]>(listKey, (current) =>
        current?.filter((item) => item.id !== conversationId),
      )
      queryClient.removeQueries({ queryKey: ['messages', userId, conversationId] })
    },
  })
}
