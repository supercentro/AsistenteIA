import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useCreateSubject } from '../hooks/useCreateSubject'
import { ApiError, messageFor } from '../lib/apiError'
import { subjectSchema, type SubjectValues } from '../lib/schemas'
import { strings } from '../lib/strings.es'
import { Alert } from './Alert'
import { Button } from './Button'
import { FormField } from './FormField'
import { TextAreaField } from './TextAreaField'

interface CreateSubjectFormProps {
  userId: string
}

const text = strings.subjects.create

/** Teacher-only form on the subject list; the API stays the authority on every limit. */
export function CreateSubjectForm({ userId }: CreateSubjectFormProps) {
  const creation = useCreateSubject(userId)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SubjectValues>({
    resolver: zodResolver(subjectSchema),
    defaultValues: { name: '', description: '' },
  })

  const onSubmit = handleSubmit((values) => {
    if (creation.isPending) {
      return
    }
    // A blank description is not sent: the API stores it as null anyway.
    const payload = values.description
      ? { name: values.name, description: values.description }
      : { name: values.name }
    creation.mutate(payload, { onSuccess: () => reset() })
  })

  const error = creation.error
  // A 401 ends the session and the router leaves the page: never flash an error for it.
  const showError = error !== null && !(error instanceof ApiError && error.status === 401)

  return (
    <section aria-labelledby="create-subject-heading" className="flex flex-col gap-3">
      <h2 id="create-subject-heading" className="text-lg font-semibold">
        {text.heading}
      </h2>
      {showError ? (
        <Alert variant="error">
          {error instanceof ApiError
            ? messageFor(error, { CONFLICT: text.nameTaken })
            : strings.errors.unknown}
        </Alert>
      ) : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
        <FormField label={text.name} error={errors.name?.message} {...register('name')} />
        <TextAreaField
          label={text.description}
          error={errors.description?.message}
          {...register('description')}
        />
        <div>
          <Button type="submit" pending={creation.isPending}>
            {creation.isPending ? text.submitting : text.submit}
          </Button>
        </div>
      </form>
    </section>
  )
}
