import { strings } from '../lib/strings.es'
import type { Message } from '../types/api'
import { SourcesBlock } from './SourcesBlock'

interface MessageBubbleProps {
  author: Message['role']
  content: string
  sources?: readonly Message['sources'][number][]
  /** The question is on its way: it is shown as sent but not saved yet. */
  pending?: boolean
}

const text = strings.chat.thread

/** One message of the thread. Questions and answers are plain text, never markup. */
export function MessageBubble({
  author,
  content,
  sources = [],
  pending = false,
}: MessageBubbleProps) {
  const mine = author === 'user'
  return (
    <div
      className={`flex flex-col gap-1 rounded-md p-3 ${mine ? 'bg-slate-100' : 'border border-slate-200 bg-white'}`}
      aria-busy={pending}
    >
      <p className="text-xs font-semibold text-slate-600">{mine ? text.you : text.assistant}</p>
      <p className="whitespace-pre-wrap break-words">{content}</p>
      {mine ? null : <SourcesBlock sources={sources} />}
    </div>
  )
}
