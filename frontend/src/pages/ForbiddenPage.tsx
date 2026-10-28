import { Link } from 'react-router-dom'
import { strings } from '../lib/strings.es'

export default function ForbiddenPage() {
  return (
    <section className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-3xl font-bold text-slate-900">{strings.forbidden.title}</h1>
      <p className="text-slate-600">{strings.forbidden.body}</p>
      <Link className="text-slate-900 underline" to="/">
        {strings.forbidden.backHome}
      </Link>
    </section>
  )
}
