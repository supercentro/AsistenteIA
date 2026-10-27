import { strings } from '../lib/strings.es'

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-4xl font-bold text-slate-900">{strings.home.title}</h1>
      <p className="text-lg text-slate-600">{strings.home.subtitle}</p>
    </main>
  )
}
