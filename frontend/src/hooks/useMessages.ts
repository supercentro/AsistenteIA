import { useQuery } from '@tanstack/react-query'
import { conversationService } from '../services/conversationService'
import type { Message } from '../types/api'

/** Messages of one conversation; nothing is requested while no conversation is open. */
export function useMessages(userId: string, conversationId: string | null) {
  return useQuery<Message[]>({
    queryKey: ['messages', userId, conversationId],
    queryFn: () => conversationService.messages(conversationId as string),
    enabled: conversationId !== null,
  })
}
