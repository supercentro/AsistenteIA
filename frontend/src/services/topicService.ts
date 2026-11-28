import { apiClient } from '../lib/apiClient'
import type {
  DocumentTopicsResponse,
  DocumentTopicsUpdate,
  TopicRankingResponse,
} from '../types/api'

function subjectPath(subjectId: string): string {
  return `/subjects/${encodeURIComponent(subjectId)}`
}

function documentTopicsPath(subjectId: string, documentId: string): string {
  return `${subjectPath(subjectId)}/documents/${encodeURIComponent(documentId)}/topics`
}

export const topicService = {
  /** One request for the window the API chooses: the route takes no parameter. */
  async ranking(subjectId: string): Promise<TopicRankingResponse> {
    const { data } = await apiClient.get<TopicRankingResponse>(
      `${subjectPath(subjectId)}/activity/topics`,
    )
    return data
  },

  async get(subjectId: string, documentId: string): Promise<DocumentTopicsResponse> {
    const { data } = await apiClient.get<DocumentTopicsResponse>(
      documentTopicsPath(subjectId, documentId),
    )
    return data
  },

  /** Replaces the whole set; `revision` is the one that was read. */
  async save(
    subjectId: string,
    documentId: string,
    body: DocumentTopicsUpdate,
  ): Promise<DocumentTopicsResponse> {
    const { data } = await apiClient.put<DocumentTopicsResponse>(
      documentTopicsPath(subjectId, documentId),
      body,
    )
    return data
  },
}
