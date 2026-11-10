import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { components } from '../api/schema'
import { api } from '../api/client'
import { messages } from '../locales'
import { handlers } from '../mocks/handlers'
import downloadHandlers from '../mocks/handlers/download'
import { server } from '../mocks/server'
import downloadRoutes from '../router/routes/download'
import { render } from './helpers'
import { sessionPinia } from './viewHelpers'

type JobRun = components['schemas']['JobRun']
type Track = components['schemas']['Track']

const track = (id: number, title: string): Track => ({
  id,
  album: 1,
  recording: id,
  also_on: 0,
  copyable: false,
  title,
  track_number: id,
  disc_number: 1,
  duration: 200,
  explicit: false,
  video_id: `video-${id}`,
  artists: [{ id: 1, name: 'Daft Punk', position: 0 }],
  downloaded: false,
  cover_url: '',
})
const run = (fields: Partial<JobRun> = {}): JobRun => ({
  id: 9,
  kind: 'download',
  params: {},
  user: 'demo',
  status: 'running',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 1,
  total: 2,
  current: 'One More Time',
  summary: {},
  ...fields,
})
const page = <T>(results: T[], next: string | null = null, previous: string | null = null) =>
  HttpResponse.json({ count: results.length, next, previous, results })

/**
 * Sets the API up: pending tracks, artists, albums, the latest download (`latest`) and what
 * starting one answers (`launch`). Records track requests and launches.
 */
function serve({
  latest = [] as JobRun[],
  launch = () => HttpResponse.json(run({ status: 'pending' }), { status: 201 }) as Response,
  detail = run({ status: 'succeeded', done: 2 }),
} = {}) {
  const trackQueries: Record<string, string>[] = []
  const launched: unknown[] = []
  const runQueries: Record<string, string>[] = []
  server.use(
    http.get('/api/v1/catalog/tracks/', ({ request }) => {
      const query = Object.fromEntries(new URL(request.url).searchParams)
      trackQueries.push(query)
      return query.page === '2'
        ? page([track(3, 'Digital Love')], null, 'http://x/?page=1')
        : page(
            [track(1, 'One More Time'), { ...track(2, 'Aerodynamic'), copyable: true }],
            'http://x/?page=2',
          )
    }),
    http.get('/api/v1/catalog/artists/', () => page([{ id: 1, name: 'Daft Punk' }])),
    http.get('/api/v1/catalog/albums/', ({ request }) =>
      page(
        new URL(request.url).searchParams.get('artist') === '1'
          ? [{ id: 1, title: 'Discovery' }]
          : [
              { id: 1, title: 'Discovery' },
              { id: 2, title: 'Homework' },
            ],
      ),
    ),
    http.get('/api/v1/jobs/runs/', ({ request }) => {
      runQueries.push(Object.fromEntries(new URL(request.url).searchParams))
      return page(latest)
    }),
    http.post('/api/v1/jobs/runs/', async ({ request }) => {
      launched.push(await request.json())
      return launch()
    }),
    http.get('/api/v1/jobs/runs/:id/', () => HttpResponse.json(detail)),
    http.get('/api/v1/jobs/runs/:id/lines/', () => HttpResponse.json([])),
  )
  return { trackQueries, launched, runQueries }
}

async function mount(path = '/download', locale = 'en', ready = 'One More Time') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [...downloadRoutes, { path: '/other', name: 'other', component: { template: '<p/>' } }],
  })
  await router.push(path)
  const wrapper = render(
    { template: '<RouterView />' },
    { global: { plugins: [router, sessionPinia()] } },
    locale,
  )
  await vi.waitFor(() => expect(wrapper.text()).toContain(ready))
  return { wrapper, router }
}

const button = (wrapper: Awaited<ReturnType<typeof mount>>['wrapper'], text: string) =>
  wrapper.findAll('button').find((b) => b.text().includes(text))!

