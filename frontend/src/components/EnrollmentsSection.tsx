import type { UseQueryResult } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useRemoveEnrollment } from '../hooks/useRemoveEnrollment'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { Enrollment } from '../types/api'
import { Alert } from './Alert'
import { ConfirmPanel } from './ConfirmPanel'
import { EmptyState } from './EmptyState'
import { EnrollStudentForm } from './EnrollStudentForm'
import { ErrorState } from './ErrorState'
import { LoadingState } from './LoadingState'

interface EnrollmentsSectionProps {
  userId: string
  subjectId: string
  enrollments: UseQueryResult<Enrollment[], Error>
  onSubjectUnavailable: () => void
}

const text = strings.enrollments

/** The students enrolled in a subject, the form to enroll one and the removal of an enrollment. */
export function EnrollmentsSection({
  userId,
  subjectId,
  enrollments,
  onSubjectUnavailable,
}: EnrollmentsSectionProps) {
  const removal = useRemoveEnrollment(userId, subjectId)
  const [goneNotice, setGoneNotice] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)

  function onRemove(studentId: string) {
    if (removal.isPending) {
      return
    }
    setGoneNotice(false)
    removal.mutate(studentId, {
      onSuccess: (result) => {
        setGoneNotice(result === 'gone')
        // The row that held the focus is gone: keep the focus inside the section.
        headingRef.current?.focus()
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 403) {
          onSubjectUnavailable()
        }
      },
    })
  }

  const error = enrollments.error instanceof ApiError ? enrollments.error : null
  let content
  if (enrollments.isPending || error?.status === 401) {
    content = <LoadingState label={text.loading} />
  } else if (enrollments.data === undefined) {
    content = (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void enrollments.refetch()}
      />
    )
  } else if (enrollments.data.length === 0) {
    content = <EmptyState message={text.empty} />
  } else {
    content = (
      <ul aria-label={text.listLabel} className="flex flex-col gap-3">
        {enrollments.data.map((item) => (
          <li
            key={item.id}
            className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4"
          >
            <p className="break-words font-medium">
              <bdi>{item.student_email}</bdi>
            </p>
            {removal.isError && removal.variables === item.student_id ? (
              <Alert variant="error">
                {removal.error instanceof ApiError
                  ? messageFor(removal.error)
                  : strings.errors.unknown}
              </Alert>
            ) : null}
            <ConfirmPanel
              id={item.id}
              triggerLabel={text.remove.action(item.student_email)}
              question={text.remove.question(item.student_email)}
              body={text.remove.body}
              confirmLabel={text.remove.confirm}
              workingLabel={text.remove.working}
              cancelLabel={text.remove.cancel}
              pending={removal.isPending && removal.variables === item.student_id}
              busy={removal.isPending}
              onConfirm={() => onRemove(item.student_id)}
            />
          </li>
        ))}
      </ul>
    )
  }

  return (
    <section aria-labelledby="enrollments-heading" className="flex flex-col gap-3">
      <h2
        id="enrollments-heading"
        ref={headingRef}
        tabIndex={-1}
        className="text-lg font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
      >
        {text.heading}
      </h2>
      <EnrollStudentForm
        userId={userId}
        subjectId={subjectId}
        onSubjectUnavailable={onSubjectUnavailable}
        onEnrolled={() => setGoneNotice(false)}
      />
      {enrollments.isError && enrollments.data !== undefined ? (
        <Alert variant="error">{messageFor(enrollments.error as ApiError)}</Alert>
      ) : null}
      {goneNotice ? <Alert variant="info">{text.remove.gone}</Alert> : null}
      {content}
    </section>
  )
}
