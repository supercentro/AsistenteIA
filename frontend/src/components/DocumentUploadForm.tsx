import { useId, useRef, useState, type FormEvent } from 'react'
import { useUploadDocument } from '../hooks/useUploadDocument'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import { Alert } from './Alert'
import { Button } from './Button'

interface DocumentUploadFormProps {
  userId: string
  subjectId: string
  /** The API answered 403 or 404: the subject is not available to this account any more. */
  onSubjectUnavailable: (status: 403 | 404) => void
}

const text = strings.materials.upload

function uploadMessage(error: Error): string {
  if (!(error instanceof ApiError)) {
    return strings.errors.unknown
  }
  if (error.kind === 'timeout') {
    return text.timeout
  }
  if (error.status === 422 && error.reason) {
    return text.reasons[error.reason]
  }
  return messageFor(error)
}

/** One file at a time. The API decides the type and the size; the form only needs a file. */
export function DocumentUploadForm({
  userId,
  subjectId,
  onSubjectUnavailable,
}: DocumentUploadFormProps) {
  const upload = useUploadDocument(userId, subjectId)
  const inputRef = useRef<HTMLInputElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)
  const [missingFile, setMissingFile] = useState(false)
  const inputId = useId()
  const noticeId = `${inputId}-notice`
  const errorId = `${inputId}-error`

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (upload.isPending) {
      return
    }
    const file = inputRef.current?.files?.[0]
    if (!file) {
      setMissingFile(true)
      inputRef.current?.focus()
      return
    }
    setMissingFile(false)
    upload.mutate(file, {
      onSettled: () => submitRef.current?.focus(),
      onSuccess: () => {
        if (inputRef.current) {
          inputRef.current.value = ''
        }
      },
      onError: (failure) => {
        if (failure instanceof ApiError && (failure.status === 403 || failure.status === 404)) {
          onSubjectUnavailable(failure.status)
        }
      },
    })
  }

  const error = upload.error
  // 401 ends the session; 403 and 404 replace the whole page, so no message is needed for them.
  const showError =
    error !== null && !(error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0))

  return (
    <section aria-labelledby={`${inputId}-heading`} className="flex flex-col gap-3">
      <h2 id={`${inputId}-heading`} className="text-lg font-semibold">
        {text.heading}
      </h2>
      <p id={noticeId} className="text-sm text-slate-700">
        {text.notice}
      </p>
      {showError ? <Alert variant="error">{uploadMessage(error)}</Alert> : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor={inputId} className="text-sm font-medium text-slate-800">
            {text.fileLabel}
          </label>
          <input
            id={inputId}
            ref={inputRef}
            type="file"
            accept=".pdf,.txt,.md"
            disabled={upload.isPending}
            aria-describedby={[noticeId, missingFile ? errorId : null].filter(Boolean).join(' ')}
            aria-invalid={missingFile ? true : undefined}
            className="block w-full text-sm file:mr-3 file:min-h-11 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-4 file:py-2"
          />
          {missingFile ? (
            <p id={errorId} role="alert" className="text-xs text-red-700">
              {text.noFile}
            </p>
          ) : null}
        </div>
        <div>
          <Button ref={submitRef} type="submit" pending={upload.isPending}>
            {upload.isPending ? text.submitting : text.submit}
          </Button>
        </div>
      </form>
    </section>
  )
}
