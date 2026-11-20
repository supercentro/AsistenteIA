import { apiClient } from '../lib/apiClient'
import type { Conversation, Message } from '../types/api'

export const conversationService = {
  async list(subjectId: string): Promise<Conversation[]> {
    const { data } = await apiClient.get<Conversation[]>('/conversations', {
      params: { subject_id: subjectId },
    })
    return data
  },

  async messages(conversationId: string): Promise<Message[]> {
    const { data } = await apiClient.get<Message[]>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
    )
    return data
  },

  async remove(conversationId: string): Promise<void> {
    await apiClient.delete(`/conversations/${encodeURIComponent(conversationId)}`)
  },

  /** Every conversation of the account in every subject, also those no longer visible. */
  async removeAll(): Promise<void> {
    await apiClient.delete('/users/me/conversations')
  },
}
