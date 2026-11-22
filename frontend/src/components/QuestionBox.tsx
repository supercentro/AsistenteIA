import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import type { UseMutationResult } from '@tanstack/react-query'
import type { AskVariables } from '../hooks/useAskQuestion'
import { ApiError, messageFor } from '../lib/apiError'
import { questionSchema, type QuestionValues } from '../lib/schemas'
import { strings } from '../lib/strings.es'
import type { ChatResponse } from '../types/api'
import { Alert } from './Alert'
import { Button } from './Button'
import { TextAreaField } from './TextAreaField'

interface QuestionBoxProps {
  conversationId: string | null
  ask: UseMutationResult<ChatResponse, Error, AskVariables>
  /** The answer arrived: the caller opens that conversation. */
  onAnswered: (conversationId: string) => void
  /** The API answered 403 or 404: the subject is not available to this account. */
  onUnavailable: () => void
  /** The API answered 404 to a question of an open conversation: the conversation is gone. */
  onConversationGone: () => void
}

const text = strings.chat

/**
 * The focus may go back to the question box only when the student has not moved it elsewhere: it is
 * on the form, or it fell to the page body (a send button that becomes disabled drops it there). A
 * control the student chose, such as an open delete confirmation, keeps it.
 */
function focusIsFree(form: HTMLFormElement | null): boolean {
  const active = document.activeElement
  return active === null || active === document.body || (form !== null && form.contains(active))
}

function chatErrorMessage(error: Error): string {
  if (!(error instanceof ApiError)) {
    return strings.errors.unknown
  }
  if (error.kind === 'timeout') {
    return text.errors.timeout
  }
  const message = messageFor(error)
  return error.status === 429 ? `${message} ${text.errors.sharedLimit}` : message
}

/** The question box: the question stays in it on any failure so it can be sent again as it is. */
export function QuestionBox({
  conversationId,
  ask,
  onAnswered,
  onUnavailable,
  onConversationGone,
}: QuestionBoxProps) {
  const {
    register,
    handleSubmit,
    resetField,
    setFocus,
    control,
    formState: { errors },
  } = useForm<QuestionValues>({
    resolver: zodResolver(questionSchema),
    defaultValues: { message: '' },
  })

  const onSubmit = handleSubmit((values, event) => {
    if (ask.isPending) {
      return
    }
    // The form that was submitted: the focus rule below asks whether the focus is still inside it.
    const form = event?.target instanceof HTMLFormElement ? event.target : null
    ask.mutate(
      { conversationId, message: values.message },
      {
        onSuccess: (response) => {
          // resetField keeps the field registered, so the focus can go back to it at once.
          resetField('message')
          onAnswered(response.conversation_id)
          if (focusIsFree(form)) {
            setFocus('message')
          }
        },
        onError: (error) => {
          if (!(error instanceof ApiError) || error.code === 'CONSENT_REQUIRED') {
            return
          }
          if (error.status === 404 && conversationId) {
            onConversationGone()
          } else if (error.status === 403 || error.status === 404) {
            onUnavailable()
          }
        },
      },
    )
  })

  const error = ask.error
  // 401 ends the session; CONSENT_REQUIRED sends the student to the consent screen; 403 and 404
  // replace the page. None of them needs a message here.
  const showError =
    error !== null && !(error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0))
  const length = useWatch({ control, name: 'message' })?.length ?? 0

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-2">
      {showError ? <Alert variant="error">{chatErrorMessage(error)}</Alert> : null}
      {ask.isPending ? (
        <p role="status" className="text-sm text-slate-700">
          {text.answering}
        </p>
      ) : null}
      <TextAreaField
        label={text.box.label}
        error={errors.message?.message}
        readOnly={ask.isPending}
        aria-busy={ask.isPending}
        {...register('message')}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-slate-600">{text.box.counter(length)}</span>
        <Button type="submit" pending={ask.isPending}>
          {ask.isPending ? text.box.sending : text.box.send}
        </Button>
      </div>
    </form>
  )
}
