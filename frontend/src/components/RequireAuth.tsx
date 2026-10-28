import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import { strings } from '../lib/strings.es'
import { LoadingState } from './LoadingState'

/** Layout route: renders the nested routes only for a signed-in user. Not an authority. */
export function RequireAuth() {
  const { status } = useSession()
  const location = useLocation()

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (status === 'loading-profile') {
    return <LoadingState label={strings.states.loading} />
  }
  return <Outlet />
}
