import { Link } from 'react-router-dom'
import { strings } from '../lib/strings.es'

/** The subject does not exist for this account: the same view whichever the cause. */
export function ChatUnavailable() {
  return (
    <section className="flex flex-col items-start gap-3">
      <h1 className="text-2xl font-bold">{strings.chat.unavailable.title}</h1>
      <p className="text-slate-600">{strings.chat.unavailable.body}</p>
      <Link className="text-sm text-slate-900 underline" to="/subjects">
        {strings.chat.back}
      </Link>
    </section>
  )
}
