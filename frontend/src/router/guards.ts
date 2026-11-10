import type { RouteLocationNormalized, RouteLocationRaw } from 'vue-router'

import { useSessionStore } from '../stores/session'

declare module 'vue-router' {
  /** Project-specific route metadata. */
  interface RouteMeta {
    /** Route reachable without a session (login, first-run setup). */
    public?: boolean
  }
}

/**
 * Guards private routes: anonymous users go to login (remembering the target), signed-in
 * users are bounced off public routes and non-admins off `adminOnly` ones. Asks the
 * server once per page load.
 */
export async function authGuard(to: RouteLocationNormalized): Promise<true | RouteLocationRaw> {
  const session = useSessionStore()
  if (!session.loaded) {
    try {
      await session.fetchMe()
    } catch {
      // Server down: treat as anonymous; the login form will show the error on submit.
    }
  }
  if (to.meta.public) return session.isAuthenticated ? { name: 'dashboard' } : true
  if (!session.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
  return true
}

/**
 * Post-login target. Internal paths only: `//host` or `https://…` would be an open redirect.
 */
export function safeRedirect(value: unknown): string | null {
  return typeof value === 'string' && /^\/(?![/\\])/.test(value) ? value : null
}
