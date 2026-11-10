import { http, HttpResponse } from 'msw'

/** Library search and summary. */
const result = (id: number, name: string, subtitle = '') => ({
  id,
  name,
  title: name,
  image: '',
  subtitle,
})

/** Sample results for the global search: one or two of each kind. */
export function searchBody(type: string) {
  const all = {
    artists: { count: 1, results: [result(1, 'Daft Punk')] },
    albums: {
      count: 2,
      results: [result(10, 'Discovery', 'Daft Punk'), result(11, 'Homework', 'Daft Punk')],
    },
    tracks: { count: 1, results: [result(100, 'Discovery (live)', 'Daft Punk')] },
  }
  return type === 'all' ? all : { [type]: all[type as keyof typeof all] }
}

export default [
  http.get('/api/v1/catalog/search/', ({ request }) =>
    HttpResponse.json(searchBody(new URL(request.url).searchParams.get('type') ?? 'all')),
  ),
  http.get('/api/v1/catalog/summary/', () =>
    HttpResponse.json({
      artists: 12,
      related_artists: 30,
      albums: 48,
      recordings: 498,
      tracks: 530,
      downloaded: 211,
    }),
  ),
]