describe('DownloadView', () => {
  it('warns that audio will be copied from another album, only on copyable tracks', async () => {
    serve()
    const { wrapper } = await mount()
    const rows = wrapper.findAll('.download__copy')
    expect(rows.map((r) => r.text())).toEqual(['Copied from another album'])
  })

  it('lists only pending tracks and keeps that fixed in the URL', async () => {
    const api = serve()
    const { router } = await mount('/download?downloaded=true')
    expect(router.currentRoute.value.query.downloaded).toBe('false')
    expect(api.trackQueries[0]).toEqual({ downloaded: 'false' })
    expect(api.runQueries[0]).toEqual({ kind: 'download' })
  })

  it('filters by artist and album with searchable pickers, and changing the artist drops the album', async () => {
    const api = serve()
    const albumQueries: Record<string, string>[] = []
    server.events.on('request:start', ({ request }) => {
      const url = new URL(request.url)
      if (url.pathname === '/api/v1/catalog/albums/')
        albumQueries.push(Object.fromEntries(url.searchParams))
    })
    const { wrapper, router } = await mount('/download?album=2')
    const [artist, album] = wrapper.findAll('input[role="combobox"]')
    await artist!.trigger('focus')
    await vi.waitFor(() => expect(wrapper.findAll('[role="option"]')).toHaveLength(1))
    await wrapper.get('[role="option"]').trigger('mousedown')
    await vi.waitFor(() => expect(router.currentRoute.value.query).toMatchObject({ artist: '1' }))
    expect(router.currentRoute.value.query.album).toBeUndefined()
    await album!.trigger('focus')
    await vi.waitFor(() => expect(albumQueries.at(-1)).toEqual({ artist: '1', page_size: '20' }))
    await vi.waitFor(() => expect(wrapper.findAll('[role="option"]')).toHaveLength(1))
    await wrapper.get('[role="option"]').trigger('mousedown')
    await vi.waitFor(() =>
      expect(api.trackQueries.at(-1)).toEqual({ downloaded: 'false', artist: '1', album: '1' }),
    )
    // The whole library is never requested just to render options.
    expect(albumQueries.every((q) => q.page_size === '20')).toBe(true)
    server.events.removeAllListeners()
  })

  it('searches by text, keeps it in the URL and goes back to page one', async () => {
    const api = serve()
    const { wrapper, router } = await mount('/download?page=2', 'en', 'Digital Love')
    await wrapper.get('input[type="search"]').setValue('daft')
    await vi.waitFor(() => expect(router.currentRoute.value.query.search).toBe('daft'))
    expect(router.currentRoute.value.query.page).toBeUndefined()
    await vi.waitFor(() =>
      expect(api.trackQueries.at(-1)).toEqual({ downloaded: 'false', search: 'daft' }),
    )
  })

  it('combines the text with the artist and restores the search from the URL', async () => {
    const api = serve()
    await mount('/download?search=daft&artist=1')
    expect(api.trackQueries[0]).toEqual({ downloaded: 'false', search: 'daft', artist: '1' })
  })

  it('keeps the selection across pages and downloads the chosen ones', async () => {
    const api = serve()
    const { wrapper } = await mount()
    const chosen = button(wrapper, 'Download selected')
    expect(chosen.attributes('disabled')).toBeDefined()
    await wrapper.findAll('input[type=checkbox]')[0]!.setValue(true)
    await button(wrapper, 'Next').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Digital Love'))
    await wrapper.findAll('input[type=checkbox]')[0]!.setValue(true)
    expect(chosen.text()).toContain('(2)')
    await chosen.trigger('click')
    await vi.waitFor(() => expect(api.launched).toHaveLength(1))
    expect(api.launched[0]).toEqual({ kind: 'download', params: { track_ids: [1, 3] } })
    await button(wrapper, 'Previous').trigger('click')
    await vi.waitFor(() =>
      expect(api.trackQueries.at(-1)).toEqual({ downloaded: 'false', page: '1' }),
    )
  })

  it('unticking a checkbox removes it from the selection', async () => {
    serve()
    const { wrapper } = await mount()
    const box = wrapper.findAll('input[type=checkbox]')[1]!
    await box.setValue(true)
    await box.setValue(false)
    expect(button(wrapper, 'Download selected').attributes('disabled')).toBeDefined()
  })

  it('downloads every pending track and reloads the list when done', async () => {
    const api = serve()
    const { wrapper } = await mount()
    await button(wrapper, 'Download all pending').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Finished'))
    expect(api.launched[0]).toEqual({ kind: 'download', params: { all_pending: true } })
    await vi.waitFor(() => expect(api.trackQueries).toHaveLength(2))
  })

  it('if a download is already running, it shows it and does not allow another', async () => {
    serve({ latest: [run()], detail: run() })
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Running'))
    expect(wrapper.text()).toContain('A download is already running')
    expect(button(wrapper, 'Download all pending').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('does not follow the latest download if it already finished', async () => {
    serve({ latest: [run({ status: 'failed' })] })
    const { wrapper } = await mount()
    await vi.waitFor(() =>
      expect(button(wrapper, 'Download all').attributes('disabled')).toBeUndefined(),
    )
    expect(wrapper.text()).not.toContain('Failed')
  })

  it('if another one has started meanwhile (409), it follows that one', async () => {
    let latest: JobRun[] = []
    serve({
      launch: () => {
        latest = [run()]
        return HttpResponse.json({ detail: 'A job is already running' }, { status: 409 })
      },
      detail: run(),
    })
    server.use(http.get('/api/v1/jobs/runs/', () => page(latest)))
    const { wrapper } = await mount()
    await button(wrapper, 'Download all').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Running'))
    expect(wrapper.text()).not.toContain('A job is already running')
    wrapper.unmount()
  })

  it('shows the error if it cannot start', async () => {
    serve({ launch: () => HttpResponse.json({ detail: 'Not allowed' }, { status: 403 }) })
    const { wrapper } = await mount()
    await button(wrapper, 'Download all').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Not allowed'))
  })

  it('shows the error if the latest download fails to load', async () => {
    serve()
    server.use(http.get('/api/v1/jobs/runs/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(wrapper.text()).toContain('The server failed'))
  })

  it('shows the error if the pending tracks fail to load', async () => {
    serve()
    server.use(http.get('/api/v1/catalog/tracks/', () => new HttpResponse(null, { status: 500 })))
    await mount('/download', 'en', 'The server failed')
  })

  it('has the same texts in English and Spanish', () => {
    const keys = (tree: object): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [k] : keys(v).map((sub) => `${k}.${sub}`),
      )
    expect(keys(messages.en.download as object)).toEqual(keys(messages.es.download as object))
  })

  it('is translated to Spanish', async () => {
    serve()
    const { wrapper } = await mount('/download', 'es')
    expect(wrapper.text()).toContain('Descargar todas las pendientes')
  })
})

describe('Download mock handlers', () => {
  const titles = async (query: string) =>
    (await api<{ results: Track[] }>(`/api/v1/catalog/tracks/?${query}`)).results.map(
      (t) => t.title,
    )

  it('return the pending tracks, filtered by album', async () => {
    expect(await titles('downloaded=false')).toHaveLength(3)
    expect(await titles('downloaded=false&album=2')).toEqual(['Da Funk'])
    expect(await api('/api/v1/catalog/artists/')).toMatchObject({ count: 1 })
    expect(await api('/api/v1/catalog/albums/')).toMatchObject({ count: 2 })
  })

  it('let other track lists through', async () => {
    // Last: only answers if the area handler lets the request through. Only this area's,
    // because others (the Library) also answer track lists.
    server.resetHandlers(
      ...downloadHandlers,
      http.get('/api/v1/catalog/tracks/', () => page([track(7, 'Other')])),
    )
    expect(await titles('')).toEqual(['Other'])
    // `resetHandlers` with arguments replaces the initial ones: put them back.
    server.resetHandlers(...handlers)
  })

  it('opens the video preview in a modal and unloads the iframe on close', async () => {
    serve()
    server.use(
      http.get('/api/v1/catalog/tracks/:id/video/', () =>
        HttpResponse.json({
          video_id: 'abcdefghijk',
          embed_url: 'https://www.youtube-nocookie.com/embed/abcdefghijk',
        }),
      ),
    )
    const { wrapper } = await mount()
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    await button(wrapper, 'Preview').trigger('click')
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.get('h2').text()).toBe('Preview of One More Time')
    await vi.waitFor(() =>
      expect(dialog.find('iframe').attributes('src')).toBe(
        'https://www.youtube-nocookie.com/embed/abcdefghijk',
      ),
    )
    expect(dialog.get('iframe').attributes('referrerpolicy')).toBe(
      'strict-origin-when-cross-origin',
    )
    expect(dialog.get('iframe').attributes('title')).toBe('One More Time')
    await button(wrapper, 'Close').trigger('click')
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('closing with Esc also unloads the iframe', async () => {
    serve()
    server.use(
      http.get('/api/v1/catalog/tracks/:id/video/', () =>
        HttpResponse.json({ video_id: 'abcdefghijk', embed_url: 'https://e/embed/a' }),
      ),
    )
    const { wrapper } = await mount()
    await button(wrapper, 'Preview').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('iframe').exists()).toBe(true))
    wrapper.get('dialog').element.dispatchEvent(new Event('close'))
    await vi.waitFor(() => expect(wrapper.find('iframe').exists()).toBe(false))
  })

  it('warns when there is no video for the track', async () => {
    serve()
    server.use(
      http.get('/api/v1/catalog/tracks/:id/video/', () =>
        HttpResponse.json({ detail: 'No video matches the track.' }, { status: 404 }),
      ),
    )
    const { wrapper } = await mount()
    await button(wrapper, 'Preview').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('dialog[open]').text()).toContain('No video matches'))
    expect(wrapper.find('iframe').exists()).toBe(false)
  })
})
