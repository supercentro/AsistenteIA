import { Link } from 'react-router-dom'
import { strings } from '../lib/strings.es'

export default function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-3xl font-bold text-slate-900">{strings.notFound.title}</h1>
      <Link className="text-blue-700 underline focus:outline-2 focus:outline-blue-700" to="/">
        {strings.notFound.backHome}
      </Link>
    </main>
  )
}
