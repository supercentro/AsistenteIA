import { NavLink, Outlet } from 'react-router-dom'
import { signOut, useSession } from '../hooks/useSession'
import { strings } from '../lib/strings.es'
import { Button } from './Button'

/** Frame of every authenticated screen: banner, navigation of the role, sign-out and content. */
export function AppShell() {
  const { user } = useSession()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <p className="text-lg font-bold">{strings.app.name}</p>
          <nav aria-label={strings.nav.label}>
            <NavLink
              to="/subjects"
              className="rounded px-2 py-1 text-sm font-medium text-slate-700 underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 aria-[current=page]:text-slate-900 aria-[current=page]:underline"
            >
              {strings.nav.subjects}
            </NavLink>
          </nav>
          <div className="flex items-center gap-3">
            {user ? (
              <span className="max-w-[12rem] truncate text-sm text-slate-600">
                {strings.nav.signedInAs(user.name)}
              </span>
            ) : null}
            <Button variant="secondary" onClick={signOut}>
              {strings.nav.signOut}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
