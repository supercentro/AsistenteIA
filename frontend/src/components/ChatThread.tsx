import { strings } from '../lib/strings.es'
import type { Message } from '../types/api'
import { MessageBubble } from './MessageBubble'

interface ChatThreadProps {
  messages: readonly Message[]
  /** The question sent and not answered yet. */
  pendingQuestion: string | null
}

const text = strings.chat

/** The messages of the open conversation; new ones are announced politely by the log role. */
export function ChatThread({ messages, pendingQuestion }: ChatThreadProps) {
  const empty = messages.length === 0 && pendingQuestion === null
  return (
    <div
      role="log"
      aria-label={text.thread.label}
      aria-relevant="additions"
      className="flex min-h-40 flex-col gap-3"
    >
      {empty ? <p className="text-slate-600">{text.thread.empty}</p> : null}
      {messages.map((message, index) => (
        <MessageBubble
          // Append-only list: an index key keeps the question in place when its local id is replaced.
          key={index}
          author={message.role}
          content={message.content}
          sources={message.sources}
          attribution={message.attribution}
        />
      ))}
      {pendingQuestion === null ? null : (
        <MessageBubble author="user" content={pendingQuestion} pending />
      )}
    </div>
  )
}
