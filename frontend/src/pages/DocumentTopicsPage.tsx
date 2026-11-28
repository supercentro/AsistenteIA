import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { TopicEditor } from '../components/TopicEditor'
import { TopicsNotAvailable } from '../components/TopicsNotAvailable'
import { useFocusOnMount } from '../hooks/useFocusOnMount'
import { useSession } from '../hooks/useSession'
import { useDocumentTopics, useSaveDocumentTopics } from '../hooks/useTopics'
import { formatDay } from '../lib/activityFormat'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { DocumentTopicsResponse } from '../types/api'
import ForbiddenPage from './ForbiddenPage'

const text = strings.topics.editor

export default function DocumentTopicsPage() {
  const { subjectId = '', documentId = '' } = useParams()
  return <Content key={documentId} subjectId={subjectId} documentId={documentId} />
}

interface Ids {
  subjectId: string
  documentId: string
}

function Content({ subjectId, documentId }: Ids) {
  const { user } = useSession()
  const query = useDocumentTopics(user?.id ?? '', subjectId, documentId)
  const error = query.error instanceof ApiError ? query.error : null

  if (error?.status === 403) return <ForbiddenPage />
  if (error?.status === 404) return <TopicsNotAvailable />
  if (query.isPending || error?.status === 401) return <LoadingState label={text.loading} />
  if (query.data === undefined) {
    return (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void query.refetch()}
      />
    )
  }
  return (
    <Loaded
      subjectId={subjectId}
      documentId={documentId}
      data={query.data}
      reload={async () => {
        const result = await query.refetch()
        return failureText(result.error)
      }}
    />
  )
}

function failureText(error: Error | null): string | null {
  if (!(error instanceof ApiError)) return error ? strings.errors.unknown : null
  if (error.topicReason === 'stale') return text.errors.stale
  if (error.topicReason === 'overlap') return text.errors.overlap
  if (error.status === 422) return text.errors.invalid
  return messageFor(error)
}

interface LoadedProps extends Ids {
  data: DocumentTopicsResponse
  /** Reads the topics again; the text of the failure, or null when it worked. */
  reload: () => Promise<string | null>
}

function Loaded({ subjectId, documentId, data, reload }: LoadedProps) {
  const { user } = useSession()
  const heading = useFocusOnMount<HTMLHeadingElement>()
  const save = useSaveDocumentTopics(user?.id ?? '', subjectId, documentId)
  // A new generation rebuilds the rows from the stored set: after a save and after a reload only.
  const [generation, setGeneration] = useState(0)
  const [reloadFailure, setReloadFailure] = useState<string | null>(null)
  const stale = save.error instanceof ApiError && save.error.topicReason === 'stale'

  return (
    <div className="flex flex-col gap-5">
      <Link className="text-sm text-slate-900 underline" to={`/subjects/${subjectId}`}>
        {text.back}
      </Link>
      <header className="flex flex-col gap-1">
        <h1 ref={heading} tabIndex={-1} className="text-2xl font-bold">
          {text.title}
        </h1>
        <p className="break-words text-slate-600">
          <bdi>{data.filename}</bdi>
        </p>
        <Link
          className="text-sm text-slate-900 underline"
          to={`/subjects/${subjectId}/activity/topics`}
        >
          {strings.topics.link}
        </Link>
      </header>
      {data.source === 'bookmarks' ? (
        <p className="text-sm text-slate-600">{text.fromBookmarks}</p>
      ) : null}
      {data.counting_from ? (
        <p className="text-sm text-slate-600">{text.countingFrom(formatDay(data.counting_from))}</p>
      ) : null}
      <p role="status" className="text-sm font-medium text-slate-900">
        {save.isSuccess ? text.saved : ''}
      </p>
      {data.editable && data.last_page !== null ? (
        <TopicEditor
          key={generation}
          saved={data.topics}
          lastPage={data.last_page}
          savedBefore={data.revision > 0}
          saving={save.isPending}
          failure={failureText(save.error)}
          onSave={(topics) => {
            setReloadFailure(null)
            save.mutate(
              { revision: data.revision, topics },
              {
                // The rows are rebuilt, so the focus goes to the heading above the message.
                onSuccess: () => {
                  setGeneration((value) => value + 1)
                  heading.current?.focus()
                },
              },
            )
          }}
        />
      ) : (
        <p className="rounded-md border border-slate-300 bg-white p-4">
          {text.unavailable[data.reason ?? 'not_ready']}
        </p>
      )}
      {reloadFailure ? <Alert variant="error">{reloadFailure}</Alert> : null}
      {stale ? (
        <div>
          <Button
            variant="secondary"
            onClick={() => {
              setReloadFailure(null)
              void reload().then((message) => {
                // A failed reload changes nothing: the typed rows are all there is of them.
                if (message) {
                  setReloadFailure(message)
                  return
                }
                save.reset()
                setGeneration((value) => value + 1)
                // The reload button goes away with the refusal, so the focus needs a place.
                heading.current?.focus()
              })
            }}
          >
            {text.reload}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
