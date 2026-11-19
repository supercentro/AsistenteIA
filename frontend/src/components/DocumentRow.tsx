import { useEffect, useRef, useState } from 'react'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { Document } from '../types/api'
import { Alert } from './Alert'
import { Button } from './Button'

interface DocumentRowProps {
  document: Document
  /** A deletion of this very document is in flight. */
  deleting: boolean
  /** Some deletion is in flight: no other confirm control may be used meanwhile. */
  deletionBusy: boolean
  deleteError: Error | null
  onDelete: (documentId: string) => void
}

const text = strings.materials

function failureSentence(code: string | null | undefined): string {
  const known = text.failures as Record<string, string>
  return (code && known[code]) || text.failures.generic
}

/** One document: name, type, size, chunks, status in words, and the inline deletion confirmation. */
export function DocumentRow({
  document: item,
  deleting,
  deletionBusy,
  deleteError,
  onDelete,
}: DocumentRowProps) {
  const [confirming, setConfirming] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  useEffect(() => {
    if (confirming) {
      panelRef.current?.focus()
    } else if (returnFocus.current) {
      returnFocus.current = false
      triggerRef.current?.focus()
    }
  }, [confirming])

  function cancel() {
    returnFocus.current = true
    setConfirming(false)
  }

  const question = text.remove.confirmQuestion(item.filename)
  const questionId = `confirm-${item.id}`

  return (
    <li className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 break-words font-medium">
          <bdi>{item.filename}</bdi>
        </p>
        <p className="text-sm font-semibold">{text.status[item.status]}</p>
      </div>
      <p className="flex flex-wrap gap-x-3 text-sm text-slate-600">
        <span>{text.documents.types[item.content_type] ?? text.documents.otherType}</span>
        <span>{text.documents.size(item.size_bytes)}</span>
        <span>{text.documents.chunks(item.chunks_count)}</span>
      </p>
      {item.status === 'failed' ? (
        <p className="break-words text-sm text-red-800">{failureSentence(item.error_code)}</p>
      ) : null}
      {deleteError ? (
        <Alert variant="error">
          {deleteError instanceof ApiError ? messageFor(deleteError) : strings.errors.unknown}
        </Alert>
      ) : null}
      {confirming ? (
        <div
          ref={panelRef}
          role="group"
          aria-labelledby={questionId}
          tabIndex={-1}
          className="flex flex-col gap-2 rounded-md border border-red-300 bg-red-50 p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
        >
          <p
            id={questionId}
            className="break-words font-medium text-red-900 [unicode-bidi:isolate]"
          >
            {question}
          </p>
          <p className="text-sm text-red-900">{text.remove.confirmBody}</p>
          <div className="flex flex-wrap gap-2">
            <Button pending={deleting} disabled={deletionBusy} onClick={() => onDelete(item.id)}>
              {deleting ? text.remove.working : text.remove.confirm}
            </Button>
            <Button variant="secondary" disabled={deleting} onClick={cancel}>
              {text.remove.cancel}
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button ref={triggerRef} variant="secondary" onClick={() => setConfirming(true)}>
            {text.remove.action(item.filename)}
          </Button>
        </div>
      )}
    </li>
  )
}
