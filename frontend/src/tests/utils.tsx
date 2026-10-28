import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from '../App'
import { createQueryClient } from '../lib/queryClient'
import { onSessionEnd, setUser, startSession } from '../lib/session'
import type { User } from '../types/api'
import { TOKEN_VALUE } from './api'

function LocationProbe() {
  const { pathname, search } = useLocation()
  return (
    <span data-testid="location" hidden>
      {pathname + search}
    </span>
  )
}

export interface RenderOptions {
  route?: string
  /** Router state of the first entry, e.g. `{ from: '/subjects' }` or `{ registered: true }`. */
  routeState?: unknown
  /** Start a signed-in session before rendering. */
  session?: { user: User; expiresInSeconds?: number } | null
}

/** Renders a tree with a fresh query client and router, optionally with a signed-in session. */
export function renderWithProviders(
  ui: ReactElement,
  { route = '/', routeState, session = null }: RenderOptions = {},
) {
  if (session) {
    startSession(TOKEN_VALUE, session.expiresInSeconds ?? 3600)
    setUser(session.user)
  }
  const client = createQueryClient({ retryDelay: 0 })
  // Mirrors lib/queryClient.ts: cached data never outlives the session that fetched it.
  const offSessionEnd = onSessionEnd(() => client.clear())
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname: route, state: routeState }]}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return {
    ...result,
    client,
    currentLocation: () => screen.getByTestId('location').textContent,
    unmountAndDetach: () => {
      offSessionEnd()
      result.unmount()
    },
  }
}

export function renderApp(options: RenderOptions = {}) {
  return renderWithProviders(<App />, options)
}
