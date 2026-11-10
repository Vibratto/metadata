import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type ActivityLog = components['schemas']['ActivityLog']
type TechnicalLog = components['schemas']['TechnicalLog']

const page = <T>(results: T[]) =>
  HttpResponse.json({ count: results.length, next: null, previous: null, results })

const entries: ActivityLog[] = [
  {
    id: 2,
    created_at: '2026-01-01T10:05:00Z',
    user: 1,
    username: 'demo',
    action: 'catalog.artist.updated',
    object_type: 'catalog.artist',
    object_id: '7',
    detail: {},
  },
  {
    id: 1,
    created_at: '2026-01-01T10:00:00Z',
    user: null,
    username: '',
    action: 'activity.technical_logs.purged',
    object_type: '',
    object_id: '',
    detail: { deleted: 3 },
  },
]

const logs: TechnicalLog[] = [
  {
    id: 2,
    created_at: '2026-01-01T10:01:00Z',
    level: 40,
    logger_name: 'catalog.tasks.downloading',
    msg: '[job 1] yt-dlp failed',
    trace: 'Traceback (most recent call last):\n  ...',
  },
  {
    id: 1,
    created_at: '2026-01-01T10:00:00Z',
    level: 20,
    logger_name: 'jobs.runner',
    msg: '[job 1] inicio',
    trace: null,
  },
]

/** Activity history and technical logs. */
export default [
  http.get('/api/v1/activity/entries/', () => page(entries)),
  http.get('/api/v1/activity/logs/', () => page(logs)),
]
