import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type JobRun = components['schemas']['JobRun']

const run = (fields: Partial<JobRun>): JobRun => ({
  id: 1,
  kind: 'import',
  params: {},
  user: 'demo',
  status: 'running',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 0,
  total: 0,
  current: '',
  summary: {},
  ...fields,
})

const jobs: JobRun[] = [
  run({ id: 2, kind: 'download', status: 'succeeded', done: 10, total: 10 }),
  run({ id: 1, status: 'running', done: 4, total: 10, current: 'Daft Punk' }),
]

/** Tareas en segundo plano. */
export default [
  http.get('/api/v1/jobs/runs/', () =>
    HttpResponse.json({ count: jobs.length, next: null, previous: null, results: jobs }),
  ),
  http.post('/api/v1/jobs/runs/', async ({ request }) => {
    const { kind, params } = (await request.json()) as Pick<JobRun, 'kind' | 'params'>
    return HttpResponse.json(run({ id: 3, kind, params, status: 'pending' }), { status: 201 })
  }),
  http.get('/api/v1/jobs/runs/:id/', ({ params }) =>
    HttpResponse.json(jobs.find((j) => j.id === Number(params.id)) ?? run({ id: 3 })),
  ),
  http.post('/api/v1/jobs/runs/:id/stop/', ({ params }) =>
    HttpResponse.json(run({ id: Number(params.id), status: 'stopping' })),
  ),
]
