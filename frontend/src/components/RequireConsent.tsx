import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { isHeldForConsent } from '../lib/consent'

/**
 * Layout route inside `RequireAuth`: a student without consent for the current policy version is
 * sent to the consent screen and the nested routes are never mounted, so their data is not
 * requested. Usability only: the backend refuses the chat with 403 CONSENT_REQUIRED on its own.
 */
export function RequireConsent() {
  const { user } = useSession()
  const location = useLocation()

  if (isHeldForConsent(user)) {
    return <Navigate to="/consent" replace state={{ from: location.pathname + location.search }} />
  }
  return <Outlet />
}
