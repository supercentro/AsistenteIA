import { apiClient } from '../lib/apiClient'
import type { ChatResponse } from '../types/api'

/** The model alone may take 30 s: an ordinary 15 s request limit would cut valid answers. */
const CHAT_TIMEOUT_MS = 60_000

interface AskInput {
  subjectId: string
  /** The open conversation, or null for a new one (the field is then not sent). */
  conversationId: string | null
  message: string
}

export const chatService = {
  async ask({ subjectId, conversationId, message }: AskInput): Promise<ChatResponse> {
    const { data } = await apiClient.post<ChatResponse>(
      '/chat',
      {
        subject_id: subjectId,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        message,
      },
      { timeout: CHAT_TIMEOUT_MS },
    )
    return data
  },
}
