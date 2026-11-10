import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import type { components } from '../api/schema'
import JobRunPanel from '../components/JobRunPanel.vue'
import { POLL_MS, useJobRun, type JobRunHandle } from '../composables/useJobRun'
import { server } from '../mocks/server'
import { render } from './helpers'
import { sessionPinia } from './viewHelpers'

type JobRun = components['schemas']['JobRun']
type Line = components['schemas']['JobRunLine']

const run = (fields: Partial<JobRun> = {}): JobRun => ({
  id: 5,
  kind: 'download',
  params: {},
  user: 'demo',
  status: 'running',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 1,
  total: 4,
  current: 'One More Time',
  summary: {},
  ...fields,
})
const line = (position: number, level: Line['level'] = 'info'): Line => ({
  position,
  level,
  message: `line ${position}`,
  created_at: '2026-01-01T10:00:00Z',
})

/**
 * Mocks the server side of a job: `states` are what the detail returns on each poll (the
 * last one repeats) and `batches` the lines per request. Records every `after`.
 */
function serve(states: JobRun[], batches: Line[][] = []) {
  const afters: string[] = []
  let detail = 0
  server.use(
    http.post('/api/v1/jobs/runs/', () =>
      HttpResponse.json(run({ status: 'pending' }), { status: 201 }),
    ),
    http.get('/api/v1/jobs/runs/5/', () =>
      HttpResponse.json(states[Math.min(detail++, states.length - 1)]),
    ),
    http.get('/api/v1/jobs/runs/5/lines/', ({ request }) => {
      afters.push(new URL(request.url).searchParams.get('after') as string)
      return HttpResponse.json(batches.shift() ?? [])
    }),
  )
  return { afters, detailCalls: () => detail }
}

function mount(locale = 'en') {
  let job!: JobRunHandle
  const Host = defineComponent({
    setup() {
      job = useJobRun()
      return () => h(JobRunPanel, { job })
    },
  })
  const wrapper = render(Host, { global: { plugins: [sessionPinia()] } }, locale)
  return { wrapper, job: () => job }
}

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }))
afterEach(() => vi.useRealTimers())

