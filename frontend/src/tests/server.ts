import { setupServer } from 'msw/node'

/** MSW server shared by all tests. Add request handlers per test with `server.use(...)`. */
export const server = setupServer()
