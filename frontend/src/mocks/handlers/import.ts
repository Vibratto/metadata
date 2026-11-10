import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type Result = components['schemas']['ArtistLookupResult']

const artists: Result[] = [
  {
    ytmusic_id: 'UCdaftpunk0000000000000a',
    name: 'Daft Punk',
    image_url: 'https://lh3.googleusercontent.com/daft-punk=w250-h250',
    monthly_listeners: 21_400_000,
    subscribers: null,
    album_count: 4,
    single_count: 12,
    in_library: true,
    blocked: false,
  },
  {
    ytmusic_id: 'UCjustice00000000000000b',
    name: 'Justice',
    image_url: null,
    monthly_listeners: null,
    subscribers: 900_000,
    album_count: null,
    single_count: null,
    in_library: false,
    blocked: false,
  },
  {
    ytmusic_id: 'UCtribute0000000000000c',
    name: 'Daft Punk Tribute',
    image_url: null,
    monthly_listeners: null,
    subscribers: null,
    album_count: null,
    single_count: null,
    in_library: false,
    blocked: true,
  },
]

/** Artist lookup on YouTube Music, used by the import screen. */
export default [
  http.get('/api/v1/catalog/ytmusic/artists/', ({ request }) => {
    const q = (new URL(request.url).searchParams.get('q') as string).toLowerCase()
    return HttpResponse.json({ results: artists.filter((a) => a.name.toLowerCase().includes(q)) })
  }),
]
