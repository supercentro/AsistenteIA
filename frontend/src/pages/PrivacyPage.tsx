import { Link } from 'react-router-dom'
import { PolicyView } from '../components/PolicyView'
import { useFocusOnMount } from '../hooks/useFocusOnMount'
import { strings } from '../lib/strings.es'

/** Public: readable before registering, and by any signed-in user, held or not. */
export default function PrivacyPage() {
  const heading = useFocusOnMount<HTMLHeadingElement>()
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-8">
      <h1 ref={heading} tabIndex={-1} className="text-2xl font-bold text-slate-900">
        {strings.privacy.title}
      </h1>
      <PolicyView />
      <Link className="text-sm text-slate-900 underline" to="/">
        {strings.privacy.back}
      </Link>
    </main>
  )
}
