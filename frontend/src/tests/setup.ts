import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, vi } from 'vitest'
import { endSession, takeNotice } from '../lib/session'
import { server } from './server'

let storageWrites: ReturnType<typeof vi.spyOn>[] = []

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))

beforeEach(() => {
  // The session must live in memory only: any storage or cookie write fails the test (L06 style guard).
  storageWrites = [vi.spyOn(Storage.prototype, 'setItem'), vi.spyOn(document, 'cookie', 'set')]
})

afterEach(() => {
  const writes = storageWrites.reduce((total, spy) => total + spy.mock.calls.length, 0)
  storageWrites.forEach((spy) => spy.mockRestore())
  cleanup()
  endSession('signed-out')
  takeNotice()
  server.resetHandlers()
  expect(writes, 'the application wrote to browser storage or cookies').toBe(0)
})

afterAll(() => server.close())
