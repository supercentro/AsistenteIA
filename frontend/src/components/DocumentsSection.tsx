import type { UseQueryResult } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useDeleteDocument } from '../hooks/useDeleteDocument'
import { useDocumentAnnouncement } from '../hooks/useDocumentAnnouncement'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { Document } from '../types/api'
import { Alert } from './Alert'
import { Button } from './Button'
import { DocumentRow } from './DocumentRow'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingState } from './LoadingState'

interface DocumentsSectionProps {
  userId: string
  subjectId: string
  documents: UseQueryResult<Document[], Error>
}

const text = strings.materials.documents

/** The documents of a subject with their status, the refresh control and the deletion. */
export function DocumentsSection({ userId, subjectId, documents }: DocumentsSectionProps) {
  const removal = useDeleteDocument(userId, subjectId)
  const announcement = useDocumentAnnouncement(documents.data)
  const [goneNotice, setGoneNotice] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)

  function onDelete(documentId: string) {
    if (removal.isPending) {
      return
    }
    setGoneNotice(false)
    removal.mutate(documentId, {
      onSuccess: (result) => {
        setGoneNotice(result === 'gone')
        // The row that held the focus is gone: keep the focus inside the section.
        headingRef.current?.focus()
      },
    })
  }

  const error = documents.error instanceof ApiError ? documents.error : null
  let content
  if (documents.isPending || error?.status === 401) {
    content = <LoadingState label={text.loading} />
  } else if (documents.data === undefined) {
    content = (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void documents.refetch()}
      />
    )
  } else if (documents.data.length === 0) {
    content = <EmptyState message={text.empty} />
  } else {
    content = (
      <ul aria-label={text.listLabel} className="flex flex-col gap-3">
        {documents.data.map((item) => (
          <DocumentRow
            key={item.id}
            document={item}
            deleting={removal.isPending && removal.variables === item.id}
            deletionBusy={removal.isPending}
            deleteError={removal.isError && removal.variables === item.id ? removal.error : null}
            onDelete={onDelete}
          />
        ))}
      </ul>
    )
  }

  return (
    <section aria-labelledby="documents-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="documents-heading"
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
        >
          {text.heading}
        </h2>
        <Button
          variant="secondary"
          pending={documents.isFetching}
          onClick={() => void documents.refetch()}
        >
          {text.refresh}
        </Button>
      </div>
      {documents.isError && documents.data !== undefined ? (
        <Alert variant="error">{text.pollFailed}</Alert>
      ) : null}
      {goneNotice ? <Alert variant="info">{strings.materials.remove.gone}</Alert> : null}
      {content}
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </section>
  )
}
