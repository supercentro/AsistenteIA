import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { peekNotice } from '../lib/session'
import { strings } from '../lib/strings.es'
import { LoadingState } from './LoadingState'

/** Layout route: renders the nested routes only for a signed-in user. Not an authority. */
export function RequireAuth() {
  const { status } = useSession()
  const location = useLocation()

  if (status === 'anonymous') {
    // After a deliberate sign-out the next person must not be sent to the previous user's page.
    const from = peekNotice() === 'signed-out' ? undefined : location.pathname + location.search
    return <Navigate to="/login" replace state={{ from }} />
  }
  if (status === 'loading-profile') {
    return <LoadingState label={strings.states.loading} />
  }
  return <Outlet />
}
