import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { messages } from '../locales'

import { server } from '../mocks/server'
import TrackUploadView from '../views/TrackUploadView.vue'
import { mountView } from './viewHelpers'

const URL = '/api/v1/catalog/tracks/101/upload/'

async function choose(wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], name = 'a.wav') {
  const input = wrapper.get('input[type="file"]')
  const file = new File(['audio'], name, { type: 'audio/wav' })
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  return file
}

describe('TrackUploadView', () => {
  it('shows the track and does not allow sending without a file', async () => {
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    expect(wrapper.get('h1').text()).toBe('Upload audio')
    expect(wrapper.text()).toContain('Giorgio by Moroder')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('uploads the chosen file with the CSRF token and reports when done', async () => {
    const sent: Request[] = []
    const listen = ({ request }: { request: Request }) => void sent.push(request.clone())
    server.events.on('request:start', listen)
    document.cookie = 'csrftoken=abc'
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper, 'recording.wav')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.find('[role="status"]').exists()).toBe(true))
    server.events.removeListener('request:start', listen)
    expect(wrapper.get('[role="status"]').text()).toBe('Audio saved. The track is now downloaded.')
    const upload = sent.find((r) => r.method === 'POST')
    expect(upload?.headers.get('X-CSRFToken')).toBe('abc')
    expect(((await upload?.formData())?.get('file') as File).name).toBe('recording.wav')
  })

  it('sends nothing if the chosen file is removed', async () => {
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper)
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [] })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('renders the uploaded percentage when the browser knows it', async () => {
    const xhrs: FakeXhr[] = []
    class FakeXhr {
      upload: { onprogress?: (e: Partial<ProgressEvent>) => void } = {}
      constructor() {
        xhrs.push(this)
      }
      open() {}
      setRequestHeader() {}
      send() {}
    }
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper)
    await wrapper.get('form').trigger('submit')
    const bar = () => wrapper.get('[role="progressbar"]').attributes('aria-valuenow')
    xhrs[0]?.upload.onprogress?.({ lengthComputable: false, loaded: 1, total: 0 })
    await flushPromises()
    expect(bar()).toBe('0')
    xhrs[0]?.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 200 })
    await flushPromises()
    expect(bar()).toBe('25')
    vi.unstubAllGlobals()
  })

  it('shows the progress while uploading', async () => {
    let finish: () => void = () => {}
    server.use(
      http.post(URL, async () => {
        await new Promise<void>((resolve) => (finish = resolve))
        return HttpResponse.json({ id: 7, downloaded: true }, { status: 201 })
      }),
    )
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(true)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    finish()
    await vi.waitFor(() => expect(wrapper.find('[role="progressbar"]').exists()).toBe(false))
  })

  it('shows the server validation error', async () => {
    server.use(
      http.post(URL, () =>
        HttpResponse.json({ file: ['The file is not valid audio.'] }, { status: 400 }),
      ),
    )
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper, 'notas.txt')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(true))
    expect(wrapper.get('[role="alert"]').text()).toBe('The file is not valid audio.')
  })

  it('shows a generic error if the server does not explain the failure', async () => {
    server.use(http.post(URL, () => new HttpResponse('boom', { status: 500 })))
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper)
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(true))
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })

  it('warns when there is no connection', async () => {
    server.use(http.post(URL, () => HttpResponse.error()))
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    await choose(wrapper)
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(true))
    expect(wrapper.get('[role="alert"]').text()).toBe('Could not reach the server.')
  })

  it('warns if the track does not exist', async () => {
    server.use(
      http.get('/api/v1/catalog/tracks/:id/', () =>
        HttpResponse.json({ detail: 'Not found.' }, { status: 404 }),
      ),
    )
    const { wrapper } = await mountView(TrackUploadView, '/tracks/101/upload')
    expect(wrapper.get('[role="alert"]').text()).toBe('Not found.')
  })

  it('has a route and no navigation entry', async () => {
    const { router } = await mountView(TrackUploadView, '/tracks/101/upload')
    const route = router.resolve({ name: 'track-upload', params: { id: 7 } })
    expect(route.path).toBe('/tracks/7/upload')
    expect(route.meta.navLabel).toBeUndefined()
  })
  it('has the same texts in English and Spanish', () => {
    const keys = (tree: object): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [k] : keys(v as object).map((c) => `${k}.${c}`),
      )
    expect(keys(messages.en.trackUpload as object)).toEqual(keys(messages.es.trackUpload as object))
  })
})