describe('useJobRun y JobRunPanel', () => {
  it('shows nothing before starting', () => {
    expect(mount().wrapper.find('section').exists()).toBe(false)
  })

  it('starts the job with its kind and params and shows the progress', async () => {
    let body: unknown
    serve([run()])
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(run({ status: 'pending' }), { status: 201 })
      }),
    )
    const { wrapper, job } = mount()
    expect(await job().start('download', { all_pending: true })).toBe(true)
    expect(body).toEqual({ kind: 'download', params: { all_pending: true } })
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Running'))
    expect(wrapper.get('.job__status').text()).toContain('1 / 4')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('25')
    expect(wrapper.get('.job__current').text()).toBe('One More Time')
  })

  it('starts without params', async () => {
    let body: unknown
    serve([run({ status: 'succeeded' })])
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(run(), { status: 201 })
      }),
    )
    await mount().job().start('watch_check')
    expect(body).toEqual({ kind: 'watch_check', params: {} })
  })

  it('shows the API rejection on start', async () => {
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json({ detail: 'A job of this kind is already running.' }, { status: 409 }),
      ),
    )
    const { wrapper, job } = mount()
    expect(await job().start('download')).toBe(false)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('A job of this kind is already running.')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('asks only for the new lines on each poll', async () => {
    const { afters } = serve([run()], [[line(1), line(2, 'warning')], [line(3, 'error')]])
    const { wrapper, job } = mount()
    await job().start('download')
    await vi.waitFor(() => expect(wrapper.findAll('.job__line')).toHaveLength(2))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.findAll('.job__line')).toHaveLength(3))
    expect(afters.slice(0, 2)).toEqual(['0', '2'])
    expect(wrapper.get('[role="log"]').attributes('aria-label')).toBe('Job log')
    expect(wrapper.get('.job__line--warning').text()).toBe('line 2')
    expect(wrapper.get('.job__line--error').text()).toBe('line 3')
  })

  it('polling does not count as activity: it does not renew an idle session', async () => {
    const polls: (string | null)[] = []
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json(run({ status: 'pending' }), { status: 201 }),
      ),
      http.get('/api/v1/jobs/runs/5/', ({ request }) => {
        polls.push(request.headers.get('X-Background-Poll'))
        return HttpResponse.json(run())
      }),
      http.get('/api/v1/jobs/runs/5/lines/', ({ request }) => {
        polls.push(request.headers.get('X-Background-Poll'))
        return HttpResponse.json([])
      }),
    )
    const { job } = mount()
    await job().start('download')
    await vi.waitFor(() => expect(polls).toHaveLength(2))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(polls).toHaveLength(4))
    expect(new Set(polls)).toEqual(new Set(['1']))
  })

  it('stops polling once the job closes, after reading all its lines', async () => {
    const closed = run({ status: 'succeeded', done: 4, current: '' })
    const { afters, detailCalls } = serve([closed], [[line(1)], [line(2)]])
    const { wrapper, job } = mount()
    await job().start('download')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Finished'))
    expect(afters).toEqual(['0', '1', '2'])
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('.job__current').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(detailCalls()).toBe(1)
  })

  it('stops the job and keeps following until it closes', async () => {
    serve([run(), run({ status: 'stopped' })])
    let stopped = false
    server.use(
      http.post('/api/v1/jobs/runs/5/stop/', () => {
        stopped = true
        return HttpResponse.json(run({ status: 'stopping' }))
      }),
    )
    const { wrapper, job } = mount()
    await job().start('download')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Running'))
    expect(wrapper.get('button').text()).toBe('Stop')
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(stopped).toBe(true))
    await vi.waitFor(() => expect(wrapper.get('button').attributes('disabled')).toBeDefined())
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Stopped'))
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('shows the error on stop', async () => {
    serve([run()])
    server.use(
      http.post('/api/v1/jobs/runs/5/stop/', () =>
        HttpResponse.json({ detail: 'The job has already finished.' }, { status: 409 }),
      ),
    )
    const { wrapper, job } = mount()
    await job().start('download')
    await job().stop()
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe('The job has already finished.'),
    )
  })

  it('stopping without a job does nothing', async () => {
    const { job } = mount()
    await job().stop()
    expect(job().error).toBe('')
  })

  it('a poll failure is shown, retried and cleared once it works', async () => {
    serve([run({ status: 'succeeded' })])
    server.use(http.get('/api/v1/jobs/runs/5/', () => HttpResponse.error(), { once: true }))
    const { wrapper, job } = mount()
    await job().start('download')
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe('Could not reach the server.'),
    )
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(false))
    expect(wrapper.get('.job__status').text()).toContain('Finished')
  })

  it('follows an existing run by id', async () => {
    serve([run({ status: 'failed', total: 0 })], [[line(1)]])
    const { wrapper, job } = mount()
    await job().follow(5)
    await vi.waitFor(() => expect(wrapper.findAll('.job__line')).toHaveLength(1))
    expect(wrapper.get('.job__status').text()).toBe('Failed')
  })

  it('shows the error if the run does not exist', async () => {
    server.use(http.get('/api/v1/jobs/runs/9/', () => new HttpResponse(null, { status: 404 })))
    const { wrapper, job } = mount()
    await job().follow(9)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe(
      'We could not find what you were looking for.',
    )
  })

  it('following another run drops the in-flight poll of the previous one', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    serve([run()])
    server.use(
      http.get('/api/v1/jobs/runs/5/lines/', async () => {
        await gate
        return HttpResponse.json([line(1)])
      }),
      http.get('/api/v1/jobs/runs/6/', () =>
        HttpResponse.json(run({ id: 6, status: 'succeeded' })),
      ),
      http.get('/api/v1/jobs/runs/6/lines/', () => HttpResponse.json([])),
    )
    const { job } = mount()
    await job().start('download')
    await job().follow(6)
    release()
    await vi.waitFor(() => expect(job().run?.id).toBe(6))
    await flushPromises()
    expect(job().lines).toEqual([])
  })

  it('stops polling when the view unmounts', async () => {
    const { detailCalls } = serve([run()])
    const { wrapper, job } = mount()
    await job().start('download')
    await vi.waitFor(() => expect(detailCalls()).toBe(1))
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(detailCalls()).toBe(1)
  })

  it('an answer arriving after unmount does not schedule another poll', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const { detailCalls } = serve([run()])
    server.use(
      http.get('/api/v1/jobs/runs/5/', async () => {
        await gate
        return HttpResponse.error()
      }),
    )
    const { wrapper, job } = mount()
    await job().start('download')
    wrapper.unmount()
    release()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(detailCalls()).toBe(0)
  })

  it('translates to Spanish', async () => {
    serve([run()])
    const { wrapper, job } = mount('es')
    await job().start('download')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('En curso'))
    expect(wrapper.get('button').text()).toBe('Detener')
  })
})
