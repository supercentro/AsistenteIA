import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useEnrollStudent } from '../hooks/useEnrollStudent'
import { ApiError, messageFor } from '../lib/apiError'
import { enrollmentSchema, type EnrollmentValues } from '../lib/schemas'
import { strings } from '../lib/strings.es'
import { Alert } from './Alert'
import { Button } from './Button'
import { FormField } from './FormField'

interface EnrollStudentFormProps {
  userId: string
  subjectId: string
  /** The API answered 403: the subject is not available to this account. */
  onSubjectUnavailable: () => void
  /** A student was enrolled: the caller may clear stale notices. */
  onEnrolled?: () => void
}

const text = strings.enrollments

function enrollMessage(error: Error): string {
  if (!(error instanceof ApiError)) {
    return strings.errors.unknown
  }
  if (error.status === 404) {
    return text.errors.notFound
  }
  return messageFor(error, { CONFLICT: text.errors.alreadyEnrolled })
}

/** One e-mail; the account must exist. The submitted value is never shown back by an error. */
export function EnrollStudentForm({
  userId,
  subjectId,
  onSubjectUnavailable,
  onEnrolled,
}: EnrollStudentFormProps) {
  const enrollment = useEnrollStudent(userId, subjectId)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EnrollmentValues>({
    resolver: zodResolver(enrollmentSchema),
    defaultValues: { studentEmail: '' },
  })

  const onSubmit = handleSubmit((values) => {
    if (enrollment.isPending) {
      return
    }
    enrollment.mutate(values.studentEmail, {
      onSuccess: () => {
        reset()
        onEnrolled?.()
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 403) {
          onSubjectUnavailable()
        }
      },
    })
  })

  const error = enrollment.error
  // 401 ends the session and 403 replaces the page: no message is needed for them.
  const showError =
    error !== null && !(error instanceof ApiError && [401, 403].includes(error.status ?? 0))

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      {showError ? <Alert variant="error">{enrollMessage(error)}</Alert> : null}
      <FormField
        label={text.form.field}
        type="email"
        autoComplete="off"
        hint={text.form.hint}
        error={errors.studentEmail?.message}
        {...register('studentEmail', { onChange: () => enrollment.reset() })}
      />
      <div>
        <Button type="submit" pending={enrollment.isPending}>
          {enrollment.isPending ? text.form.submitting : text.form.submit}
        </Button>
      </div>
    </form>
  )
}
