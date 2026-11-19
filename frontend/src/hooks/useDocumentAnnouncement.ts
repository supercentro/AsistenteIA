import { useState } from 'react'
import { strings } from '../lib/strings.es'
import type { Document } from '../types/api'

interface Tracked {
  documents: Document[] | undefined
  message: string
}

function announcementFor(before: Document[], after: Document[]): string {
  const previous = new Map(before.map((item) => [item.id, item.status]))
  const messages: string[] = []
  for (const item of after) {
    const was = previous.get(item.id)
    const wasInProgress = was === 'pending' || was === 'processing'
    if (wasInProgress && item.status === 'ready') {
      messages.push(strings.materials.announce.ready(item.filename))
    } else if (wasInProgress && item.status === 'failed') {
      messages.push(strings.materials.announce.failed(item.filename))
    }
  }
  return messages.join(' ')
}

/**
 * Text for a polite live region: set when a document that was pending or processing becomes
 * `ready` or `failed`. Documents already final on the first load are not announced.
 */
export function useDocumentAnnouncement(documents: Document[] | undefined): string {
  const [tracked, setTracked] = useState<Tracked>({ documents: undefined, message: '' })

  if (documents !== tracked.documents) {
    const message =
      tracked.documents && documents
        ? announcementFor(tracked.documents, documents) || tracked.message
        : tracked.message
    setTracked({ documents, message })
  }

  return tracked.message
}
