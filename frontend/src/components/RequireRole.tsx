import { Outlet } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import ForbiddenPage from '../pages/ForbiddenPage'
import type { UserRole } from '../types/api'

interface RequireRoleProps {
  roles: readonly UserRole[]
}

/**
 * Layout route inside `RequireAuth`: other roles get the "not allowed" view and the nested
 * routes are never mounted, so their data is never requested. The backend still enforces it.
 */
export function RequireRole({ roles }: RequireRoleProps) {
  const { user } = useSession()
  if (!user || !roles.includes(user.role)) {
    return <ForbiddenPage />
  }
  return <Outlet />
}
