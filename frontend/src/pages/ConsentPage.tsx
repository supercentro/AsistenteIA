import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { ErrorState } from '../components/ErrorState'
import { PolicyView } from '../components/PolicyView'
import { DEFAULT_HOME } from '../components/RedirectIfAuthenticated'
import { useAcceptConsent } from '../hooks/useAcceptConsent'
import { useFocusOnMount } from '../hooks/useFocusOnMount'
import { signOut, useSession } from '../hooks/useSession'
import { ApiError, messageFor } from '../lib/apiError'
import { isHeldForConsent } from '../lib/consent'
import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import { safeReturnTarget } from '../lib/returnTarget'
import { strings } from '../lib/strings.es'

function returnTarget(state: unknown): string {
  const from = safeReturnTarget((state as { from?: unknown } | null)?.from)
  return from === null || from.startsWith('/consent') ? DEFAULT_HOME : from
}

export default function ConsentPage() {
  const { user } = useSession()
  const location = useLocation()
  const heading = useFocusOnMount<HTMLHeadingElement>()
  const [ticked, setTicked] = useState(false)
  const accept = useAcceptConsent()

  if (!isHeldForConsent(user)) {
    // Consent already current, a teacher, or just accepted: go on to the page that was wanted.
    return <Navigate to={returnTarget(location.state)} replace />
  }

  const error = accept.error
  const versionRejected = error instanceof ApiError && error.code === 'INVALID_CONSENT_VERSION'

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-8">
      <h1 ref={heading} tabIndex={-1} className="text-2xl font-bold text-slate-900">
        {strings.consent.title}
      </h1>
      <Alert variant="info">
        {user?.consent_accepted_at === null ? strings.consent.firstTime : strings.consent.changed}
      </Alert>
      <PolicyView />
      <a
        className="text-sm text-slate-900 underline"
        href="/privacy"
        target="_blank"
        rel="noopener noreferrer"
      >
        {strings.consent.policyLink}
      </a>
      {versionRejected ? <Alert variant="error">{strings.consent.versionChanged}</Alert> : null}
      {error && !versionRejected ? (
        <ErrorState
          message={error instanceof ApiError ? messageFor(error) : strings.errors.unknown}
          onRetry={() => accept.mutate()}
        />
      ) : null}
      <label className="flex items-start gap-3 text-sm text-slate-900">
        <input
          type="checkbox"
          checked={ticked}
          onChange={(event) => setTicked(event.target.checked)}
          className="mt-1 h-5 w-5 rounded border-slate-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
        />
        <span>{strings.consent.checkbox(PRIVACY_POLICY_VERSION)}</span>
      </label>
      <div className="flex flex-wrap gap-3">
        <Button disabled={!ticked} pending={accept.isPending} onClick={() => accept.mutate()}>
          {accept.isPending ? strings.consent.accepting : strings.consent.accept}
        </Button>
        <Button variant="secondary" onClick={signOut}>
          {strings.consent.signOut}
        </Button>
      </div>
    </main>
  )
}
