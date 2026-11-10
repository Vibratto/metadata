/** Common API error category, mapped to an `errors.*` vue-i18n key. */
export type ApiErrorKind =
  'network' | 'unauthorized' | 'forbidden' | 'notFound' | 'server' | 'unknown'

/**
 * Error from an API request; `kind` maps to an `errors.*` i18n key.
 */
export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    readonly body: unknown = null,
  ) {
    super(kind)
  }

  /** vue-i18n key of the message shown to the user. */
  get messageKey(): string {
    return `errors.${this.kind}`
  }
}

export function kindOf(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'notFound'
  return status >= 500 ? 'server' : 'unknown'
}

export function csrfToken(): string {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? ''
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * JSON request to the Django API. Session cookies require the CSRF token in the
 * `X-CSRFToken` header on every non-read method. A `FormData` body goes as multipart
 * (file uploads); the browser sets its Content-Type with the boundary.
 *
 * @throws {ApiError} si no hay red o la respuesta no es 2xx.
 */
export async function api<T = unknown>(
  path: string,
  init: { method?: string; body?: unknown; poll?: boolean; signal?: AbortSignal } = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  // The backend only serves the API to the frontend (see core/api_guard.py).
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Vibratto-Client': 'web',
  }
  const form = init.body instanceof FormData
  if (init.body !== undefined && !form) headers['Content-Type'] = 'application/json'
  if (!SAFE_METHODS.has(method)) headers['X-CSRFToken'] = csrfToken()
  // Automatic polling: the server does not count it as activity (idle timeout).
  if (init.poll) headers['X-Background-Poll'] = '1'

  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      signal: init.signal,
      body: form
        ? (init.body as FormData)
        : init.body === undefined
          ? undefined
          : JSON.stringify(init.body),
    })
  } catch (e) {
    // A deliberate abort is not a network failure.
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError('network', 0)
  }

  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(kindOf(res.status), res.status, body)
  return body as T
}
