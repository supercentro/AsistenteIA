import { useState } from 'react'
import { useDeleteHistory } from '../hooks/useDeleteHistory'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import { Alert } from './Alert'
import { ConfirmPanel } from './ConfirmPanel'

interface HistorySectionProps {
  userId: string
}

const text = strings.chat.history

/** The right of erasure over conversations: every subject, permanent, the account stays. */
export function HistorySection({ userId }: HistorySectionProps) {
  const deletion = useDeleteHistory(userId)
  const [done, setDone] = useState(false)

  function onConfirm() {
    if (deletion.isPending) {
      return
    }
    setDone(false)
    deletion.mutate(undefined, { onSuccess: () => setDone(true) })
  }

  const error = deletion.error
  // A 401 ends the session and the router leaves the page: never flash an error for it.
  const showError = error !== null && !(error instanceof ApiError && error.status === 401)

  return (
    <section aria-labelledby="history-heading" className="flex flex-col gap-3">
      <h2 id="history-heading" className="text-lg font-semibold">
        {text.heading}
      </h2>
      {showError ? (
        <Alert variant="error">
          {error instanceof ApiError ? messageFor(error) : strings.errors.unknown}
        </Alert>
      ) : null}
      {done ? <Alert variant="success">{text.done}</Alert> : null}
      <ConfirmPanel
        id="history"
        triggerLabel={text.action}
        question={text.question}
        body={text.body}
        confirmLabel={text.confirm}
        workingLabel={text.working}
        cancelLabel={text.cancel}
        pending={deletion.isPending}
        busy={deletion.isPending}
        onConfirm={onConfirm}
      />
    </section>
  )
}
