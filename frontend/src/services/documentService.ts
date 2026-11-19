import { apiClient } from '../lib/apiClient'
import type { Document } from '../types/api'

function documentsPath(subjectId: string): string {
  return `/subjects/${encodeURIComponent(subjectId)}/documents`
}

/** A 10 MB file on a slow connection needs more than the 15 s of an ordinary request. */
const UPLOAD_TIMEOUT_MS = 120_000

export const documentService = {
  async list(subjectId: string): Promise<Document[]> {
    const { data } = await apiClient.get<Document[]>(documentsPath(subjectId))
    return data
  },

  /** One file in the single multipart field `file`; the browser sets the boundary itself. */
  async upload(subjectId: string, file: File): Promise<Document> {
    const body = new FormData()
    body.append('file', file)
    const { data } = await apiClient.post<Document>(documentsPath(subjectId), body, {
      headers: { 'Content-Type': undefined },
      timeout: UPLOAD_TIMEOUT_MS,
    })
    return data
  },

  async remove(subjectId: string, documentId: string): Promise<void> {
    await apiClient.delete(`${documentsPath(subjectId)}/${encodeURIComponent(documentId)}`)
  },
}
