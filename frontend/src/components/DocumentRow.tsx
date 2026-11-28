import { Link } from 'react-router-dom'
import { ApiError, messageFor } from '../lib/apiError'
import { teacherTopicsEnabled } from '../lib/features'
import { strings } from '../lib/strings.es'
import type { Document } from '../types/api'
import { Alert } from './Alert'
import { ConfirmPanel } from './ConfirmPanel'

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
      {teacherTopicsEnabled() &&
      item.status === 'ready' &&
      item.content_type === 'application/pdf' ? (
        <Link
          className="text-sm text-slate-900 underline [overflow-wrap:anywhere]"
          to={`/subjects/${item.subject_id}/documents/${item.id}/topics`}
        >
          {strings.topics.documentLink(item.filename)}
        </Link>
      ) : null}
      {deleteError ? (
        <Alert variant="error">
          {deleteError instanceof ApiError ? messageFor(deleteError) : strings.errors.unknown}
        </Alert>
      ) : null}
      <ConfirmPanel
        id={item.id}
        triggerLabel={text.remove.action(item.filename)}
        question={text.remove.confirmQuestion(item.filename)}
        body={text.remove.confirmBody}
        confirmLabel={text.remove.confirm}
        workingLabel={text.remove.working}
        cancelLabel={text.remove.cancel}
        pending={deleting}
        busy={deletionBusy}
        onConfirm={() => onDelete(item.id)}
      />
    </li>
  )
}
