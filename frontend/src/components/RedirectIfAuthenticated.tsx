import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { safeReturnTarget } from '../lib/returnTarget'

export const DEFAULT_HOME = '/subjects'

/** Layout route for login and registration: a signed-in user is sent on to the page they wanted. */
export function RedirectIfAuthenticated() {
  const { status } = useSession()
  const location = useLocation()

  if (status === 'authenticated') {
    const from = (location.state as { from?: unknown } | null)?.from
    return <Navigate to={safeReturnTarget(from) ?? DEFAULT_HOME} replace />
  }
  return <Outlet />
}
