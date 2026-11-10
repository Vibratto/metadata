import { setupWorker } from 'msw/browser'

import { handlers } from './handlers'

/** MSW service worker for the browser; only loaded in development with `VITE_MOCKS=1`. */
export const worker = setupWorker(...handlers)
