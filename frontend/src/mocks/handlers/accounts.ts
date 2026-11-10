import { http, HttpResponse } from 'msw'

import type { User } from '../../stores/session'

const user: User = { username: 'demo', language: '' }

/** Session and account. */
export default [
  http.get('/api/v1/accounts/me/', () => HttpResponse.json(user)),
  http.post('/api/v1/accounts/login/', () => HttpResponse.json(user)),
  http.post('/api/v1/accounts/logout/', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/v1/accounts/setup/', () =>
    HttpResponse.json({ needed: false, code_required: false }),
  ),
  http.post('/api/v1/accounts/setup/', () => HttpResponse.json(user, { status: 201 })),
  http.put('/api/v1/accounts/language/', async ({ request }) =>
    HttpResponse.json(await request.json()),
  ),
  http.post('/api/v1/accounts/password/', () => new HttpResponse(null, { status: 204 })),
  http.post('/api/v1/accounts/username/', async ({ request }) => {
    const { username } = (await request.json()) as { username: string }
    return HttpResponse.json({ ...user, username })
  }),
]
