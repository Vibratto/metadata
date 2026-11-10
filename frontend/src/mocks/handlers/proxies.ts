import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type Proxy = components['schemas']['Proxy']

const proxies: Proxy[] = [
  {
    id: 1,
    url: 'http://proxy.example:3128',
    ip_version: 'ipv4',
    enabled: true,
    success_count: 42,
    failure_count: 3,
    last_used_at: '2026-10-30T10:00:00Z',
    last_failed_at: '2026-10-29T08:00:00Z',
    created_at: '2026-10-01T09:00:00Z',
  },
  {
    id: 2,
    url: 'socks5://socks.example:1080',
    ip_version: 'ipv6',
    enabled: false,
    success_count: 0,
    failure_count: 0,
    last_used_at: null,
    last_failed_at: null,
    created_at: '2026-10-02T09:00:00Z',
  },
]

/** Outgoing proxies: unpaginated list, CRUD and connection test. */
export default [
  http.get('/api/v1/proxies/', () => HttpResponse.json(proxies)),
  http.post('/api/v1/proxies/', async ({ request }) => {
    const body = (await request.json()) as Pick<Proxy, 'url' | 'enabled'>
    return HttpResponse.json(
      { ...proxies[1], ...body, id: 3, created_at: '2026-10-30T12:00:00Z' },
      { status: 201 },
    )
  }),
  http.patch('/api/v1/proxies/:id/', async ({ params, request }) => {
    const proxy = proxies.find((p) => p.id === Number(params.id))
    return HttpResponse.json({ ...proxy, ...((await request.json()) as object) })
  }),
  http.post('/api/v1/proxies/bulk/', async ({ request }) => {
    const body = (await request.json()) as { text: string }
    const lines = body.text.split('\n').filter((line) => line.trim() !== '')
    return HttpResponse.json({ created: lines.length, duplicates: [], invalid: [] })
  }),
  http.delete('/api/v1/proxies/:id/', () => new HttpResponse(null, { status: 204 })),
  http.post('/api/v1/proxies/:id/check/', () => HttpResponse.json({ ok: true, status_code: 200 })),
]
