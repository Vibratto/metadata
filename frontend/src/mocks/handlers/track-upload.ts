import { http, HttpResponse } from 'msw'

import type { components } from '../../api/schema'

type Track = components['schemas']['Track']

const track = (id: number): Track => ({
  id,
  album: 1,
  recording: id,
  also_on: 0,
  copyable: false,
  title: 'One More Time',
  track_number: 1,
  disc_number: 1,
  duration: 320,
  explicit: false,
  video_id: null,
  artists: [],
  downloaded: true,
  cover_url: '',
})

/** Manual audio upload; the track itself is mocked in `library.ts`. */
export default [
  http.post('/api/v1/catalog/tracks/:id/upload/', ({ params }) =>
    HttpResponse.json(track(Number(params.id)), { status: 201 }),
  ),
]
