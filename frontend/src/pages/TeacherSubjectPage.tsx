import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DocumentUploadForm } from '../components/DocumentUploadForm'
import { DocumentsSection } from '../components/DocumentsSection'
import { EnrollmentsSection } from '../components/EnrollmentsSection'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { useDocuments } from '../hooks/useDocuments'
import { useEnrollments } from '../hooks/useEnrollments'
import { useSession } from '../hooks/useSession'
import { useSubject } from '../hooks/useSubject'
import { ApiError, messageFor } from '../lib/apiError'
import { teacherActivityEnabled } from '../lib/features'
import { strings } from '../lib/strings.es'
import ForbiddenPage from './ForbiddenPage'

const text = strings.materials

function BackLink() {
  return (
    <Link className="text-sm text-slate-900 underline" to="/subjects">
      {text.back}
    </Link>
  )
}

/** The subject does not exist for this account: the same view whether it exists or not. */
function SubjectNotFound() {
  return (
    <section className="flex flex-col items-start gap-3">
      <h1 className="text-2xl font-bold">{text.notFound.title}</h1>
      <p className="text-slate-600">{text.notFound.body}</p>
      <BackLink />
    </section>
  )
}

/** One page per subject: the key drops the state of the previous subject when the route changes. */
export default function TeacherSubjectPage() {
  const { subjectId = '' } = useParams()
  return <SubjectContent key={subjectId} subjectId={subjectId} />
}

/** A teacher's page for one subject: its upload form, its documents and its enrolled students. */
function SubjectContent({ subjectId }: { subjectId: string }) {
  const { user } = useSession()
  const userId = user?.id ?? ''
  const subject = useSubject(userId, subjectId)
  const documents = useDocuments(userId, subjectId)
  const enrollments = useEnrollments(userId, subjectId)
  const [unavailable, setUnavailable] = useState<403 | 404 | null>(null)

  const statuses = [subject.error, documents.error, enrollments.error]
    .filter((error): error is ApiError => error instanceof ApiError)
    .map((error) => error.status)
  if (unavailable === 403 || statuses.includes(403)) {
    return <ForbiddenPage />
  }
  if (unavailable === 404 || statuses.includes(404) || statuses.includes(422)) {
    return <SubjectNotFound />
  }

  const subjectError = subject.error instanceof ApiError ? subject.error : null
  if (subject.isPending || subjectError?.status === 401) {
    return <LoadingState label={text.loading} />
  }
  if (subject.data === undefined) {
    return (
      <ErrorState
        message={subjectError ? messageFor(subjectError) : strings.errors.unknown}
        onRetry={() => void subject.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <BackLink />
      <header className="flex flex-col gap-1">
        <h1 className="break-words text-2xl font-bold">{subject.data.name}</h1>
        {subject.data.description ? (
          <p className="whitespace-pre-line break-words text-slate-600">
            {subject.data.description}
          </p>
        ) : null}
        {teacherActivityEnabled() ? (
          <Link className="text-sm text-slate-900 underline" to={`/subjects/${subjectId}/activity`}>
            {strings.activity.link}
          </Link>
        ) : null}
      </header>
      <DocumentUploadForm
        userId={userId}
        subjectId={subjectId}
        onSubjectUnavailable={setUnavailable}
      />
      <DocumentsSection userId={userId} subjectId={subjectId} documents={documents} />
      <EnrollmentsSection
        userId={userId}
        subjectId={subjectId}
        enrollments={enrollments}
        onSubjectUnavailable={() => setUnavailable(403)}
      />
    </div>
  )
}
