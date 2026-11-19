import { useQuery } from '@tanstack/react-query'
import { documentService } from '../services/documentService'
import type { Document } from '../types/api'

/** How often the list is refreshed while a document is still being processed. */
export const DOCUMENTS_POLL_MS = 3000

/** Poll only while some document is not final; stop as soon as every one is `ready` or `failed`. */
export function documentsRefetchInterval(documents: Document[] | undefined): number | false {
  const inProgress = documents?.some(
    (item) => item.status === 'pending' || item.status === 'processing',
  )
  return inProgress ? DOCUMENTS_POLL_MS : false
}

/** The cache key includes the user id and the subject id. Background tabs do not poll. */
export function useDocuments(userId: string, subjectId: string) {
  return useQuery<Document[]>({
    queryKey: ['documents', userId, subjectId],
    queryFn: () => documentService.list(subjectId),
    refetchInterval: (query) => documentsRefetchInterval(query.state.data),
  })
}
