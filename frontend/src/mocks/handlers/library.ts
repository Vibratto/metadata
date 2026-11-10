import { http, HttpResponse } from 'msw'

import type { Album, Artist, Item, Track } from '../../views/library/kinds'

const artists: Artist[] = [
  {
    id: 1,
    name: 'Daft Punk',
    image_url: '',
    description: 'French electronic duo.',
    ytmusic_id: 'UCdaftpunk0000000000000a',
    monthly_listeners: 21_400_000,
    subscribers: null,
    album_count: 1,
    track_count: 2,
    pending_count: 1,
    suggest_import: false,
  },
  {
    id: 2,
    name: 'Pharrell Williams',
    image_url: '',
    description: '',
    ytmusic_id: 'UCpharrell000000000000b',
    monthly_listeners: null,
    subscribers: 3_100_000,
    album_count: 0,
    track_count: 1,
    pending_count: 0,
    suggest_import: false,
  },
]
/** Profiles saved without music: the artists related to the imported ones. */
const related: Artist[] = [
  {
    id: 3,
    name: 'Justice',
    image_url: '',
    description: '',
    ytmusic_id: 'UCjustice00000000000000b',
    monthly_listeners: 4_800_000,
    subscribers: null,
    album_count: 0,
    track_count: 0,
    pending_count: 0,
    suggest_import: true,
  },
  {
    id: 4,
    name: 'Kavinsky',
    image_url: '',
    description: '',
    ytmusic_id: 'UCkavinsky000000000000c',
    monthly_listeners: null,
    subscribers: 310_000,
    album_count: 0,
    track_count: 0,
    pending_count: 0,
    suggest_import: false,
  },
]
const credit = (a: Artist, position: number) => ({ id: a.id, name: a.name, position })
const albums: Album[] = [
  {
    id: 10,
    title: 'Random Access Memories',
    year: 2013,
    cover_url: 'https://example.com/ram.jpg',
    record_type: 'album',
    artists: [credit(artists[0]!, 0)],
    ytmusic_id: 'MPREb_ram',
    track_count: 2,
    pending_count: 1,
  },
]
const tracks: Track[] = [
  {
    id: 100,
    album: 10,
    recording: 100,
    also_on: 0,
    copyable: false,
    title: 'Get Lucky',
    track_number: 8,
    disc_number: 1,
    duration: 369,
    video_id: '5NV6Rdv1a3I',
    explicit: false,
    artists: [credit(artists[0]!, 0), credit(artists[1]!, 1)],
    downloaded: true,
    cover_url: 'https://example.com/ram.jpg',
  },
  {
    id: 101,
    album: 10,
    recording: 101,
    also_on: 2,
    copyable: false,
    title: 'Giorgio by Moroder',
    track_number: 3,
    disc_number: 1,
    duration: 544,
    video_id: null,
    explicit: false,
    artists: [credit(artists[0]!, 0)],
    downloaded: false,
    cover_url: '',
  },
]
const data: Record<string, Item[]> = { artists: [...artists, ...related], albums, tracks }

function find(kind: string, params: Record<string, unknown>): Item | undefined {
  return data[kind]!.find((i) => i.id === Number(params.id))
}

/** The artist list honours `profile_only`, which is what tells the two artist tabs apart. */
function listed(kind: string, query: URLSearchParams): Item[] {
  if (kind !== 'artists') return data[kind]!
  const profiles = query.get('profile_only')
  if (profiles === 'true') return related
  return profiles === 'false' ? artists : data[kind]!
}

const history = [
  {
    history_id: 2,
    history_date: '2026-10-02T10:00:00Z',
    history_type: '~',
    history_user: 'demo',
    changes: { title: 'Get Lucky (Radio Edit)' },
  },
  {
    history_id: 1,
    history_date: '2026-10-01T10:00:00Z',
    history_type: '+',
    history_user: null,
    changes: { title: 'Get Lucky' },
  },
]

const notFound = () => HttpResponse.json({ detail: 'Not found.' }, { status: 404 })

/** The recording of a track, with that track as its only appearance. */
function recording(track: Track) {
  return {
    id: track.recording,
    title: track.title,
    duration: track.duration,
    explicit: track.explicit,
    video_id: track.video_id,
    artists: track.artists,
    track_count: 1,
    downloaded: track.downloaded,
    tracks: [
      {
        id: track.id,
        album: track.album,
        album_title: 'Random Access Memories',
        title: track.title,
        disc_number: track.disc_number,
        track_number: track.track_number,
        downloaded: track.downloaded,
      },
    ],
  }
}

/** Handlers for one of the three lists and its item pages. */
function itemHandlers(kind: string) {
  const base = `/api/v1/catalog/${kind}`
  return [
    http.get(`${base}/`, ({ request }) => {
      const results = listed(kind, new URL(request.url).searchParams)
      return HttpResponse.json({ count: results.length, next: null, previous: null, results })
    }),
    http.get(`${base}/:id/`, ({ params }) => {
      const item = find(kind, params)
      return item ? HttpResponse.json(item) : notFound()
    }),
    http.patch(`${base}/:id/`, async ({ params, request }) =>
      HttpResponse.json({ ...find(kind, params), ...((await request.json()) as object) }),
    ),
    http.put(`${base}/:id/artists/`, async ({ params, request }) => {
      const { artists: ids } = (await request.json()) as { artists: number[] }
      const chosen = ids.map((id, i) => {
        const artist = artists.find((a) => a.id === id)!
        return credit(artist, i)
      })
      return HttpResponse.json({ ...find(kind, params), artists: chosen })
    }),
    http.delete(`${base}/:id/`, () => new HttpResponse(null, { status: 204 })),
    http.get(`${base}/:id/history/`, () => HttpResponse.json(history)),
    http.post(`${base}/:id/revert/`, ({ params }) => HttpResponse.json(find(kind, params))),
  ]
}

/** Library: lists, item pages, editing, credits, history and blocking. Stateless. */
export default [
  ...Object.keys(data).flatMap(itemHandlers),
  // By default every track is the only appearance of its recording.
  http.get('/api/v1/catalog/recordings/:id/', ({ params }) => {
    const track = tracks.find((t) => t.recording === Number(params.id))
    return track ? HttpResponse.json(recording(track)) : notFound()
  }),
  http.post('/api/v1/catalog/tracks/:id/split/', ({ params }) =>
    HttpResponse.json(find('tracks', params)),
  ),
  http.post('/api/v1/catalog/recordings/:id/merge/', ({ params }) =>
    HttpResponse.json(recording(tracks.find((t) => t.recording === Number(params.id))!)),
  ),
  http.post('/api/v1/catalog/blocked/', async ({ request }) =>
    HttpResponse.json(
      { id: 1, created_at: '2026-10-30T10:00:00Z', ...((await request.json()) as object) },
      { status: 201 },
    ),
  ),
]
