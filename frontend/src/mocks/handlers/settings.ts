import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type Preference = components['schemas']['Preference']

const preferences: Preference[] = [
  { key: 'download.format', value: 'opus', default: 'opus' },
  { key: 'download.folder', value: 'music', default: 'music' },
  {
    key: 'download.name_template',
    value: '{albumartist}/{album}/{disc}-{track}-{title}',
    default: '{albumartist}/{album}/{disc}-{track}-{title}',
  },
  {
    key: 'tags.artist_separators',
    value: [' / ', ' feat. ', ' feat ', ' ft. ', ' ft ', '; '],
    default: [' / ', ' feat. ', ' feat ', ' ft. ', ' ft ', '; '],
  },
  { key: 'import.suggestion_threshold', value: 1_000_000, default: 1_000_000 },
]

/** Global settings. Stateless: every test starts from the same data. */
export default [
  http.get('/api/v1/preferences/', () => HttpResponse.json(preferences)),
  http.put('/api/v1/preferences/:key/', async ({ params, request }) => {
    const { value } = (await request.json()) as { value: unknown }
    const pref = preferences.find((p) => p.key === params.key)
    return HttpResponse.json({ ...pref, value })
  }),
]
