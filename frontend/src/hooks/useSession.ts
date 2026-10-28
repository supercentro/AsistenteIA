import { useSyncExternalStore } from 'react'
import { endSession, getSnapshot, subscribe } from '../lib/session'
import type { User } from '../types/api'

export type SessionStatus = 'anonymous' | 'loading-profile' | 'authenticated'

export interface SessionView {
  status: SessionStatus
  user: User | null
}

const views = new WeakMap<object, SessionView>()

/** Read-only view of the session for components. The token is deliberately not exposed. */
export function useSession(): SessionView {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  let view = views.get(snapshot)
  if (!view) {
    const status: SessionStatus =
      snapshot.token === null ? 'anonymous' : snapshot.user ? 'authenticated' : 'loading-profile'
    view = { status, user: snapshot.user }
    views.set(snapshot, view)
  }
  return view
}

export function signOut(): void {
  endSession('signed-out')
}
