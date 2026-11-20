import type { UseQueryResult } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useDeleteConversation } from '../hooks/useDeleteConversation'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { Conversation } from '../types/api'
import { Alert } from './Alert'
import { Button } from './Button'
import { ConfirmPanel } from './ConfirmPanel'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingState } from './LoadingState'

interface ConversationListProps {
  userId: string
  subjectId: string
  conversations: UseQueryResult<Conversation[], Error>
  selectedId: string | null
  onSelect: (conversationId: string | null) => void
  /** A question is pending: the open conversation must not change until its answer arrives. */
  locked: boolean
}

const text = strings.chat.conversations

/** The student's conversations of this subject: open one, start a new one, delete one. */
export function ConversationList({
  userId,
  subjectId,
  conversations,
  selectedId,
  onSelect,
  locked,
}: ConversationListProps) {
  const removal = useDeleteConversation(userId, subjectId)
  const [goneNotice, setGoneNotice] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)

  function onRemove(conversationId: string) {
    if (removal.isPending) {
      return
    }
    setGoneNotice(false)
    removal.mutate(conversationId, {
      onSuccess: (result) => {
        setGoneNotice(result === 'gone')
        if (selectedId === conversationId) {
          onSelect(null)
        }
        headingRef.current?.focus()
      },
    })
  }

  const error = conversations.error instanceof ApiError ? conversations.error : null
  let content
  if (conversations.isPending || error?.status === 401) {
    content = <LoadingState label={text.loading} />
  } else if (conversations.data === undefined) {
    content = (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void conversations.refetch()}
      />
    )
  } else if (conversations.data.length === 0) {
    content = <EmptyState message={text.empty} />
  } else {
    content = (
      <ul aria-label={text.listLabel} className="flex flex-col gap-2">
        {conversations.data.map((item) => {
          const preview = item.last_message_preview || text.untitled(item.created_at)
          return (
            <li
              key={item.id}
              className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3"
            >
              <button
                type="button"
                aria-current={item.id === selectedId ? 'true' : undefined}
                disabled={locked}
                onClick={() => onSelect(item.id)}
                className="min-h-11 break-words text-left text-sm underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 aria-[current=true]:font-semibold"
              >
                {preview}
              </button>
              {removal.isError && removal.variables === item.id ? (
                <Alert variant="error">
                  {removal.error instanceof ApiError
                    ? messageFor(removal.error)
                    : strings.errors.unknown}
                </Alert>
              ) : null}
              <ConfirmPanel
                id={item.id}
                triggerLabel={text.remove.action(preview)}
                question={text.remove.question(preview)}
                body={text.remove.body}
                confirmLabel={text.remove.confirm}
                workingLabel={text.remove.working}
                cancelLabel={text.remove.cancel}
                pending={removal.isPending && removal.variables === item.id}
                busy={removal.isPending || locked}
                onConfirm={() => onRemove(item.id)}
              />
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <section aria-labelledby="conversations-heading" className="flex flex-col gap-3">
      <h2
        id="conversations-heading"
        ref={headingRef}
        tabIndex={-1}
        className="text-lg font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
      >
        {text.heading}
      </h2>
      <div>
        <Button variant="secondary" disabled={locked} onClick={() => onSelect(null)}>
          {text.new}
        </Button>
      </div>
      {goneNotice ? <Alert variant="info">{text.gone}</Alert> : null}
      {content}
    </section>
  )
}
