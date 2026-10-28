import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { API, errorResponse } from '../tests/api'
import { server } from '../tests/server'
import { apiClient } from './apiClient'
import { ApiError } from './apiError'
import { createQueryClient, queryClient, shouldRetry } from './queryClient'
import { endSession, startSession } from './session'

afterEach(() => {
  endSession('signed-out')
})

function Probe() {
  const { status } = useQuery({
    queryKey: ['probe'],
    queryFn: async () => (await apiClient.get('/probe', { public: true })).data,
  })
  return <p>{status}</p>
}

function renderProbe() {
  const client = createQueryClient({ retryDelay: 0 })
  render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  )
}

describe('shouldRetry', () => {
  it('never retries a 4xx error', () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) {
      expect(shouldRetry(0, new ApiError({ kind: 'http', status }))).toBe(false)
    }
  })

  it('retries network errors and 5xx once', () => {
    expect(shouldRetry(0, new ApiError({ kind: 'network' }))).toBe(true)
    expect(shouldRetry(0, new ApiError({ kind: 'http', status: 503 }))).toBe(true)
    expect(shouldRetry(1, new ApiError({ kind: 'http', status: 503 }))).toBe(false)
    expect(shouldRetry(1, new ApiError({ kind: 'network' }))).toBe(false)
  })

  it('does not retry unexpected errors', () => {
    expect(shouldRetry(0, new Error('boom'))).toBe(false)
  })
})

describe('query client behaviour', () => {
  it('sends exactly one request when the server answers 4xx', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/probe`, () => {
        calls += 1
        return errorResponse(404, 'NOT_FOUND')
      }),
    )

    renderProbe()
    await waitFor(() => expect(screen.getByText('error')).toBeInTheDocument())

    expect(calls).toBe(1)
  })

  it('sends at most two requests for a transient 503 that recovers', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/probe`, () => {
        calls += 1
        return calls === 1
          ? errorResponse(503, 'SERVICE_UNAVAILABLE')
          : HttpResponse.json({ ok: 1 })
      }),
    )

    renderProbe()
    await waitFor(() => expect(screen.getByText('success')).toBeInTheDocument())

    expect(calls).toBe(2)
  })

  it('stops after one retry when the 503 persists', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/probe`, () => {
        calls += 1
        return errorResponse(503, 'SERVICE_UNAVAILABLE')
      }),
    )

    renderProbe()
    await waitFor(() => expect(screen.getByText('error')).toBeInTheDocument())

    expect(calls).toBe(2)
  })
})

describe('cache isolation', () => {
  it('clears the shared cache when the session ends', () => {
    startSession('token', 60)
    queryClient.setQueryData(['subjects', 'user-1'], [{ id: 'a' }])

    endSession('signed-out')

    expect(queryClient.getQueryData(['subjects', 'user-1'])).toBeUndefined()
  })
})
