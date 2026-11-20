import { useQuery } from '@tanstack/react-query'
import { conversationService } from '../services/conversationService'
import type { Conversation } from '../types/api'

/** The cache key includes the user id and the subject id. */
export function useConversations(userId: string, subjectId: string) {
  return useQuery<Conversation[]>({
    queryKey: ['conversations', userId, subjectId],
    queryFn: () => conversationService.list(subjectId),
  })
}
