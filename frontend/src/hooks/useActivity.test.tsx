import { QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { StrictMode, type ReactNode } from 'react'
import { beforeEach, describe, expect, it } from 'vitest'
import { startSession } from '../lib/session'
import { TOKEN_VALUE } from '../tests/api'
import { createQueryClient } from '../lib/queryClient'
import { serveActivity } from '../tests/activity'
import { SUBJECT } from '../tests/materials'
import { useActivity } from './useActivity'

function setup() {
  const client = createQueryClient({ retryDelay: 0 })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

describe('useActivity', () => {
  beforeEach(() => {
    startSession(TOKEN_VALUE, 3600)
  })

  it('keys the query by user and subject only, never by a window', async () => {
    serveActivity()
    const { client, wrapper } = setup()

    const { result } = renderHook(() => useActivity('user-1', SUBJECT.id), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(
      client
        .getQueryCache()
        .findAll()
        .map((query) => query.queryKey),
    ).toEqual([['activity', 'user-1', SUBJECT.id]])
  })

  it('does not keep the response once nobody is looking at it', async () => {
    serveActivity()
    const { client, wrapper } = setup()
    const { result, unmount } = renderHook(() => useActivity('user-1', SUBJECT.id), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    unmount()

    await waitFor(() => expect(client.getQueryCache().findAll()).toHaveLength(0))
  })

  it('sends one request even in strict mode, which mounts twice in development', async () => {
    const state = serveActivity()
    const client = createQueryClient({ retryDelay: 0 })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <StrictMode>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </StrictMode>
    )

    const { result } = renderHook(() => useActivity('user-1', SUBJECT.id), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(state.calls).toBe(1)
  })

  it('does not retry a failure by itself', async () => {
    const { wrapper } = setup()
    let calls = 0
    const { server } = await import('../tests/server')
    const { HttpResponse, http } = await import('msw')
    const { API } = await import('../tests/api')
    server.use(
      http.get(`${API}/subjects/${SUBJECT.id}/activity`, () => {
        calls += 1
        return HttpResponse.json({ code: 'SERVICE_UNAVAILABLE', message: 'x' }, { status: 503 })
      }),
    )

    const { result } = renderHook(() => useActivity('user-1', SUBJECT.id), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(calls).toBe(1)
  })
})
