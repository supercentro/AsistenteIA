import { Link } from 'react-router-dom'
import { CreateSubjectForm } from '../components/CreateSubjectForm'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { HistorySection } from '../components/HistorySection'
import { LoadingState } from '../components/LoadingState'
import { useSession } from '../hooks/useSession'
import { useSubjects } from '../hooks/useSubjects'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'

/**
 * The subjects the API returns to the signed-in user. A teacher also gets the create form and a
 * link to the page of each subject; a student gets a link to the chat of each subject and the
 * action to delete the whole history.
 */
export default function SubjectsPage() {
  const { user } = useSession()
  const userId = user?.id ?? ''
  const isTeacher = user?.role === 'teacher'
  const subjects = useSubjects(userId)

  const error = subjects.error instanceof ApiError ? subjects.error : null
  // A 401 ends the session and the router leaves this page: never flash an error for it.
  const sessionEnding = error?.status === 401

  let content
  if (subjects.isPending || sessionEnding) {
    content = <LoadingState label={strings.subjects.loading} />
  } else if (subjects.isError) {
    content = (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void subjects.refetch()}
      />
    )
  } else if (subjects.data.length === 0) {
    content = (
      <EmptyState
        message={isTeacher ? strings.subjects.emptyTeacher : strings.subjects.emptyStudent}
      />
    )
  } else {
    content = (
      <ul aria-label={strings.subjects.listLabel} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {subjects.data.map((subject) => (
          <li key={subject.id} className="rounded-md border border-slate-200 bg-white p-4">
            <h2 className="break-words text-lg font-semibold">
              {isTeacher ? (
                <Link className="underline" to={`/subjects/${subject.id}`}>
                  {subject.name}
                </Link>
              ) : (
                subject.name
              )}
            </h2>
            {subject.description ? (
              <p className="mt-1 whitespace-pre-line break-words text-sm text-slate-600">
                {subject.description}
              </p>
            ) : null}
            {isTeacher ? null : (
              <p className="mt-2">
                <Link
                  className="break-words text-sm underline [overflow-wrap:anywhere]"
                  to={`/subjects/${subject.id}/chat`}
                >
                  {strings.chat.openChat(subject.name)}
                </Link>
              </p>
            )}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold">
        {isTeacher ? strings.subjects.titleTeacher : strings.subjects.titleStudent}
      </h1>
      {isTeacher ? <CreateSubjectForm userId={userId} /> : null}
      {content}
      {isTeacher ? null : <HistorySection userId={userId} />}
    </div>
  )
}
