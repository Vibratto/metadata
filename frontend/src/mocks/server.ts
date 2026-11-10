import { setupServer } from 'msw/node'

import { handlers } from './handlers'

/** MSW server for Vitest (Node). */
export const server = setupServer(...handlers)
