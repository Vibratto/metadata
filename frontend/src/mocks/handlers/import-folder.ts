import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type JobRun = components['schemas']['JobRun']

const ID = 30

const finished: JobRun = {
  id: ID,
  kind: 'folder_import',
  params: { folder: 'Daft Punk' },
  user: 'demo',
  status: 'succeeded',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: '2026-01-01T10:01:00Z',
  done: 4,
  total: 4,
  current: '',
  summary: {
    albums: 1,
    tracks: 12,
    linked: 2,
    already_linked: 0,
    completed: true,
    unlinked: [
      { file: 'Daft Punk/demo.mp3', reason: 'no_tags' },
      { file: 'Daft Punk/live.flac', reason: 'not_found' },
    ],
  },
}

/**
 * Folder import: the `folder_import` job finishes at once with a sample summary. Every other
 * job stays in `jobs.ts` (this file loads first and lets the request through by not answering).
 */
export default [
  http.post('/api/v1/jobs/runs/', async ({ request }) => {
    const { kind } = (await request.clone().json()) as Pick<JobRun, 'kind'>
    if (kind === 'folder_import') return HttpResponse.json(finished, { status: 201 })
  }),
  http.get(`/api/v1/jobs/runs/${ID}/`, () => HttpResponse.json(finished)),
]
