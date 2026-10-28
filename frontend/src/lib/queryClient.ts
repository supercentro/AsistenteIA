import { QueryClient, type QueryClientConfig } from '@tanstack/react-query'
import { ApiError } from './apiError'
import { onSessionEnd } from './session'

const MAX_TRANSIENT_RETRIES = 1

/** 4xx answers are final; only network errors and 5xx are retried, once. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (!(error instanceof ApiError) || error.isClientError) {
    return false
  }
  return failureCount < MAX_TRANSIENT_RETRIES
}

export function createQueryClient(
  queries: NonNullable<QueryClientConfig['defaultOptions']>['queries'] = {},
): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false, ...queries },
    },
  })
}

export const queryClient = createQueryClient()

// Cached server data belongs to the session that fetched it: drop it whenever a session ends.
onSessionEnd(() => queryClient.clear())
