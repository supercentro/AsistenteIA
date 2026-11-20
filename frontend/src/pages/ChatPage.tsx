import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChatThread } from '../components/ChatThread'
import { ChatUnavailable } from '../components/ChatUnavailable'
import { ConversationList } from '../components/ConversationList'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { QuestionBox } from '../components/QuestionBox'
import { useAskQuestion } from '../hooks/useAskQuestion'
import { useConversations } from '../hooks/useConversations'
import { useMessages } from '../hooks/useMessages'
import { useSession } from '../hooks/useSession'
import { useSubject } from '../hooks/useSubject'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'

const text = strings.chat

/** One page per subject: the key drops the state of the previous subject when the route changes. */
export default function ChatPage() {
  const { subjectId = '' } = useParams()
  return <ChatContent key={subjectId} subjectId={subjectId} />
}

function ChatContent({ subjectId }: { subjectId: string }) {
  const { user } = useSession()
  const userId = user?.id ?? ''
  const subject = useSubject(userId, subjectId)
  const conversations = useConversations(userId, subjectId)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const messages = useMessages(userId, selectedId)
  const ask = useAskQuestion(userId, subjectId)
  const [unavailable, setUnavailable] = useState(false)
  const [conversationGone, setConversationGone] = useState(false)
  const queryClient = useQueryClient()
  const messagesGone =
    messages.error instanceof ApiError &&
    (messages.error.status === 404 || messages.error.status === 403)
  const threadGone = messagesGone || conversationGone
  useEffect(() => {
    if (threadGone) {
      void queryClient.invalidateQueries({ queryKey: ['conversations', userId, subjectId] })
    }
  }, [threadGone, queryClient, userId, subjectId, selectedId])

  const statuses = [subject.error, conversations.error]
    .filter((error): error is ApiError => error instanceof ApiError)
    .map((error) => error.status)
  if (unavailable || statuses.includes(403) || statuses.includes(404) || statuses.includes(422)) {
    return <ChatUnavailable />
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

  const pendingQuestion = ask.isPending && ask.variables ? ask.variables.message : null

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm text-slate-900 underline" to="/subjects">
        {text.back}
      </Link>
      <h1 className="break-words text-2xl font-bold">{subject.data.name}</h1>
      <p className="text-sm text-slate-700">{text.notice}</p>
      <p>
        <Link
          className="text-sm text-slate-900 underline"
          to="/privacy"
          target="_blank"
          rel="noopener noreferrer"
        >
          {text.policyLink}
        </Link>
      </p>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[18rem_1fr]">
        <ConversationList
          userId={userId}
          subjectId={subjectId}
          conversations={conversations}
          selectedId={selectedId}
          onSelect={(conversationId) => {
            setConversationGone(false)
            setSelectedId(conversationId)
          }}
          locked={ask.isPending}
        />
        <div className="flex min-w-0 flex-col gap-4">
          {threadGone ? (
            <p role="alert" className="text-slate-700">
              {text.conversations.messagesUnavailable}
            </p>
          ) : (
            <ChatThread messages={messages.data ?? []} pendingQuestion={pendingQuestion} />
          )}
          <QuestionBox
            conversationId={threadGone ? null : selectedId}
            ask={ask}
            onAnswered={(conversationId) => {
              setConversationGone(false)
              setSelectedId(conversationId)
            }}
            onUnavailable={() => setUnavailable(true)}
            onConversationGone={() => {
              setConversationGone(true)
              setSelectedId(null)
            }}
          />
        </div>
      </div>
    </div>
  )
}
