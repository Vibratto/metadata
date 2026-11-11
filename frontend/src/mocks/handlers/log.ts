import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type ActivityLog = components['schemas']['ActivityLog']

const page = <T>(results: T[]) =>
  HttpResponse.json({ count: results.length, next: null, previous: null, results })

const entries: ActivityLog[] = [
  {
    id: 2,
    created_at: '2026-01-01T10:05:00Z',
    user: 1,
    username: 'demo',
    action: 'catalog.album.edited',
    object_type: 'catalog.album',
    object_id: '7',
    detail: {},
  },
  {
    id: 1,
    created_at: '2026-01-01T10:00:00Z',
    user: null,
    username: '',
    action: 'catalog.download.finished',
    object_type: '',
    object_id: '',
    detail: { downloaded: 3, failed: 0, skipped: 0 },
  },
]

/** Activity history. */
export default [http.get('/api/v1/activity/entries/', () => page(entries))]
