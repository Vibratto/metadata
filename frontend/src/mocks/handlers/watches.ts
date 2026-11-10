import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type Artist = components['schemas']['Artist']
type Watch = components['schemas']['Watch']
type WatchRequest = components['schemas']['WatchRequest']
type WatchRun = components['schemas']['WatchRun']

const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

export const artists: Artist[] = [
  {
    id: 1,
    name: 'Rosalía',
    image_url: '',
    description: '',
    ytmusic_id: 'UCrosalia0000000000000a',
    monthly_listeners: null,
    subscribers: null,
    album_count: 0,
    track_count: 0,
    pending_count: 0,
    suggest_import: false,
  },
  {
    id: 2,
    name: 'Bad Bunny',
    image_url: '',
    description: '',
    ytmusic_id: 'UCbadbunny000000000000b',
    monthly_listeners: null,
    subscribers: null,
    album_count: 0,
    track_count: 0,
    pending_count: 0,
    suggest_import: false,
  },
  {
    id: 3,
    name: 'Rauw Alejandro',
    image_url: '',
    description: '',
    ytmusic_id: 'UCrauw000000000000000c',
    monthly_listeners: null,
    subscribers: null,
    album_count: 0,
    track_count: 0,
    pending_count: 0,
    suggest_import: false,
  },
]

const credits = (ids: number[]) =>
  ids.map((id, position) => ({
    id,
    name: (artists.find((a) => a.id === id) as Artist).name,
    position,
  }))

export const watches: Watch[] = [
  {
    id: 1,
    name: 'Urban',
    enabled: true,
    interval_hours: 24,
    auto_download: false,
    artists: credits([2, 3]),
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
  },
  {
    id: 2,
    name: 'Flamenco',
    enabled: false,
    interval_hours: 6,
    auto_download: true,
    artists: credits([1]),
    created_at: '2026-01-02T10:00:00Z',
    updated_at: '2026-01-02T10:00:00Z',
  },
]

export const runs: WatchRun[] = [
  {
    id: 2,
    watch: 1,
    started_at: '2026-01-03T10:00:00Z',
    finished_at: '2026-01-03T10:01:00Z',
    status: 'failed',
    found: 0,
    detail: 'YouTube Music did not answer',
  },
  {
    id: 1,
    watch: 1,
    started_at: '2026-01-02T10:00:00Z',
    finished_at: '2026-01-02T10:01:00Z',
    status: 'succeeded',
    found: 2,
    detail: '',
  },
]

/** What the API would return after saving `body` (the form always sends the artists). */
function saved(base: Watch, body: WatchRequest): Watch {
  const { artist_ids, ...fields } = body
  return { ...base, ...fields, artists: credits(artist_ids as number[]) }
}

const byId = (id: unknown) => watches.find((w) => w.id === Number(id))

/** Release watches, plus the library artist search their form uses. */
export default [
  http.get('/api/v1/watches/', () => HttpResponse.json(page(watches))),
  http.post('/api/v1/watches/', async ({ request }) =>
    HttpResponse.json(
      saved({ ...watches[0], id: 3 } as Watch, (await request.json()) as WatchRequest),
      {
        status: 201,
      },
    ),
  ),
  http.get('/api/v1/watches/:id/', ({ params }) => {
    const watch = byId(params.id)
    return watch
      ? HttpResponse.json(watch)
      : HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
  }),
  http.patch('/api/v1/watches/:id/', async ({ params, request }) =>
    HttpResponse.json(saved(byId(params.id) as Watch, (await request.json()) as WatchRequest)),
  ),
  http.delete('/api/v1/watches/:id/', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/v1/watches/:id/runs/', ({ params }) =>
    HttpResponse.json(page(runs.filter((r) => r.watch === Number(params.id)))),
  ),
  http.get('/api/v1/catalog/artists/', ({ request }) => {
    const search = (new URL(request.url).searchParams.get('search') ?? '').toLowerCase()
    return HttpResponse.json(page(artists.filter((a) => a.name.toLowerCase().includes(search))))
  }),
]
