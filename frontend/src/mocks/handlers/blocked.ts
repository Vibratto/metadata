import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

const items: components['schemas']['BlockedItem'][] = [
  {
    id: 1,
    kind: 'album',
    external_id: 'MPREb_discovery',
    name: 'Discovery',
    created_at: '2026-10-20T09:30:00Z',
  },
  {
    id: 2,
    kind: 'track',
    external_id: 'gAjR4_CbPpQ',
    name: 'Harder, Better, Faster, Stronger',
    created_at: '2026-10-18T17:05:00Z',
  },
]

/** Blocked items. */
export default [
  http.get('/api/v1/catalog/blocked/', () =>
    HttpResponse.json({ count: items.length, results: items }),
  ),
  http.delete('/api/v1/catalog/blocked/:id/', () => new HttpResponse(null, { status: 204 })),
]
