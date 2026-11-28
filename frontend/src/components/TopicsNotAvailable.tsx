import { Link } from 'react-router-dom'
import { strings } from '../lib/strings.es'

/** The same view for another teacher's material, unknown material and topics switched off. */
export function TopicsNotAvailable() {
  return (
    <section className="flex flex-col items-start gap-3">
      <h1 className="text-2xl font-bold">{strings.materials.notFound.title}</h1>
      <p className="text-slate-600">{strings.materials.notFound.body}</p>
      <Link className="text-sm text-slate-900 underline" to="/subjects">
        {strings.materials.back}
      </Link>
    </section>
  )
}
