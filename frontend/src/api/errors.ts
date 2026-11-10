import { ApiError } from './client'

/** API error body: `{ detail }`, plus per-field keys on validation 400s. */
function flatten(body: unknown): string[] {
  if (typeof body === 'string') return [body]
  if (Array.isArray(body)) return body.flatMap(flatten)
  if (body !== null && typeof body === 'object') return Object.values(body).flatMap(flatten)
  return []
}

/**
 * User-facing text for an API error: the server's own messages, else the generic `errors.*`.
 * Any other exception is a bug and is rethrown.
 */
export function errorText(e: unknown, t: (key: string) => string): string {
  if (!(e instanceof ApiError)) throw e
  const body = e.body as { detail?: unknown } | null
  const messages = typeof body?.detail === 'string' ? [body.detail] : flatten(e.body)
  return messages.join(' ') || t(e.messageKey)
}
