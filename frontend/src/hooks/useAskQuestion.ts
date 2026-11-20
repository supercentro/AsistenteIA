import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiError'
import { chatService } from '../services/chatService'
import type { ChatResponse, Message } from '../types/api'

export interface AskVariables {
  conversationId: string | null
  message: string
}

/**
 * On success both messages are added to the cache (when the thread is known to be complete) and
 * the data is then reconciled with the server: invalidating an active query cancels the request
 * that is still on its way, so an older answer cannot undo the change. After a timeout the turn may have been saved, so
 * the conversation and the list are requested again.
 */
export function useAskQuestion(userId: string, subjectId: string) {
  const queryClient = useQueryClient()
  const listKey = ['conversations', userId, subjectId]

  return useMutation<ChatResponse, Error, AskVariables>({
    mutationFn: ({ conversationId, message }) =>
      chatService.ask({ subjectId, conversationId, message }),
    onSuccess: (response, variables) => {
      const messagesKey = ['messages', userId, response.conversation_id]
      const now = new Date().toISOString()
      const asked: Message = {
        id: `local-${response.message_id}`,
        role: 'user',
        content: variables.message,
        created_at: now,
        sources: [],
      }
      const answered: Message = {
        id: response.message_id,
        role: 'assistant',
        content: response.answer,
        created_at: now,
        sources: response.sources,
      }
      const current = queryClient.getQueryData<Message[]>(messagesKey)
      if (current) {
        queryClient.setQueryData<Message[]>(messagesKey, [...current, asked, answered])
      } else if (variables.conversationId === null) {
        // A new conversation holds exactly these two messages.
        queryClient.setQueryData<Message[]>(messagesKey, [asked, answered])
      }
      void queryClient.invalidateQueries({ queryKey: listKey })
      void queryClient.invalidateQueries({ queryKey: messagesKey })
    },
    onError: (error, variables) => {
      if (error instanceof ApiError && error.kind === 'timeout') {
        void queryClient.invalidateQueries({ queryKey: listKey })
        if (variables.conversationId) {
          void queryClient.invalidateQueries({
            queryKey: ['messages', userId, variables.conversationId],
          })
        }
      }
    },
  })
}
