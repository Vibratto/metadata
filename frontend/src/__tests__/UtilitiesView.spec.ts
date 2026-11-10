import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { components } from '../api/schema'
import { POLL_MS } from '../composables/useJobRun'
import { messages } from '../locales'
import { routes } from '../router'
import { server } from '../mocks/server'
import UtilitiesView from '../views/UtilitiesView.vue'
import { render } from './helpers'
import { mountView, sessionPinia } from './viewHelpers'

type JobRun = components['schemas']['JobRun']

const run = (fields: Partial<JobRun> = {}): JobRun => ({
  id: 8,
  kind: 'maintenance',
  params: {},
  user: 'demo',
  status: 'running',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 1,
  total: 3,
  current: 'a.mp3',
  summary: {},
  ...fields,
})

/** Serves the job: the detail returns `states` in order (the last one repeats). */
function serve(states: JobRun[]) {
  const bodies: unknown[] = []
  let detail = 0
  server.use(
    http.post('/api/v1/jobs/runs/', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json(run({ status: 'pending' }), { status: 201 })
    }),
    http.get('/api/v1/jobs/runs/8/', () =>
      HttpResponse.json(states[Math.min(detail++, states.length - 1)]),
    ),
    http.get('/api/v1/jobs/runs/8/lines/', () => HttpResponse.json([])),
  )
  return bodies
}

const mount = async () => (await mountView(UtilitiesView, '/utilities')).wrapper
const boxes = (wrapper: Awaited<ReturnType<typeof mount>>) =>
  wrapper.findAll('input[type="checkbox"]')
const startButton = (wrapper: Awaited<ReturnType<typeof mount>>) =>
  wrapper.findAll('button').find((b) => b.text() === 'Run')!

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }))
afterEach(() => vi.useRealTimers())

describe('UtilitiesView', () => {
  it('offers the seven operations, all ticked except relocating and completing albums', async () => {
    const wrapper = await mount()
    expect(wrapper.findAll('.check').map((c) => c.text())).toEqual([
      'Retag the downloaded files',
      'Recompute the ReplayGain of the whole library',
      'Move the files to the template names, without retagging',
      'Check the files are still on disk',
      'Refresh artist profiles (image, description and audience)',
      'Look up missing lyrics (LRCLIB and YouTube Music)',
      'Complete albums with their missing tracks (queries YouTube Music)',
    ])
    expect(boxes(wrapper).map((b) => (b.element as HTMLInputElement).checked)).toEqual([
      true,
      true,
      false,
      true,
      true,
      true,
      false,
    ])
  })

  it('does not allow rewriting tags and relocating in the same run', async () => {
    const wrapper = await mount()
    await boxes(wrapper)[2].setValue(true)
    const warning = 'Retagging and ReplayGain do not go in the same run as relocating'
    expect(startButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain(warning)
    await boxes(wrapper)[0].setValue(false)
    expect(startButton(wrapper).attributes('disabled')).toBeDefined()
    await boxes(wrapper)[1].setValue(false)
    expect(startButton(wrapper).attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain(warning)
  })

  it('starts only the chosen operations', async () => {
    const bodies = serve([run({ status: 'succeeded' })])
    const wrapper = await mount()
    await boxes(wrapper)[0].setValue(false)
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      kind: 'maintenance',
      params: { operations: ['replaygain', 'check_files', 'complete_artists', 'lyrics'] },
    })
  })

  it('“Complete albums” spends YouTube Music requests: it comes unticked and runs once ticked', async () => {
    const bodies = serve([run({ status: 'succeeded' })])
    const wrapper = await mount()
    expect(wrapper.text()).toContain('Complete albums with their missing tracks')
    const last = boxes(wrapper)[boxes(wrapper).length - 1]
    expect((last.element as HTMLInputElement).checked).toBe(false)
    await last.setValue(true)
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect((bodies[0] as { params: { operations: string[] } }).params.operations).toContain(
      'complete_albums',
    )
  })

  it('does not allow starting without operations', async () => {
    const wrapper = await mount()
    for (const box of boxes(wrapper)) await box.setValue(false)
    expect(startButton(wrapper).attributes('disabled')).toBeDefined()
  })

  it('follows the job and does not allow another while it is active', async () => {
    serve([run()])
    const wrapper = await mount()
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Running'))
    expect(startButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.find('.summary').exists()).toBe(false)
  })

  it('shows the final summary with the missing files and the changes', async () => {
    serve([
      run(),
      run({
        status: 'succeeded',
        done: 3,
        summary: {
          retag: { retagged: 5, failed: 1 },
          replaygain: { albums: 2, files: 9, failed: 1 },
          relocate: { moved: 4, unchanged: 2, failed: 0 },
          check_files: { checked: 6, missing: [3, 7] },
          complete_artists: { reviewed: 5, completed: 3, unchanged: 1, errors: 1 },
          lyrics: { found: 3, not_found: 2, failed: 1 },
          complete_albums: { albums: 8, tracks: 5, reused_recordings: 4, errors: 1 },
        },
      }),
    ])
    const wrapper = await mount()
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Running'))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.find('.summary').exists()).toBe(true))
    expect(wrapper.findAll('.summary li').map((l) => l.text())).toEqual([
      'Files retagged: 5. Failed: 1.',
      'ReplayGain: 2 albums and 9 files. Failed albums: 1.',
      'Files moved: 4. Already in place: 2. Failed: 0.',
      'Files checked: 6. Missing: 2.',
      'Downloads without a file: #3, #7.',
      'Artists reviewed: 5. Completed: 3. Unchanged: 1. Failed: 1.',
      'Lyrics saved: 3. Not found: 2. No answer: 1.',
      'Albums checked: 8. Tracks added: 5 (4 with an already known recording). No answer from YouTube Music: 1.',
    ])
  })

  it('summarises only the operations run and omits the list if nothing is missing', async () => {
    serve([run({ status: 'stopped', summary: { check_files: { checked: 2, missing: [] } } })])
    const wrapper = await mount()
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(wrapper.find('.summary').exists()).toBe(true))
    expect(wrapper.findAll('.summary li').map((l) => l.text())).toEqual([
      'Files checked: 2. Missing: 0.',
    ])
  })

  it('without a summary (failed job) it does not show the section', async () => {
    serve([run({ status: 'failed' })])
    const wrapper = await mount()
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Failed'))
    expect(wrapper.find('.summary').exists()).toBe(false)
  })

  it('shows the API rejection on start', async () => {
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json({ detail: 'A job of this kind is already running.' }, { status: 409 }),
      ),
    )
    const wrapper = await mount()
    await startButton(wrapper).trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe('A job of this kind is already running.'),
    )
  })

  it('links to the library backup', async () => {
    expect((await mount()).get('a[href="/library/backup"]').text()).toBe('Library backup')
  })

  it('translates to Spanish', async () => {
    const wrapper = render(
      UtilitiesView,
      {
        global: {
          plugins: [createRouter({ history: createMemoryHistory(), routes }), sessionPinia()],
        },
      },
      'es',
    )
    expect(wrapper.get('h1').text()).toBe('Utilidades')
    expect(wrapper.findAll('button').at(-1)!.text()).toBe('Ejecutar')
  })

  it('has the same keys in en and es', () => {
    expect(Object.keys(messages.en.utilities as object)).toEqual(
      Object.keys(messages.es.utilities as object),
    )
  })
})
