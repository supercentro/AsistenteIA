import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { topicService } from '../services/topicService'
import type {
  DocumentTopicsResponse,
  DocumentTopicsUpdate,
  TopicRankingResponse,
} from '../types/api'

/** Read once per visit and never kept, like the activity: no earlier response to compare with. */
const ONCE_PER_VISIT = {
  retry: false,
  staleTime: Infinity,
  gcTime: 0,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
  refetchInterval: false,
} as const

export function useTopicRanking(userId: string, subjectId: string) {
  return useQuery<TopicRankingResponse>({
    queryKey: ['topic-ranking', userId, subjectId],
    queryFn: () => topicService.ranking(subjectId),
    ...ONCE_PER_VISIT,
  })
}

function documentTopicsKey(userId: string, subjectId: string, documentId: string) {
  return ['document-topics', userId, subjectId, documentId]
}

export function useDocumentTopics(userId: string, subjectId: string, documentId: string) {
  return useQuery<DocumentTopicsResponse>({
    queryKey: documentTopicsKey(userId, subjectId, documentId),
    queryFn: () => topicService.get(subjectId, documentId),
    ...ONCE_PER_VISIT,
  })
}

export function useSaveDocumentTopics(userId: string, subjectId: string, documentId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: DocumentTopicsUpdate) => topicService.save(subjectId, documentId, body),
    onSuccess: (data) => {
      client.setQueryData(documentTopicsKey(userId, subjectId, documentId), data)
    },
  })
}
