import { useMutation, useQueryClient } from '@tanstack/react-query'
import { conversationService } from '../services/conversationService'
import type { Conversation } from '../types/api'

/** Deletes every conversation of the account (all subjects) and empties what the cache holds. */
export function useDeleteHistory(userId: string) {
  const queryClient = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: () => conversationService.removeAll(),
    onSuccess: async () => {
      await queryClient.cancelQueries({ queryKey: ['conversations', userId] })
      queryClient.setQueriesData<Conversation[]>({ queryKey: ['conversations', userId] }, [])
      queryClient.removeQueries({ queryKey: ['messages', userId] })
    },
  })
}
