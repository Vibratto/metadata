import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type BackupPreview = components['schemas']['BackupPreview']
type JobRun = components['schemas']['JobRun']

const preview: BackupPreview = {
  artists: { total: 3, existing: 1 },
  albums: { total: 5, existing: 2 },
  tracks: { total: 40, existing: 12 },
  downloads: { total: 30, existing: 12 },
}

const restore: JobRun = {
  id: 7,
  kind: 'library_restore',
  params: {},
  user: 'demo',
  status: 'pending',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 0,
  total: 0,
  current: '',
  summary: {},
}

/** Library backup: export, preview and import. */
export default [
  http.get('/api/v1/catalog/backup/', () =>
    HttpResponse.json([{ model: 'catalog.artist', pk: 1, fields: { name: 'Daft Punk' } }]),
  ),
  http.post('/api/v1/catalog/backup/preview/', () => HttpResponse.json(preview)),
  http.post('/api/v1/catalog/backup/restore/', () => HttpResponse.json(restore, { status: 201 })),
]
