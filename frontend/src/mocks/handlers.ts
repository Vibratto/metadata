import type { RequestHandler } from 'msw'

// One file per area in `handlers/`, like routes and texts: each view adds its own
// without touching a shared array (and without conflicts between pull requests).
const modules = import.meta.glob<{ default: RequestHandler[] }>('./handlers/*.ts', { eager: true })

/** Mocked API responses, for development without a backend and for the tests. */
export const handlers: RequestHandler[] = Object.values(modules).flatMap((m) => m.default)
